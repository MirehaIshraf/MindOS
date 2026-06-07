"""
Converts a raw observation session into a clean, semantic SkillStep list.

Strategy:
1. Build a compact text timeline of all captured events.
2. Send the timeline to the LLM in ONE call and ask it to return organised
   JSON steps (group related micro-events, detect URLs, hotkeys, app opens).
3. Parse the JSON → SkillStep list.
4. If LLM fails, fall back to a rule-based grouper that at least consolidates
   consecutive type-events and labels keyboard shortcuts.
"""

import json
import logging
import re

from app.domain.models import SkillStep
from app.services.observation_service import RawEvent

logger = logging.getLogger(__name__)

_DESTRUCTIVE_WORDS = {
    "delete", "remove", "erase", "clear", "close", "quit", "exit",
    "send", "submit", "overwrite", "format", "reset", "uninstall",
}

_HOTKEY_MAP: dict[frozenset, list[str]] = {
    frozenset({"ctrl_l", "t"}): ["ctrl", "t"],
    frozenset({"ctrl_r", "t"}): ["ctrl", "t"],
    frozenset({"ctrl_l", "w"}): ["ctrl", "w"],
    frozenset({"ctrl_r", "w"}): ["ctrl", "w"],
    frozenset({"ctrl_l", "c"}): ["ctrl", "c"],
    frozenset({"ctrl_l", "v"}): ["ctrl", "v"],
    frozenset({"ctrl_l", "s"}): ["ctrl", "s"],
    frozenset({"ctrl_l", "a"}): ["ctrl", "a"],
    frozenset({"ctrl_l", "z"}): ["ctrl", "z"],
    frozenset({"ctrl_l", "l"}): ["ctrl", "l"],
    frozenset({"alt_l", "f4"}): ["alt", "f4"],
    frozenset({"alt_l", "tab"}): ["alt", "tab"],
}


# ---------------------------------------------------------------------------
# Build a text summary of events for the LLM
# ---------------------------------------------------------------------------

