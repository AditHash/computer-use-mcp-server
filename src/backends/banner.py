"""Non-activating, topmost local stop control on its owned Windows GUI thread."""
import sys
import threading
import time
import uuid

from src.core.errors import ComputerError

from .desktop_session import require_interactive_session


class EmergencyBanner:
    def __init__(self, stop):
        self.stop = stop
        self.closed = threading.Event()
        self.ready = threading.Event()
        self.failed = False
        self.thread = None
        self._window_handle = None

    def start(self):
        self.stop.check()
        if sys.platform != 'win32':
            raise ComputerError('UNSUPPORTED', 'Interactive automation requires the local Windows stop control.')
        require_interactive_session()
        if self.closed.is_set():
            raise ComputerError('CANCELLED', 'The local stop control was closed.')
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, name='operator-stop-banner', daemon=True)
            self.thread.start()
        if not self.ready.wait(3) or self.failed or not self.thread.is_alive():
            self.stop.stop()
            raise ComputerError('BACKEND_UNAVAILABLE', 'The local emergency-stop control could not be shown.')

    def _run(self):
        import pywintypes
        import win32api
        import win32con
        import win32gui

        from .physical import physical_pixels
        handle = label = button = None
        instance = win32api.GetModuleHandle(None)
        class_name = 'ComputerUseStop_' + uuid.uuid4().hex

        def stopped():
            self.stop.stop()
            if label and win32gui.IsWindow(label):
                win32gui.SetWindowText(label, 'STOPPED - restart server to resume')
            if button and win32gui.IsWindow(button):
                win32gui.EnableWindow(button, False)

        def procedure(window, message, wparam, lparam):
            if message == win32con.WM_CLOSE or (message == win32con.WM_COMMAND and win32api.LOWORD(wparam) == 1):
                stopped()
                return 0
            return win32gui.DefWindowProc(window, message, wparam, lparam)

        try:
            with physical_pixels():
                wc = win32gui.WNDCLASS()
                wc.hInstance = instance
                wc.lpszClassName = class_name
                wc.lpfnWndProc = procedure
                wc.hbrBackground = win32con.COLOR_BTNFACE + 1
                wc.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
                win32gui.RegisterClass(wc)
                handle = win32gui.CreateWindowEx(
                    win32con.WS_EX_TOPMOST | win32con.WS_EX_NOACTIVATE | win32con.WS_EX_TOOLWINDOW,
                    class_name, 'Computer-use automation', win32con.WS_CAPTION | win32con.WS_SYSMENU,
                    max(0, win32api.GetSystemMetrics(0) - 380), 20, 360, 110, 0, 0, instance, None)
                label = win32gui.CreateWindowEx(0, 'STATIC', 'Automation enabled for allowed controls',
                    win32con.WS_CHILD | win32con.WS_VISIBLE, 10, 8, 335, 22, handle, 2, instance, None)
                button = win32gui.CreateWindowEx(0, 'BUTTON', 'STOP AUTOMATION',
                    win32con.WS_CHILD | win32con.WS_VISIBLE | win32con.BS_PUSHBUTTON,
                    10, 34, 335, 32, handle, 1, instance, None)
                win32gui.ShowWindow(handle, win32con.SW_SHOWNOACTIVATE)
                win32gui.SetWindowPos(handle, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
                self._window_handle = handle
                self.ready.set()
                while not self.closed.is_set() and win32gui.IsWindow(handle):
                    win32gui.PumpWaitingMessages()
                    if self.stop.event.is_set():
                        stopped()
                    time.sleep(0.03)
        except (pywintypes.error, OSError):
            self.failed = True
            self.stop.stop()
            self.ready.set()
        finally:
            if not self.closed.is_set():
                self.stop.stop()
            if handle and win32gui.IsWindow(handle):
                win32gui.DestroyWindow(handle)
            try:
                win32gui.UnregisterClass(class_name, instance)
            except pywintypes.error:
                self.failed = True

    def close(self):
        self.closed.set()
        if self.thread:
            self.thread.join(timeout=2)
            if self.thread.is_alive():
                raise ComputerError('TIMEOUT', 'The local stop control did not shut down.')
