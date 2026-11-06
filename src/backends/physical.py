"""Bounded native capture and explicitly enabled physical-input fallback."""
import ctypes
import io
import time
from contextlib import contextmanager

from PIL import Image

from src.core.errors import ComputerError


@contextmanager
def physical_pixels():
    user32 = ctypes.windll.user32
    function = user32.SetThreadDpiAwarenessContext
    function.argtypes = [ctypes.c_void_p]
    function.restype = ctypes.c_void_p
    previous = function(ctypes.c_void_p(-4))
    if not previous:
        raise ComputerError('UNSUPPORTED', 'Per-thread DPI awareness is unavailable.')
    try:
        yield
    finally:
        function(ctypes.c_void_p(previous))


def window_bounds(handle):
    import win32gui
    with physical_pixels():
        left, top, right, bottom = win32gui.GetWindowRect(handle)
    if right <= left or bottom <= top:
        raise ComputerError('BACKEND_UNAVAILABLE', 'The window has no drawable bounds.')
    return {'left': left, 'top': top, 'width': right - left, 'height': bottom - top}


def capture_window(handle):
    import win32gui
    import win32ui
    if win32gui.IsIconic(handle) or not win32gui.IsWindowVisible(handle):
        raise ComputerError('UNSUPPORTED', 'Restore the allowed window before capturing it.')
    bounds = window_bounds(handle)
    if bounds['width'] * bounds['height'] > 16_000_000:
        raise ComputerError('OUT_OF_BOUNDS', 'Window capture exceeds the 16 megapixel limit.')
    window_dc = None
    source = memory = bitmap = None
    old_bitmap = None
    try:
        with physical_pixels():
            window_dc = win32gui.GetWindowDC(handle)
            source = win32ui.CreateDCFromHandle(window_dc)
            memory = source.CreateCompatibleDC()
            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(source, bounds['width'], bounds['height'])
            old_bitmap = memory.SelectObject(bitmap)
            print_window = ctypes.windll.user32.PrintWindow
            print_window.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
            print_window.restype = ctypes.c_int
            if not print_window(handle, memory.GetSafeHdc(), 2):
                raise ComputerError('BACKEND_UNAVAILABLE', 'This window does not support PrintWindow capture.')
            raw = bitmap.GetBitmapBits(True)
            image = Image.frombuffer('RGB', (bounds['width'], bounds['height']), raw, 'raw', 'BGRX', 0, 1)
            output = io.BytesIO()
            image.save(output, format='PNG')
            return output.getvalue(), bounds
    finally:
        if memory and old_bitmap:
            memory.SelectObject(old_bitmap)
        if bitmap:
            win32gui.DeleteObject(bitmap.GetHandle())
        if memory:
            memory.DeleteDC()
        if source:
            source.DeleteDC()
        if window_dc:
            win32gui.ReleaseDC(handle, window_dc)


def apply_input(handle, action, points, stop, duration=0.5, authorize=None):
    import pyautogui
    import win32api
    import win32con
    import win32gui
    import win32process
    if not pyautogui.FAILSAFE:
        raise ComputerError('PERMISSION_DENIED', 'PyAutoGUI fail-safe must remain enabled.')
    window_bounds(handle)

    def check(point=None, verify_cursor=False):
        stop.check()
        if authorize:
            authorize()
        if win32gui.GetForegroundWindow() != handle:
            raise ComputerError('TARGET_NOT_FOREGROUND', 'Foreground target changed; input aborted.')
        modifiers = (win32con.VK_CONTROL, win32con.VK_MENU, win32con.VK_SHIFT, win32con.VK_LWIN, win32con.VK_RWIN)
        if any(win32api.GetAsyncKeyState(key) & 0x8000 for key in modifiers):
            raise ComputerError('CANCELLED', 'A held human modifier interrupted physical input.')
        if point:
            current_bounds = window_bounds(handle)
            if not (current_bounds['left'] <= point[0] < current_bounds['left'] + current_bounds['width'] and
                    current_bounds['top'] <= point[1] < current_bounds['top'] + current_bounds['height']):
                raise ComputerError('OUT_OF_BOUNDS', 'Input coordinates must remain inside the allowed target.')
            hit = win32gui.WindowFromPoint(point)
            if (hit != handle and not win32gui.IsChild(handle, hit)) or (
                win32process.GetWindowThreadProcessId(hit)[1] != win32process.GetWindowThreadProcessId(handle)[1]):
                raise ComputerError('TARGET_NOT_FOREGROUND', 'The input point is covered by another target.')
            if verify_cursor:
                position = pyautogui.position()
                if abs(position.x - point[0]) > 3 or abs(position.y - point[1]) > 3:
                    raise ComputerError('CANCELLED', 'Human cursor movement interrupted input.')

    def move_bounded(destination, seconds):
        current = pyautogui.position()
        start = (current.x, current.y)
        bounds = window_bounds(handle)
        inside = bounds['left'] <= start[0] < bounds['left'] + bounds['width'] and bounds['top'] <= start[1] < bounds['top'] + bounds['height']
        steps = 5 if inside and seconds > 0 else 1
        previous = start
        for index in range(1, steps + 1):
            check()
            position = pyautogui.position()
            if abs(position.x - previous[0]) > 3 or abs(position.y - previous[1]) > 3:
                raise ComputerError('CANCELLED', 'Human cursor movement interrupted pointer motion.')
            point = (round(start[0] + (destination[0] - start[0]) * index / steps),
                     round(start[1] + (destination[1] - start[1]) * index / steps))
            check(point)
            pyautogui.moveTo(*point)
            check(point, verify_cursor=True)
            previous = point
            if steps > 1:
                time.sleep(min(seconds, 1) / steps)

    with physical_pixels():
        check()
        for point in points:
            check(point)
        pressed = False
        try:
            if win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000:
                raise ComputerError('CANCELLED', 'The human is already holding the mouse button.')
            if action in ('move', 'double_click'):
                move_bounded(points[0], duration)
                check(points[0], verify_cursor=True)
                if action == 'double_click':
                    for index in range(2):
                        check(points[0], verify_cursor=True)
                        pyautogui.click()
                        if index == 0:
                            time.sleep(0.05)
            elif action == 'drag':
                move_bounded(points[0], 0.1)
                check(points[0], verify_cursor=True)
                pyautogui.mouseDown()
                pressed = True
                last = points[0]
                for step in range(1, 6):
                    check(last, verify_cursor=True)
                    position = pyautogui.position()
                    if abs(position.x - last[0]) > 3 or abs(position.y - last[1]) > 3:
                        raise ComputerError('CANCELLED', 'Human cursor movement interrupted the drag.')
                    point = (round(points[0][0] + (points[1][0] - points[0][0]) * step / 5),
                             round(points[0][1] + (points[1][1] - points[0][1]) * step / 5))
                    check(point)
                    pyautogui.moveTo(*point)
                    last = point
                    time.sleep(min(duration, 1) / 5)
            else:
                raise ComputerError('UNSUPPORTED', 'Unsupported physical input action.')
        except pyautogui.FailSafeException:
            stop.stop()
            raise ComputerError('CANCELLED', 'PyAutoGUI emergency fail-safe stopped automation.') from None
        finally:
            if pressed:
                # Release even if fail-safe prevents another PyAutoGUI call.
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
