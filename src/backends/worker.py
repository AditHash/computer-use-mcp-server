"""One owned MTA/COM thread for serialized native Windows operations."""
import asyncio
import concurrent.futures
import queue
import sys
import threading

from src.core.errors import ComputerError


class WindowsWorker:
    def __init__(self, stop, wait=True):
        if sys.platform != 'win32':
            raise ComputerError('UNSUPPORTED', 'Native accessibility requires Windows.')
        # Importing comtypes initializes its main-thread apartment. Worker calls
        # have their own balanced MTA initialization and never share wrappers.
        import comtypes
        self.comtypes = comtypes
        self.stop = stop
        self.queue = queue.Queue(maxsize=32)
        self.poisoned = False
        self.ready = threading.Event()
        self.start_error = False
        self.thread = threading.Thread(target=self._run, name='windows-uia-worker', daemon=True)
        self.thread.start()
        if wait and (not self.ready.wait(5) or self.start_error):
            self.poisoned = True
            raise ComputerError('BACKEND_UNAVAILABLE', 'Windows accessibility could not be initialized.')

    @classmethod
    async def create(cls, stop):
        worker = cls(stop, wait=False)
        ready = await asyncio.to_thread(worker.ready.wait, 5)
        if not ready or worker.start_error:
            worker.poisoned = True
            await asyncio.to_thread(worker.close)
            raise ComputerError('BACKEND_UNAVAILABLE', 'Windows accessibility could not be initialized.')
        return worker

    def _run(self):
        initialized = False
        try:
            self.comtypes.CoInitializeEx(0)
            initialized = True
            from comtypes.client import CreateObject
            from comtypes.gen import UIAutomationClient
            from pywinauto.uia_defines import IUIA
            # Drop singleton pointers from a previous, already closed worker.
            IUIA._instances.pop(IUIA, None)
            interface = CreateObject(UIAutomationClient.CUIAutomation8, interface=UIAutomationClient.IUIAutomation2)
            interface.ConnectionTimeout = 1000
            interface.TransactionTimeout = 1000
            IUIA().iuia = interface.QueryInterface(UIAutomationClient.IUIAutomation)
            IUIA().true_condition = IUIA().iuia.CreateTrueCondition()
            IUIA().root = IUIA().iuia.GetRootElement()
            IUIA().get_focused_element = IUIA().iuia.GetFocusedElement
            self.ready.set()
            while True:
                item = self.queue.get()
                if item is None:
                    break
                future, function, arguments = item
                if future.set_running_or_notify_cancel():
                    try:
                        self.stop.check()
                        result = function(*arguments)
                    except BaseException as error:  # noqa: BLE001 - transfer every worker failure to its owning future.
                        future.set_exception(error)
                    else:
                        future.set_result(result)
        except BaseException:  # noqa: BLE001 - thread initialization must always signal readiness failure.
            self.start_error = True
            self.ready.set()
        finally:
            if initialized:
                self.comtypes.CoUninitialize()

    async def call(self, function, *arguments, timeout=5):
        if self.poisoned or not self.thread.is_alive():
            raise ComputerError('BACKEND_UNAVAILABLE', 'Restart the server to restore the native worker.')
        self.stop.check()
        future = concurrent.futures.Future()
        try:
            self.queue.put_nowait((future, function, arguments))
        except queue.Full:
            raise ComputerError('TIMEOUT', 'The native request queue is full.') from None
        try:
            return await asyncio.wait_for(asyncio.wrap_future(future), timeout)
        except TimeoutError:
            self.poisoned = True
            self.stop.stop()
            raise ComputerError('TIMEOUT', 'Native automation timed out and was stopped; restart the server.') from None
        except asyncio.CancelledError:
            future.cancel()
            self.poisoned = True
            self.stop.stop()
            raise
        except ComputerError:
            raise
        except Exception:  # noqa: BLE001 - sanitize exceptions transferred from third-party native providers.
            raise ComputerError('BACKEND_UNAVAILABLE', 'The native operation could not be completed.') from None

    def close(self):
        self.poisoned = True
        while True:
            try:
                item = self.queue.get_nowait()
                if item:
                    item[0].cancel()
            except queue.Empty:
                break
        self.queue.put_nowait(None)
        self.thread.join(timeout=2)
