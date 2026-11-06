"""Never operate across the Windows input/secure-desktop boundary."""
from src.core.errors import ComputerError


def require_interactive_session() -> None:
    import pywintypes
    import win32con
    import win32service
    desktop = None
    try:
        desktop = win32service.OpenInputDesktop(0, False, win32con.DESKTOP_READOBJECTS)
        name = win32service.GetUserObjectInformation(desktop, win32con.UOI_NAME)
        if name.casefold() != 'default':
            raise ComputerError('OS_PERMISSION_BOUNDARY', 'The interactive desktop is locked or unavailable.')
    except pywintypes.error:
        raise ComputerError('OS_PERMISSION_BOUNDARY', 'The interactive desktop is locked or unavailable.') from None
    finally:
        if desktop is not None:
            desktop.CloseDesktop()
