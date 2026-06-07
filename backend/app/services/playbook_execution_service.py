"""
Playbook execution engine — semantic, window-aware, resilient.

For every step:
  1. Try to focus the target window (by window_title then app_name).
  2. Route to the action-specific handler.
  3. If payload fields (text / value / keys / coordinates) are empty,
     extract them from the human-readable description as a fallback.

Security: only ALLOWED_ACTIONS may execute. Any other action raises SecurityError.
"""

import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

from app.domain.models import SkillStep

logger = logging.getLogger(__name__)

ALLOWED_ACTIONS = {
    "click", "type", "hotkey", "key", "navigate_url",
    "open_app", "scroll", "focus", "close_window", "switch_window",
}

# pynput / LLM key names → pyautogui key names
_KEY_MAP: dict[str, str] = {
    "enter": "enter", "return": "enter",
    "tab": "tab", "escape": "escape", "esc": "escape",
    "backspace": "backspace", "delete": "delete",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "ctrl_l": "ctrl", "ctrl_r": "ctrl", "ctrl": "ctrl",
    "shift": "shift", "shift_l": "shift", "shift_r": "shift",
    "alt_l": "alt", "alt_r": "alt", "alt": "alt",
    "home": "home", "end": "end",
    "page_up": "pageup", "page_down": "pagedown",
    "space": "space", "spacebar": "space",
    "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4", "f5": "f5",
    "f6": "f6", "f7": "f7", "f8": "f8", "f9": "f9", "f10": "f10",
    "f11": "f11", "f12": "f12",
    "caps_lock": "capslock",
}

# Natural-language phrases → pyautogui key (longer phrases matched first)
_PHRASE_KEY: list[tuple[str, str]] = sorted([
    ("arrow down", "down"), ("down arrow", "down"), ("downward", "down"),
    ("arrow up",   "up"),   ("up arrow",   "up"),   ("upward",   "up"),
    ("arrow left", "left"), ("left arrow", "left"),
    ("arrow right","right"),("right arrow","right"),
    ("enter key",  "enter"),("press enter","enter"),("return key","enter"),
    ("escape key", "escape"),("esc key",   "escape"),
    ("tab key",    "tab"),
    ("backspace",  "backspace"),
    ("delete key", "delete"),
    ("space bar",  "space"), ("spacebar",  "space"),
    ("page down",  "pagedown"), ("page up", "pageup"),
    ("home key",   "home"),  ("end key",   "end"),
], key=lambda t: len(t[0]), reverse=True)


try:
    import pyautogui  # type: ignore
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    _PA = True
except Exception:
    _PA = False
    logger.warning("pyautogui not available — execution disabled")


class SecurityError(Exception):
    pass


@dataclass
class StepResult:
    step_index: int
    action: str
    description: str
    status: str        # ok | failed | paused | skipped
    message: str = ""


