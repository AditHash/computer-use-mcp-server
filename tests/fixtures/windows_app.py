"""Disposable native controls for opt-in Windows acceptance; no file/network I/O."""
import json
import os

import win32api
import win32con
import win32gui

CLASS = 'MCPAcceptanceFixture'
TITLE = 'MCP controlled acceptance fixture'
children = {}
count = 0


def procedure(handle, message, wparam, lparam):
    global count
    if (message == win32con.WM_COMMAND and win32api.LOWORD(wparam) == 101
            and win32api.HIWORD(wparam) == win32con.BN_CLICKED):
        count += 1
        win32gui.SetWindowText(children['status'], f'Count {count}')
        return 0
    if message == win32con.WM_DESTROY:
        win32gui.PostQuitMessage(0)
        return 0
    if message == win32con.WM_APP + 10:
        # Independent test verification, from inside the control's own process.
        # Password contents are deliberately never included in this channel.
        print(json.dumps({'name': win32gui.GetWindowText(children['name']), 'count': count}), flush=True)
        return 0
    return win32gui.DefWindowProc(handle, message, wparam, lparam)


instance = win32api.GetModuleHandle(None)
window_class = win32gui.WNDCLASS()
window_class.hInstance = instance
window_class.lpszClassName = CLASS
window_class.lpfnWndProc = procedure
window_class.hbrBackground = win32con.COLOR_WINDOW + 1
window_class.hCursor = win32gui.LoadCursor(0, win32con.IDC_ARROW)
win32gui.RegisterClass(window_class)
window = win32gui.CreateWindowEx(0, CLASS, TITLE, win32con.WS_OVERLAPPEDWINDOW,
                                60, 120, 560, 500, 0, 0, instance, None)


def child(kind, text, number, x, y, width, height, extra=0):
    return win32gui.CreateWindowEx(0, kind, text, win32con.WS_CHILD | win32con.WS_VISIBLE | extra,
                                  x, y, width, height, window, number, instance, None)


children['increment'] = child('BUTTON', 'Increment', 101, 20, 20, 140, 32, win32con.WS_TABSTOP)
children['name_label'] = child('STATIC', 'Name', 102, 20, 70, 100, 24)
children['name'] = child('EDIT', '', 103, 130, 70, 240, 24, win32con.WS_BORDER | win32con.WS_TABSTOP)
children['password_label'] = child('STATIC', 'Password', 104, 20, 110, 100, 24)
children['password'] = child('EDIT', 'fixture-private-value', 105, 130, 110, 240, 24,
                             win32con.ES_PASSWORD | win32con.WS_BORDER | win32con.WS_TABSTOP)
children['status'] = child('STATIC', 'Count 0', 106, 20, 150, 180, 24)
children['protected'] = child('BUTTON', 'Delete everything', 107, 20, 190, 160, 32)
children['list_label'] = child('STATIC', 'Items', 108, 20, 240, 80, 24)
children['list'] = child('LISTBOX', '', 109, 130, 240, 240, 100,
                        win32con.WS_VSCROLL | win32con.WS_BORDER | win32con.WS_TABSTOP)
for index in range(100):
    win32gui.SendMessage(children['list'], win32con.LB_ADDSTRING, 0, f'Fixture item {index}')
win32gui.ShowWindow(window, win32con.SW_SHOWNOACTIVATE)
win32gui.UpdateWindow(window)
print(json.dumps({'handle': window, 'process_id': os.getpid(), 'class': CLASS,
                  'title': TITLE, 'children': children}), flush=True)
win32gui.PumpMessages()
