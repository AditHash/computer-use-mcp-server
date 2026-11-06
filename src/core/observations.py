"""Expiring, target/revision-scoped element references and screenshot maps."""
import time
import uuid
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from .errors import ComputerError
from .operator import protected


class Rect(BaseModel):
    left: int
    top: int
    width: int = Field(gt=0)
    height: int = Field(gt=0)

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.left + self.width and self.top <= y < self.top + self.height


@dataclass
class ElementRecord:
    role: str
    name: str
    enabled: bool
    visible: bool
    rect: dict | None
    locator: Any
    sensitive: bool = False
    scope: str | None = None
    state: str | None = None


class ElementInfo(BaseModel):
    ref: str
    role: str
    name: str
    enabled: bool
    visible: bool
    rect: Rect | None = None
    protected: bool = False


class Observation(BaseModel):
    target_id: str
    snapshot_id: str
    kind: str
    coordinate_space: str
    elements: list[ElementInfo]


@dataclass
class Snapshot:
    target_id: str
    snapshot_id: str
    fingerprint: str
    expires: float
    records: dict[str, ElementRecord]
    policy_revision: str = ''


class ImageMap(BaseModel):
    map_id: str
    target_id: str
    snapshot_id: str
    image_width: int
    image_height: int
    source: Rect


class ObservationStore:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.snapshots: dict[str, Snapshot] = {}
        self.maps: dict[str, ImageMap] = {}

    def invalidate(self, target_id: str):
        self.snapshots.pop(target_id, None)
        self.maps = {key: value for key, value in self.maps.items() if value.target_id != target_id}

    def create(self, target_id: str, fingerprint: str, records: list[ElementRecord], kind='desktop', policy_revision='') -> Observation:
        self.invalidate(target_id)
        # At most one snapshot per target, with a hard bound for long sessions.
        if len(self.snapshots) >= 128:
            self.invalidate(next(iter(self.snapshots)))
        snapshot_id = 's_' + uuid.uuid4().hex
        by_ref = {}
        elements = []
        for record in records[:500]:
            record.sensitive = record.sensitive or protected(record.name, record.role)
            if record.sensitive:
                record.name = '[protected]'
            ref = 'e_' + uuid.uuid4().hex
            by_ref[ref] = record
            elements.append(ElementInfo(ref=ref, role=record.role[:80], name=record.name[:200],
                enabled=record.enabled, visible=record.visible, rect=record.rect, protected=record.sensitive))
        self.snapshots[target_id] = Snapshot(target_id, snapshot_id, fingerprint, self.clock() + 30, by_ref, policy_revision)
        return Observation(target_id=target_id, snapshot_id=snapshot_id, kind=kind,
            coordinate_space='browser_css_pixels' if kind == 'browser' else 'screen_physical_pixels', elements=elements)

    def snapshot(self, target_id, snapshot_id) -> Snapshot:
        value = self.snapshots.get(target_id)
        if value is None or value.snapshot_id != snapshot_id:
            raise ComputerError('STALE_REF', 'Observe this target again before acting.')
        if value.expires <= self.clock():
            self.invalidate(target_id)
            raise ComputerError('STALE_REF', 'Observe this target again before acting.')
        return value

    def resolve(self, target_id, snapshot_id, ref) -> ElementRecord:
        value = self.snapshot(target_id, snapshot_id).records.get(ref)
        if value is None:
            raise ComputerError('STALE_REF', 'This element ref does not belong to the current target snapshot.')
        if value.sensitive:
            raise ComputerError('PERMISSION_DENIED', 'Protected fields and controls cannot be acted on.')
        if not value.enabled or not value.visible:
            raise ComputerError('ELEMENT_NOT_INTERACTABLE', 'The element must be visible and enabled.')
        return value

    def add_map(self, target_id, snapshot_id, source, width, height) -> ImageMap:
        self.snapshot(target_id, snapshot_id)
        result = ImageMap(map_id='m_' + uuid.uuid4().hex, target_id=target_id,
            snapshot_id=snapshot_id, image_width=width, image_height=height, source=source)
        if len(self.maps) >= 256:
            self.maps.pop(next(iter(self.maps)))
        self.maps[result.map_id] = result
        return result

    def map_point(self, target_id, snapshot_id, map_id, x, y):
        self.snapshot(target_id, snapshot_id)
        value = self.maps.get(map_id)
        if value is None or value.target_id != target_id or value.snapshot_id != snapshot_id:
            raise ComputerError('STALE_REF', 'Capture a fresh image map for this target and snapshot.')
        if not 0 <= x < value.image_width or not 0 <= y < value.image_height:
            raise ComputerError('OUT_OF_BOUNDS', 'Point must be inside the returned screenshot.')
        return (value.source.left + min(value.source.width - 1, int(x * value.source.width / value.image_width)),
                value.source.top + min(value.source.height - 1, int(y * value.source.height / value.image_height)))