@dataclass
class RunResult:
    playbook_id: str
    status: str        # running | completed | paused | failed
    steps_total: int = 0
    steps_completed: int = 0
    steps_failed: int = 0
    pause_at_step: Optional[int] = None
    log: list[StepResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers — payload extraction
# ---------------------------------------------------------------------------

def _extract_text(step: SkillStep) -> str:
    """Return the text to type. Falls back to parsing the description."""
    text = step.text or step.value
    if text:
        return text
    # Pattern: typed "X", types "X", entered "X", writes "X", sends "X"
    m = re.search(
        r'(?:type[sd]?|enter[sd]?|input[sd]?|write[sd]?|send[sd]?)\s+["\'""''](.+?)["\'""'']',
        step.description, re.IGNORECASE
    )
    if m:
        return m.group(1)
    # Any quoted string
    m = re.search(r'["''""](.+?)["''""]', step.description)
    if m:
        return m.group(1)
    return ""


def _extract_key(step: SkillStep) -> str:
    """Return the key to press. Falls back to parsing the description."""
    raw = (step.value or step.text or "").strip().lower()
    if raw:
        return _KEY_MAP.get(raw, raw)
    desc = step.description.lower()
    for phrase, key in _PHRASE_KEY:
        if phrase in desc:
            return key
    # Single key words
    for word in ("enter", "escape", "tab", "space", "backspace", "delete",
                 "up", "down", "left", "right", "home", "end"):
        if re.search(rf"\b{word}\b", desc):
            return word
    return ""


# ---------------------------------------------------------------------------
# Window focusing
# ---------------------------------------------------------------------------

def _focus_window(app_name: str, window_title: str) -> bool:
    """Bring the best matching window to foreground using pure Win32 ctypes.

    pygetwindow.activate() can hang; this uses EnumWindows + SetForegroundWindow
    directly — no blocking calls, no extra dependencies.
    """
    if not app_name and not window_title:
        return False
    try:
        import ctypes
        import ctypes.wintypes as wt

        user32 = ctypes.windll.user32
        found: list[int] = []
        wt_lower = window_title.lower() if window_title else ""
        an_lower = app_name.lower() if app_name else ""

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def _cb(hwnd: int, _: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd) + 1
            buf = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hwnd, buf, length)
            title = buf.value.lower()
            if (wt_lower and wt_lower in title) or (an_lower and an_lower in title):
                found.append(hwnd)
                return False   # stop enumeration on first match
            return True

        user32.EnumWindows(_cb, 0)

        if not found:
            return False

        hwnd = found[0]
        # SW_RESTORE = 9 — un-minimises without blocking
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.3)
        logger.debug("Focused hwnd=%d", hwnd)
        return True
    except Exception as exc:
        logger.debug("_focus_window failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Per-action handlers
# ---------------------------------------------------------------------------

def _handle_type(step: SkillStep) -> bool:
    _focus_window(step.app_name, step.window_title)
    text = _extract_text(step)
    if not text:
        return False
    if _PA:
        try:
            pyautogui.write(text, interval=0.05)
            return True
        except Exception as e:
            logger.debug("write failed: %s", e)
    return False


def _handle_navigate_url(step: SkillStep) -> bool:
    _focus_window(step.app_name, step.window_title)
    url = step.url or step.text
    if not url:
        return False
    if _PA:
        try:
            time.sleep(0.3)
            pyautogui.hotkey("ctrl", "l")
            time.sleep(0.4)
            pyautogui.hotkey("ctrl", "a")
            pyautogui.write(url, interval=0.04)
            time.sleep(0.2)
            pyautogui.press("enter")
            return True
        except Exception as e:
            logger.debug("navigate_url failed: %s", e)
    return False


def _handle_hotkey(step: SkillStep) -> bool:
    _focus_window(step.app_name, step.window_title)
    keys = list(step.keys) if step.keys else []
    if not keys and step.value:
        keys = [k.strip() for k in re.split(r"[+,\s]+", step.value) if k.strip()]
    if not keys:
        return False
    if _PA:
        try:
            mapped = [_KEY_MAP.get(k.lower(), k.lower()) for k in keys]
            pyautogui.hotkey(*mapped)
            return True
        except Exception as e:
            logger.debug("hotkey %s failed: %s", keys, e)
    return False


def _handle_click(step: SkillStep) -> bool:
    x = step.coordinates.get("x", 0)
    y = step.coordinates.get("y", 0)
    if (x or y) and _PA:
        try:
            pyautogui.click(x, y)
            return True
        except Exception as e:
            logger.debug("click(%d,%d) failed: %s", x, y, e)
    # No coordinates — focus the window (acts as "click into window")
    return _focus_window(step.app_name, step.window_title)


def _handle_open_app(step: SkillStep) -> bool:
    app = step.app_name or step.text
    if not app:
        return False
    for fn in [lambda: os.startfile(app), lambda: subprocess.Popen(app, shell=True)]:
        try:
            fn()
            time.sleep(1.5)
            return True
        except Exception:
            pass
    return False


def _handle_key(step: SkillStep) -> bool:
    _focus_window(step.app_name, step.window_title)
    key = _extract_key(step)
    if not key:
        return False
    if _PA:
        try:
            pyautogui.press(key)
            return True
        except Exception as e:
            logger.debug("press(%s) failed: %s", key, e)
    return False


def _handle_scroll(step: SkillStep) -> bool:
    _focus_window(step.app_name, step.window_title)
    direction = (step.value or step.text or "down").lower()
    x = step.coordinates.get("x") or None
    y = step.coordinates.get("y") or None
    clicks = -5 if "down" in direction else 5
    if _PA:
        try:
            if x and y:
                pyautogui.scroll(clicks, x=x, y=y)
            else:
                pyautogui.scroll(clicks)
            return True
        except Exception as e:
            logger.debug("scroll failed: %s", e)
    return False


def _handle_close_window(step: SkillStep) -> bool:
    _focus_window(step.app_name, step.window_title)
    if _PA:
        try:
            pyautogui.hotkey("alt", "f4")
            return True
        except Exception:
            pass
    return False


def _handle_switch_window(step: SkillStep) -> bool:
    # Try direct focus first
    if _focus_window(step.app_name, step.window_title):
        return True
    if _PA:
        try:
            pyautogui.hotkey("alt", "tab")
            time.sleep(0.5)
            return True
        except Exception:
            pass
    return True  # informational — don't fail the run


_HANDLERS: dict[str, object] = {
    "type":          _handle_type,
    "navigate_url":  _handle_navigate_url,
    "hotkey":        _handle_hotkey,
    "click":         _handle_click,
    "open_app":      _handle_open_app,
    "key":           _handle_key,
    "scroll":        _handle_scroll,
    "close_window":  _handle_close_window,
    "switch_window": _handle_switch_window,
    "focus":         _handle_click,
}


# ---------------------------------------------------------------------------
# Validation & entry point
# ---------------------------------------------------------------------------

def _validate(steps: list[SkillStep]) -> None:
    for step in steps:
        if step.action not in ALLOWED_ACTIONS:
            raise SecurityError(
                f"Step {step.step_index} has disallowed action '{step.action}'. "
                f"Allowed: {sorted(ALLOWED_ACTIONS)}"
            )


def execute(playbook_id: str, steps: list[SkillStep], confirm_step: Optional[int] = None) -> RunResult:
    result = RunResult(playbook_id=playbook_id, status="running", steps_total=len(steps))

    try:
        _validate(steps)
    except SecurityError as exc:
        result.status = "failed"
        result.log.append(StepResult(-1, "validate", "", "failed", str(exc)))
        return result

    start_from = confirm_step if confirm_step is not None else 0

    for step in steps:
        if step.step_index < start_from:
            continue

        if step.requires_confirmation and confirm_step is None:
            result.status = "paused"
            result.pause_at_step = step.step_index
            result.log.append(StepResult(
                step.step_index, step.action, step.description, "paused",
                "Waiting for user confirmation before executing this step.",
            ))
            return result

        time.sleep(0.4)

        handler = _HANDLERS.get(step.action)
        success = bool(handler(step)) if handler else False  # type: ignore[operator]

        if success:
            result.steps_completed += 1
            result.log.append(StepResult(step.step_index, step.action, step.description, "ok"))
            logger.info("Step %d OK: %s", step.step_index, step.description)
        else:
            result.steps_failed += 1
            # Build a helpful message explaining what was missing
            if step.action == "type":
                got = _extract_text(step)
                msg = f"No text to type — add text to step or update description with quoted text. Got: '{got}'"
            elif step.action == "key":
                got = _extract_key(step)
                msg = f"No key to press — add key name to 'value' field. Got: '{got}'"
            elif step.action == "click" and not step.coordinates.get("x"):
                msg = "No coordinates for click — window focus attempted as fallback"
            else:
                msg = f"Handler returned False for action '{step.action}'"
            result.log.append(StepResult(step.step_index, step.action, step.description, "failed", msg))
            logger.warning("Step %d FAILED (%s): %s", step.step_index, step.action, step.description)

    result.status = "completed" if result.steps_failed == 0 else "failed"
    return result
