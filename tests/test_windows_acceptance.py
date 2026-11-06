"""Opt-in live tests operating only on our owned disposable Win32 fixture."""
import asyncio
import io
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import psutil
import pytest
from PIL import Image

from src.backends.banner import EmergencyBanner
from src.backends.worker import WindowsWorker
from src.core.errors import ComputerError
from src.core.operator import OperatorPolicy
from src.core.policy import normalize_executable
from src.core.runtime import ComputerRuntime
from src.core.stop import StopState
from src.core.targets import WindowRecord
from src.tools.targets import registry

pytestmark = [pytest.mark.windows, pytest.mark.skipif(
    sys.platform != 'win32' or os.environ.get('COMPUTER_USE_RUN_WINDOWS_TESTS') != '1',
    reason='Set COMPUTER_USE_RUN_WINDOWS_TESTS=1 in an interactive Windows session.')]


class Source:
    def __init__(self, policy):
        self.policy = policy
    def load(self):
        return self.policy


@pytest.fixture
def native_fixture():
    import win32con
    import win32gui
    import win32process
    process = subprocess.Popen([sys.executable, '-u', str(Path(__file__).parent / 'fixtures/windows_app.py')],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8',
        creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        ready = json.loads(process.stdout.readline())
        # Windows venv python.exe may be a redirector with a distinct child PID.
        descendants = {child.pid for child in psutil.Process(process.pid).children(recursive=True)}
        assert ready['process_id'] == process.pid or ready['process_id'] in descendants
        assert win32process.GetWindowThreadProcessId(ready['handle'])[1] == ready['process_id']
        owner = psutil.Process(ready['process_id'])
        record = WindowRecord(ready['handle'], owner.pid, owner.create_time(),
            normalize_executable(owner.exe()), ready['class'], ready['title'])
        ready['_process'] = process
        yield ready, record
    finally:
        if process.poll() is None:
            if 'ready' in locals() and win32gui.IsWindow(ready['handle']):
                win32gui.PostMessage(ready['handle'], win32con.WM_CLOSE, 0, 0)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()


async def test_native_observation_invoke_type_protection_and_window_capture(native_fixture):
    import win32gui
    ready, window = native_fixture
    policy = OperatorPolicy.model_validate({
        'desktop': {'allowed_apps': [window.executable]},
        'permissions': {'interact': True, 'screenshot': True},
        'grants': [
            {'target': window.executable, 'role': 'Button', 'name': 'Increment', 'actions': ['click']},
            {'target': window.executable, 'role': 'Edit', 'name': 'Name', 'actions': ['type']},
        ],
    })
    runtime = ComputerRuntime(Source(policy))
    target = registry.refresh([window], policy.apps())[0]
    try:
        observation = await runtime.observe(target['target_id'])
        assert 'fixture-private-value' not in observation.model_dump_json()
        button = next(item for item in observation.elements if item.name == 'Increment' and item.role == 'Button')
        result = await runtime.action(target['target_id'], observation.snapshot_id, button.ref, 'click')
        assert result.status == 'executed_unverified'
        # UIA Invoke may enqueue its native command and return before dispatch.
        for _ in range(40):
            if win32gui.GetWindowText(ready['children']['status']) == 'Count 1':
                break
            await asyncio.sleep(0.05)
        assert win32gui.GetWindowText(ready['children']['status']) == 'Count 1'
        observation = await runtime.observe(target['target_id'])
        field = next(item for item in observation.elements if item.name == 'Name' and item.role == 'Edit')
        result = await runtime.action(target['target_id'], observation.snapshot_id, field.ref, 'type', text='Native fixture input')
        assert result.status == 'verified'
        import win32con
        win32gui.PostMessage(window.handle, win32con.WM_APP + 10, 0, 0)
        state = json.loads(await asyncio.wait_for(asyncio.to_thread(ready['_process'].stdout.readline), 5))
        assert state['name'] == 'Native fixture input'
        observation = await runtime.observe(target['target_id'])
        assert any(item.protected for item in observation.elements)
        password = next(item for item in observation.elements if item.protected and item.role == 'Edit')
        with pytest.raises(ComputerError, match='PERMISSION_DENIED'):
            await runtime.action(target['target_id'], observation.snapshot_id, password.ref, 'type', text='must-not-enter')
        observation = await runtime.observe(target['target_id'])
        png, metadata = await runtime.screenshot(target['target_id'], observation.snapshot_id, max_dimension=400)
        assert png[:8] == b'\x89PNG\r\n\x1a\n'
        assert metadata['image_width'] <= 400
        assert metadata['coordinate_space'] == 'screen_physical_pixels'
        with Image.open(io.BytesIO(png)) as captured:
            assert any(low < high for low, high in captured.getextrema()), 'Known fixture capture must not be blank'
    finally:
        await runtime.close()
        registry.refresh([], frozenset())


async def test_native_edit_change_rejects_old_refs(native_fixture):
    import win32con
    import win32gui
    ready, window = native_fixture
    policy = OperatorPolicy.model_validate({'desktop': {'allowed_apps': [window.executable]},
        'permissions': {'interact': True}, 'grants': [
            {'target': window.executable, 'role': 'Edit', 'name': 'Name', 'actions': ['type']} ]})
    runtime = ComputerRuntime(Source(policy))
    target = registry.refresh([window], policy.apps())[0]
    try:
        observation = await runtime.observe(target['target_id'])
        field = next(item for item in observation.elements if item.name == 'Name' and item.role == 'Edit')
        win32gui.SendMessage(ready['children']['name'], win32con.WM_SETTEXT, 0, 'External fixture change')
        with pytest.raises(ComputerError, match='STALE_REF'):
            await runtime.action(target['target_id'], observation.snapshot_id, field.ref, 'type', text='must-not-overwrite')
    finally:
        await runtime.close()
        registry.refresh([], frozenset())


async def test_stop_banner_is_topmost_nonactivating_and_close_latches_stop():
    import win32con
    import win32gui
    import win32process
    stop = StopState()
    banner = EmergencyBanner(stop)
    try:
        await asyncio.to_thread(banner.start)
        handle = banner._window_handle
        assert win32process.GetWindowThreadProcessId(handle)[1] == os.getpid()
        style = win32gui.GetWindowLong(handle, win32con.GWL_EXSTYLE)
        assert style & win32con.WS_EX_TOPMOST
        assert style & win32con.WS_EX_NOACTIVATE
        win32gui.PostMessage(handle, win32con.WM_CLOSE, 0, 0)
        assert await asyncio.to_thread(stop.event.wait, 2)
        assert win32gui.IsWindow(handle), 'Operator close must stop, not dismiss, the safety control'
        with pytest.raises(ComputerError, match='CANCELLED'):
            stop.check()
    finally:
        await asyncio.to_thread(banner.close)
    assert not banner.thread.is_alive()


async def test_worker_cancellation_poisoning_prevents_a_delayed_side_effect():
    stop = StopState()
    worker = await WindowsWorker.create(stop)
    entered, released = threading.Event(), threading.Event()
    effects = []
    def callback():
        entered.set()
        released.wait(3)
        stop.check()
        effects.append('must-not-execute')
    try:
        task = asyncio.create_task(worker.call(callback))
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert worker.poisoned and stop.event.is_set()
        released.set()
    finally:
        released.set()
        await asyncio.to_thread(worker.close)
    assert effects == []


async def test_native_focus_keys_scroll_and_guarded_physical_primitives(native_fixture):
    import win32api
    import win32con
    import win32gui
    ready, window = native_fixture
    policy = OperatorPolicy.model_validate({
        'desktop': {'allowed_apps': [window.executable]},
        'permissions': {'interact': True, 'screenshot': True, 'focus': True, 'fallback': True},
        'grants': [
            {'target': window.executable, 'role': 'Window', 'name': window.title, 'actions': ['focus']},
            {'target': window.executable, 'role': 'Button', 'name': 'Increment', 'actions': ['double_click']},
            {'target': window.executable, 'role': 'Edit', 'name': 'Name', 'actions': ['type', 'press_keys', 'drag']},
            {'target': window.executable, 'role': 'List', 'name': 'Items', 'actions': ['scroll', 'drag']},
        ],
    })
    runtime = ComputerRuntime(Source(policy))
    target_id = registry.refresh([window], policy.apps())[0]['target_id']
    try:
        observation = await runtime.observe(target_id)
        root = next(item for item in observation.elements if item.role == 'Window' and item.name == window.title)
        if os.environ.get('COMPUTER_USE_WAIT_FOR_FOCUS') == '1':
            print('Click the title bar of MCP controlled acceptance fixture and leave it focused until it closes.', flush=True)
            for _ in range(900):
                if win32gui.GetForegroundWindow() == window.handle:
                    break
                await asyncio.sleep(0.1)
            if win32gui.GetForegroundWindow() != window.handle:
                pytest.fail('Manual fixture focus was not supplied within 90 seconds.')
            observation = await runtime.observe(target_id)
            root = next(item for item in observation.elements if item.role == 'Window' and item.name == window.title)
        try:
            focused = await runtime.action(target_id, observation.snapshot_id, root.ref, 'focus')
        except ComputerError as error:
            if error.code == 'TARGET_NOT_FOREGROUND':
                pytest.skip('Windows foreground policy blocked focus; rerun with COMPUTER_USE_WAIT_FOR_FOCUS=1 and focus the fixture.')
            raise
        assert focused.status == 'verified'
        assert win32gui.GetForegroundWindow() == window.handle
        observation = await runtime.observe(target_id)
        field = next(item for item in observation.elements if item.role == 'Edit' and item.name == 'Name')
        await runtime.action(target_id, observation.snapshot_id, field.ref, 'type', text='navigation fixture')
        observation = await runtime.observe(target_id)
        field = next(item for item in observation.elements if item.role == 'Edit' and item.name == 'Name')
        await runtime.action(target_id, observation.snapshot_id, field.ref, 'press_keys', keys=['HOME', 'ARROWRIGHT'])
        selection = win32gui.SendMessage(ready['children']['name'], win32con.EM_GETSEL, 0, 0)
        assert win32api.LOWORD(selection) == win32api.HIWORD(selection) == 1
        observation = await runtime.observe(target_id)
        items = next(item for item in observation.elements if item.role == 'List' and item.name == 'Items')
        await runtime.action(target_id, observation.snapshot_id, items.ref, 'scroll', direction='down', amount=2)
        for _ in range(30):
            if win32gui.SendMessage(ready['children']['list'], win32con.LB_GETTOPINDEX, 0, 0) > 0:
                break
            await asyncio.sleep(0.05)
        assert win32gui.SendMessage(ready['children']['list'], win32con.LB_GETTOPINDEX, 0, 0) > 0
        observation = await runtime.observe(target_id)
        button = next(item for item in observation.elements if item.role == 'Button' and item.name == 'Increment')
        _, metadata = await runtime.screenshot(target_id, observation.snapshot_id, max_dimension=400)
        point_x = button.rect.left + button.rect.width // 2
        point_y = button.rect.top + button.rect.height // 2
        x = int((point_x - metadata['source']['left']) * metadata['scale_x'])
        y = int((point_y - metadata['source']['top']) * metadata['scale_y'])
        moved = await runtime.move(target_id, observation.snapshot_id, metadata['map_id'], x, y, duration=0.2)
        assert moved.observation_invalidated
        observation = await runtime.observe(target_id)
        button = next(item for item in observation.elements if item.role == 'Button' and item.name == 'Increment')
        await runtime.action(target_id, observation.snapshot_id, button.ref, 'double_click')
        assert int(win32gui.GetWindowText(ready['children']['status']).split()[-1]) >= 1
        observation = await runtime.observe(target_id)
        field = next(item for item in observation.elements if item.role == 'Edit' and item.name == 'Name')
        items = next(item for item in observation.elements if item.role == 'List' and item.name == 'Items')
        await runtime.action(target_id, observation.snapshot_id, field.ref, 'drag', destination_ref=items.ref, duration=0.2)
        assert not win32api.GetAsyncKeyState(win32con.VK_LBUTTON) & 0x8000
    finally:
        await runtime.close()
        registry.refresh([], frozenset())