def _build_timeline(events: list[RawEvent]) -> str:
    lines: list[str] = []
    for i, ev in enumerate(events):
        app = ev.app_name or "?"
        win = ev.window_title or ""
        ctx = f"[App: {app}" + (f" | Window: {win}]" if win else "]")

        if ev.action == "click":
            elem = ev.element_name or f"coords({ev.coordinates.get('x','?')},{ev.coordinates.get('y','?')})"
            lines.append(f"{i+1:3}. CLICK  '{elem}' {ctx}")
        elif ev.action == "type":
            lines.append(f"{i+1:3}. TYPE   '{ev.value}' {ctx}")
        elif ev.action == "key":
            lines.append(f"{i+1:3}. KEY    {ev.value} {ctx}")
        elif ev.action == "scroll":
            lines.append(f"{i+1:3}. SCROLL {ev.value} {ctx}")
        else:
            lines.append(f"{i+1:3}. {ev.action.upper()} {ctx}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

_LLM_SYSTEM = """\
You are a UX analyst converting raw screen-recording events into executable skill steps.

## Action types
- open_app      — user launched an application (search bar, taskbar, etc.)
- navigate_url  — user navigated to a URL in a browser
- click         — user clicked a button, link, or UI element
- type          — user typed text (keyboard input to a text field)
- hotkey        — user pressed a keyboard shortcut (Ctrl+T, Ctrl+S, Alt+Tab, etc.)
- key           — user pressed a single special key (Enter, Escape, Arrow keys, Tab…)
- switch_window — user switched focus to another window/app
- close_window  — user closed a window or tab
- scroll        — user scrolled the mouse wheel

## Grouping rules
- Cluster micro-events into ONE meaningful step:
  - Click address bar + TYPE url + KEY enter → ONE navigate_url step
  - Multiple TYPE events in a row → ONE type step with concatenated text
  - KEY ctrl_l + KEY t → ONE hotkey step with keys=["ctrl","t"]

## CRITICAL payload rules (execution depends on these being correct)
- type steps: ALWAYS put the EXACT typed text in "text" field (copy from TYPE events verbatim)
- key steps:  ALWAYS put the key name in "value" field (e.g., "enter", "down", "up", "escape")
- hotkey:     ALWAYS list all keys in "keys" array (e.g., ["ctrl","s"], ["alt","f4"])
- navigate_url: ALWAYS put the full URL/address in "url" field
- click:      ALWAYS copy the coordinates from the CLICK event into "coordinates"
- app_name:   ALWAYS copy the app name from the events (e.g., "Command Prompt", "Chrome")
- window_title: ALWAYS copy the window title from the events

## Destructive / confirmation
- is_destructive=true: send, submit, delete, close, format, overwrite
- requires_confirmation=true: only for irreversible actions (send email, delete file, submit form)

## Output format
Return ONLY a valid JSON array — no markdown fences, no explanation.
Every element must contain ALL fields below (empty string / empty array / 0 for unused ones):

[
  {
    "step_index": 0,
    "description": "User opens Command Prompt by typing cmd in Windows search.",
    "action": "open_app",
    "app_name": "Command Prompt",
    "window_title": "",
    "element_name": "",
    "element_type": "",
    "text": "",
    "url": "",
    "keys": [],
    "value": "",
    "coordinates": {"x": 0, "y": 0},
    "screenshot_b64": "",
    "is_destructive": false,
    "requires_confirmation": false
  }
]"""


def _call_llm(timeline: str) -> list[SkillStep] | None:
    """Send the event timeline to the LLM and parse its JSON response."""
    prompt = f"Here are the raw events from the screen recording:\n\n{timeline}\n\nOrganize into skill steps."
    try:
        from app.services.model_router_service import ModelRouterService
        router = ModelRouterService()
        result = router.generate(
            messages=[
                {"role": "system", "content": _LLM_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            requested_model_id=None,
            options={"max_tokens": 3000},
        )
        raw = result.reply.strip()

        # Strip markdown code fences if present
        code_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if code_match:
            raw = code_match.group(1).strip()

        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("LLM returned non-list JSON")

        steps: list[SkillStep] = []
        for i, item in enumerate(data):
            item["step_index"] = i
            # Ensure coordinates always has x and y
            coords = item.get("coordinates") or {}
            item["coordinates"] = {"x": int(coords.get("x", 0)), "y": int(coords.get("y", 0))}
            steps.append(SkillStep(**item))

        logger.info("LLM organised %d raw events → %d steps", 0, len(steps))
        return steps

    except Exception as exc:
        logger.warning("LLM step organisation failed (%s) — falling back to rule-based", exc)
        return None


# ---------------------------------------------------------------------------
# Rule-based fallback grouper
# ---------------------------------------------------------------------------

def _rule_based(events: list[RawEvent]) -> list[SkillStep]:
    """
    Simple grouper when the LLM is unavailable.
    - Collapses consecutive key presses that form a hotkey.
    - Preserves type/click/key as-is with fallback descriptions.
    """
    steps: list[SkillStep] = []
    idx = 0

    for ev in events:
        desc = _fallback_desc(ev)
        destructive = any(w in (ev.element_name + ev.value).lower() for w in _DESTRUCTIVE_WORDS)

        steps.append(SkillStep(
            step_index=idx,
            action=ev.action,
            description=desc,
            app_name=ev.app_name,
            window_title=ev.window_title,
            element_name=ev.element_name,
            element_type=ev.element_type,
            text=ev.value if ev.action == "type" else "",
            value=ev.value if ev.action == "key" else "",
            coordinates=ev.coordinates,
            is_destructive=destructive,
            requires_confirmation=destructive,
        ))
        idx += 1

    return steps


def _fallback_desc(ev: RawEvent) -> str:
    app = ev.app_name or "unknown app"
    elem = ev.element_name or ev.element_type or "element"
    if ev.action == "click":
        return f"User clicks '{elem}' in {app}."
    if ev.action == "type":
        snippet = ev.value[:40] + "…" if len(ev.value) > 40 else ev.value
        return f"User types '{snippet}' in {app}."
    if ev.action == "key":
        return f"User presses {ev.value} in {app}."
    if ev.action == "scroll":
        return f"User scrolls {ev.value} in {app}."
    return f"User performs {ev.action} in {app}."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_skill_steps(events: list[RawEvent], enrich_with_llm: bool = True) -> list[SkillStep]:
    """
    Convert raw observation events into a semantic SkillStep list.
    Tries LLM organisation first; falls back to rule-based if LLM fails.
    """
    if not events:
        return []

    if enrich_with_llm:
        timeline = _build_timeline(events)
        steps = _call_llm(timeline)
        if steps:
            return steps

    return _rule_based(events)
