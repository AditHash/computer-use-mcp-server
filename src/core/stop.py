"""Local emergency stop and a non-dismissible operator banner."""
import asyncio
import threading
from contextlib import contextmanager

from .errors import ComputerError


class StopState:
    def __init__(self):
        self.event = threading.Event()
        self.tasks = set()
        self.lock = threading.Lock()
        self.callbacks = []

    def check(self):
        if self.event.is_set():
            raise ComputerError('CANCELLED', 'Automation is stopped. The operator must restart the server.')

    def stop(self):
        with self.lock:
            if self.event.is_set():
                return
            self.event.set()
            tasks = list(self.tasks)
            callbacks, self.callbacks = self.callbacks, []
        for loop, task in tasks:
            if not loop.is_closed():
                loop.call_soon_threadsafe(task.cancel)
        for callback in callbacks:
            callback()

    def on_stop(self, callback):
        with self.lock:
            if not self.event.is_set():
                self.callbacks.append(callback)
                return
        callback()

    @contextmanager
    def track(self):
        self.check()
        item = (asyncio.get_running_loop(), asyncio.current_task())
        with self.lock:
            self.tasks.add(item)
        try:
            self.check()
            yield
        finally:
            with self.lock:
                self.tasks.discard(item)
