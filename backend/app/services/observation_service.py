"""
Observation service — dual-track recording of user actions.

Track A (Structural): pynput listens globally; pywinauto reads the Windows
                      accessibility tree to identify app, window, element.
Track B (Visual):     Pillow screenshots each action moment.

The merged RawEvent list is handed off to skill_file_generator_service.
"""

import base64
import io
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional heavy imports — gracefully degrade if libraries not installed
# ---------------------------------------------------------------------------
try:
    import pywinauto  # type: ignore
    from pywinauto import Desktop  # type: ignore
    _PYWINAUTO_AVAILABLE = True
except Exception as _e:
    _PYWINAUTO_AVAILABLE = False
    logger.warning("pywinauto unavailable (%s) — accessibility capture disabled", _e)

try:
    from pynput import mouse as pynput_mouse, keyboard as pynput_keyboard  # type: ignore
    _PYNPUT_AVAILABLE = True
except Exception as _e:
    _PYNPUT_AVAILABLE = False
    logger.warning("pynput unavailable (%s) — global input capture disabled", _e)

try:
    from PIL import ImageGrab  # type: ignore
    _PIL_AVAILABLE = True
except Exception as _e:
    _PIL_AVAILABLE = False
    logger.warning("Pillow unavailable (%s) — screenshots disabled", _e)

# ---------------------------------------------------------------------------
# Process-name → friendly-name mapping for common apps
# ---------------------------------------------------------------------------
_PROCESS_NAME_MAP: dict[str, str] = {
    "msedge": "Microsoft Edge",
    "chrome": "Google Chrome",
    "firefox": "Firefox",
    "notepad": "Notepad",
    "notepad++": "Notepad++",
    "explorer": "File Explorer",
    "code": "VS Code",
    "devenv": "Visual Studio",
    "winword": "Microsoft Word",
    "excel": "Microsoft Excel",
    "powerpnt": "PowerPoint",
    "outlook": "Outlook",
    "teams": "Microsoft Teams",
    "slack": "Slack",
    "discord": "Discord",
    "cmd": "Command Prompt",
    "powershell": "PowerShell",
    "windowsterminal": "Windows Terminal",
    "python": "Python",
}

# Windows (by title substring) that belong to MindOS itself — filter these out
_MINDOS_WINDOW_HINTS = {"localhost", "mindos", "127.0.0.1", "vite"}


@dataclass
class RawEvent:
    """One captured user action before LLM enrichment."""
    action: str                        # click | type | key | scroll | focus
    timestamp: float = field(default_factory=time.time)
    app_name: str = ""
    window_title: str = ""
    element_type: str = ""
    element_name: str = ""
    value: str = ""                    # typed text or key name
    coordinates: dict = field(default_factory=dict)
    screenshot_b64: str = ""           # base64-encoded PNG


@dataclass
class RecordingSession:
    session_id: str
    events: list[RawEvent] = field(default_factory=list)
    active: bool = True
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _mouse_listener: Optional[object] = None
    _keyboard_listener: Optional[object] = None
    _pending_chars: list[str] = field(default_factory=list)
    _last_type_ts: float = 0.0


# Module-level singleton — one recording session at a time
_active_session: Optional[RecordingSession] = None
_session_lock = threading.Lock()

# Minimum ms between captured click events to avoid duplicates
_CLICK_DEBOUNCE_MS = 200
_last_click_ts: float = 0.0


def _get_window_info() -> tuple[str, str]:
    """Return (app_name, window_title) of the foreground window.

    Uses raw Win32 ctypes calls — no COM initialization required, safe to call
    from pynput's background listener threads.
    """
    try:
        import ctypes
        import ctypes.wintypes as wintypes

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return ("", "")

        # Window title
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd) + 1
        buf = ctypes.create_unicode_buffer(length)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length)
        title = buf.value or ""

        # Process ID
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        # App name from psutil
        app = ""
        try:
            import psutil  # type: ignore
            proc = psutil.Process(pid.value)
            raw = proc.name().lower().replace(".exe", "").strip()
            app = _PROCESS_NAME_MAP.get(raw, raw.title())
        except Exception:
            pass

        # Fallback: extract from title "Page – App Name"
        if not app and " - " in title:
            app = title.split(" - ")[-1].strip()

        return (app, title)
    except Exception:
        return ("", "")


def _is_mindos_window(app_name: str, window_title: str) -> bool:
    """True if this window belongs to the MindOS frontend (should be filtered out)."""
    combined = (app_name + " " + window_title).lower()
    return any(hint in combined for hint in _MINDOS_WINDOW_HINTS)


def _get_element_at(x: int, y: int) -> tuple[str, str]:
    """Return (element_type, element_name) of the UI element under (x, y).

    Initialises COM on the caller thread (needed when called from pynput threads).
    """
    if not _PYWINAUTO_AVAILABLE:
        return ("", "")
    try:
        # CoInitialize so COM works on this background thread
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 0)
        try:
            desktop = Desktop(backend="uia")
            elem = desktop.from_point(x, y)
            if elem is None:
                return ("", "")
            etype = elem.friendly_class_name() or ""
            ename = elem.window_text() or ""
            return (etype, ename)
        finally:
            ctypes.windll.ole32.CoUninitialize()
    except Exception:
        return ("", "")


def _take_screenshot_b64() -> str:
    """Capture the full screen and return as base64 PNG string."""
    if not _PIL_AVAILABLE:
        return ""
    try:
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return ""


