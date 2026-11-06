"""Read top-level Windows metadata, checking application identity before titles."""

import sys

import psutil

from src.core.policy import normalize_executable
from src.core.targets import WindowRecord

from .desktop_session import require_interactive_session


class UnsupportedPlatformError(Exception):
    pass


class BackendUnavailableError(Exception):
    pass


def foreground_window_handle() -> int:
    """Read the foreground handle for internal matching; never expose it to MCP."""
    if sys.platform != "win32":
        raise UnsupportedPlatformError
    require_interactive_session()
    try:
        import pywintypes
        import win32gui
    except ImportError:
        raise BackendUnavailableError from None
    try:
        return win32gui.GetForegroundWindow() or 0
    except (pywintypes.error, OSError):
        raise BackendUnavailableError from None


def discover_windows(allowed: frozenset[str]) -> list[WindowRecord]:
    """Enumerate visible, titled windows from explicitly allowed executables."""
    if sys.platform != "win32":
        raise UnsupportedPlatformError
    require_interactive_session()

    # Discovery uses Win32 metadata, not UIA or COM. Import only on Windows.
    try:
        import pywintypes
        import win32gui
        import win32process
    except ImportError:
        raise BackendUnavailableError from None

    windows: list[WindowRecord] = []

    def visit(handle, _):
        try:
            if not win32gui.IsWindowVisible(handle):
                return True
            _, process_id = win32process.GetWindowThreadProcessId(handle)
            if not process_id:
                return True
            process = psutil.Process(process_id)
            started = process.create_time()
            executable = normalize_executable(process.exe())
            if executable not in allowed:
                return True
            title = win32gui.GetWindowText(handle).strip()
            if not title:
                return True
            window_class = win32gui.GetClassName(handle)
            _, current_pid = win32process.GetWindowThreadProcessId(handle)
            if current_pid != process_id or not process.is_running():
                return True
            windows.append(WindowRecord(handle, process_id, started, executable, window_class, title[:200]))
        except (psutil.Error, pywintypes.error, OSError):
            # Closed, inaccessible, or replaced windows are omitted, not retried.
            pass
        return True

    try:
        win32gui.EnumWindows(visit, None)
    except (pywintypes.error, OSError):
        raise BackendUnavailableError from None
    return windows
