"""Opaque, short-lived IDs for the latest allowed window discovery."""

import time
import uuid
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Literal, TypedDict

from .policy import normalize_executable


@dataclass(frozen=True)
class WindowRecord:
    handle: int
    process_id: int
    process_started: float
    executable: str
    window_class: str
    title: str

    @property
    def identity(self) -> tuple[int, int, float, str, str]:
        return (self.handle, self.process_id, self.process_started,
                normalize_executable(self.executable), self.window_class)


class TargetInfo(TypedDict):
    target_id: str
    name: str
    kind: Literal["desktop"]


class TargetRegistry:
    """Reuse IDs for matching live identities; expire after 60 idle seconds.

    This is discovery state, not an authorization mechanism for future actions.
    Those actions must freshly validate the underlying window and permissions.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._entries: dict[tuple[int, int, float, str, str], tuple[str, float]] = {}
        self._lock = Lock()

    def refresh(self, windows: list[WindowRecord], allowed: frozenset[str]) -> list[TargetInfo]:
        with self._lock:
            now = self._clock()
            current: dict[tuple[int, int, float, str, str], tuple[str, float]] = {}
            result: list[TargetInfo] = []
            for window in windows:
                if len(result) >= 100:
                    break
                if normalize_executable(window.executable) not in allowed:
                    continue
                identity = window.identity
                if identity in current:
                    continue
                prior = self._entries.get(identity)
                target_id = prior[0] if prior and prior[1] > now else "t_" + uuid.uuid4().hex
                current[identity] = (target_id, now + 60.0)
                result.append({"target_id": target_id, "name": window.title[:200], "kind": "desktop"})
            self._entries = current
            return result

    def target_id_for_handle(self, handle: int) -> str | None:
        """Match a foreground handle against the freshly discovered registry."""
        with self._lock:
            now = self._clock()
            matches = [target_id for identity, (target_id, expires) in self._entries.items()
                       if identity[0] == handle and expires > now]
            return matches[0] if len(matches) == 1 else None