def _flush_pending_type(session: RecordingSession) -> None:
    """Consolidate buffered keystrokes into a single 'type' event."""
    with session._lock:
        if not session._pending_chars:
            return
        text = "".join(session._pending_chars)
        session._pending_chars.clear()
        if not text.strip():
            return
        app, window = _get_window_info()
        event = RawEvent(
            action="type",
            app_name=app,
            window_title=window,
            value=text,
            screenshot_b64=_take_screenshot_b64(),
        )
        session.events.append(event)
        logger.debug("Captured type event: %r in %s / %s", text, app, window)


def start_recording() -> str:
    """Begin a new observation session. Returns the session_id."""
    global _active_session

    if not _PYNPUT_AVAILABLE:
        raise RuntimeError("pynput is required for recording. Run: pip install pynput pywinauto pillow pyautogui psutil")

    with _session_lock:
        if _active_session and _active_session.active:
            return _active_session.session_id  # already recording

        session = RecordingSession(session_id=str(uuid4()))
        _active_session = session

    def on_click(x: int, y: int, button, pressed: bool) -> None:
        global _last_click_ts
        if not pressed:
            return
        now = time.time()
        if (now - _last_click_ts) * 1000 < _CLICK_DEBOUNCE_MS:
            return
        _last_click_ts = now

        # Flush any pending typed characters first
        _flush_pending_type(session)

        app, window = _get_window_info()

        # Skip clicks on MindOS itself
        if _is_mindos_window(app, window):
            logger.debug("Skipped MindOS click at (%d, %d)", x, y)
            return

        screenshot = _take_screenshot_b64()
        etype, ename = _get_element_at(x, y)

        event = RawEvent(
            action="click",
            app_name=app,
            window_title=window,
            element_type=etype,
            element_name=ename,
            coordinates={"x": x, "y": y},
            screenshot_b64=screenshot,
        )
        with session._lock:
            session.events.append(event)
        logger.debug("Captured click at (%d, %d) on %s / %s [%s]", x, y, app, window, ename)

    def on_scroll(x: int, y: int, dx: int, dy: int) -> None:
        app, window = _get_window_info()
        if _is_mindos_window(app, window):
            return
        direction = "down" if dy < 0 else "up"
        event = RawEvent(
            action="scroll",
            app_name=app,
            window_title=window,
            value=direction,
            coordinates={"x": x, "y": y},
        )
        with session._lock:
            session.events.append(event)

    def on_press(key) -> None:
        try:
            # Printable character — buffer it for consolidation
            ch = key.char
            if ch is not None:
                with session._lock:
                    session._pending_chars.append(ch)
                    session._last_type_ts = time.time()
                return
        except AttributeError:
            pass

        # Space bar — treat as a typed character so words aren't split
        if _PYNPUT_AVAILABLE and key == pynput_keyboard.Key.space:
            with session._lock:
                session._pending_chars.append(" ")
                session._last_type_ts = time.time()
            return

        # Special key — flush buffered chars first, then record as key event
        _flush_pending_type(session)

        app, window = _get_window_info()
        if _is_mindos_window(app, window):
            return

        key_name = str(key).replace("Key.", "")
        event = RawEvent(
            action="key",
            app_name=app,
            window_title=window,
            value=key_name,
        )
        with session._lock:
            session.events.append(event)
        logger.debug("Captured key: %s in %s / %s", key_name, app, window)

    mouse_listener = pynput_mouse.Listener(on_click=on_click, on_scroll=on_scroll)
    keyboard_listener = pynput_keyboard.Listener(on_press=on_press)

    session._mouse_listener = mouse_listener
    session._keyboard_listener = keyboard_listener

    # Start listeners in a background thread with a hard timeout.
    # pynput's .start() internally waits for a Win32 message-loop to be ready;
    # on some systems this never completes — we must not block the HTTP handler.
    import concurrent.futures as _cf
    def _do_start():
        mouse_listener.start()
        keyboard_listener.start()

    with _cf.ThreadPoolExecutor(max_workers=1) as _pool:
        fut = _pool.submit(_do_start)
        try:
            fut.result(timeout=6.0)
        except _cf.TimeoutError:
            try:
                mouse_listener.stop()
                keyboard_listener.stop()
            except Exception:
                pass
            with _session_lock:
                _active_session = None
            raise RuntimeError(
                "Input listeners could not start within 6 seconds. "
                "Try running the backend as Administrator, or check that no "
                "security software is blocking global input hooks."
            )
        except Exception as exc:
            with _session_lock:
                _active_session = None
            raise RuntimeError(f"Input listener error: {exc}") from exc

    logger.info("Observation session %s started", session.session_id)
    return session.session_id


def stop_recording() -> tuple[str, list[RawEvent]]:
    """Stop the active recording session. Returns (session_id, events)."""
    global _active_session

    with _session_lock:
        session = _active_session
        if session is None or not session.active:
            raise RuntimeError("No active recording session")
        session.active = False
        _active_session = None

    # Flush any remaining typed characters
    _flush_pending_type(session)

    if session._mouse_listener:
        session._mouse_listener.stop()
    if session._keyboard_listener:
        session._keyboard_listener.stop()

    events = session.events

    # Re-index steps sequentially (in case any were filtered mid-session)
    for i, ev in enumerate(events):
        _ = i  # step_index assigned later in generator

    logger.info("Observation session %s stopped — %d events", session.session_id, len(events))
    return session.session_id, events


def is_recording() -> bool:
    return _active_session is not None and _active_session.active
