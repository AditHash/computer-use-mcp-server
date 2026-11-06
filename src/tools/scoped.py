"""Target-scoped observation, capture, and bounded interaction tools."""
import asyncio
import json
import time
from typing import Annotated, Literal

from mcp.server.mcpserver import Image
from mcp.types import ImageContent, TextContent
from pydantic import BaseModel, Field

from src.core.errors import ComputerError
from src.core.observations import Observation, Rect
from src.core.runtime import ActionResult, get_runtime

TargetId = Annotated[str, Field(pattern=r'^t_[0-9a-f]{32}$')]
SnapshotId = Annotated[str, Field(pattern=r'^s_[0-9a-f]{32}$')]
ElementRef = Annotated[str, Field(pattern=r'^e_[0-9a-f]{32}$')]
MapId = Annotated[str, Field(pattern=r'^m_[0-9a-f]{32}$')]


async def computer_observe(target_id: TargetId, max_depth: Annotated[int, Field(ge=1, le=10)] = 6) -> Observation:
    """Read an allowed target and obtain fresh opaque refs before acting.

    Protected values are omitted. Re-observe after any action or stale-ref error.
    """
    return await get_runtime().observe(target_id, max_depth)


async def focus_window(target_id: TargetId, snapshot_id: SnapshotId, ref: ElementRef) -> ActionResult:
    """Focus an observed allowed target only when local policy permits disruption."""
    return await get_runtime().action(target_id, snapshot_id, ref, 'focus')


async def computer_click(target_id: TargetId, snapshot_id: SnapshotId, ref: ElementRef) -> ActionResult:
    """Activate a fresh allowed element semantically. Prefer this over coordinates."""
    return await get_runtime().action(target_id, snapshot_id, ref, 'click')


async def computer_type(target_id: TargetId, snapshot_id: SnapshotId, ref: ElementRef,
                        text: Annotated[str, Field(max_length=5000)]) -> ActionResult:
    """Fill an observed ordinary field; protected fields and ungranted controls are denied."""
    return await get_runtime().action(target_id, snapshot_id, ref, 'type', text=text)


async def computer_press_keys(target_id: TargetId, snapshot_id: SnapshotId, ref: ElementRef,
    keys: Annotated[list[Literal['TAB', 'SHIFT+TAB', 'ARROWUP', 'ARROWDOWN', 'ARROWLEFT', 'ARROWRIGHT',
        'HOME', 'END', 'PAGEUP', 'PAGEDOWN', 'ESCAPE']], Field(min_length=1, max_length=10)]) -> ActionResult:
    """Send bounded navigation keys to an allowed element. Command-launch and submit chords are unsupported."""
    return await get_runtime().action(target_id, snapshot_id, ref, 'press_keys', keys=keys)


async def computer_scroll(target_id: TargetId, snapshot_id: SnapshotId, ref: ElementRef,
    direction: Literal['up', 'down', 'left', 'right'], amount: Annotated[int, Field(ge=1, le=10)] = 1) -> ActionResult:
    """Scroll a fresh permitted element by a bounded amount, then observe again."""
    return await get_runtime().action(target_id, snapshot_id, ref, 'scroll', direction=direction, amount=amount)


async def computer_double_click(target_id: TargetId, snapshot_id: SnapshotId, ref: ElementRef) -> ActionResult:
    """Double-click an allowed element. Native physical fallback requires separate local permission."""
    return await get_runtime().action(target_id, snapshot_id, ref, 'double_click')


class DragImagePoints(BaseModel):
    map_id: MapId
    source_x: Annotated[int, Field(ge=0)]
    source_y: Annotated[int, Field(ge=0)]
    destination_x: Annotated[int, Field(ge=0)]
    destination_y: Annotated[int, Field(ge=0)]


async def computer_drag(target_id: TargetId, snapshot_id: SnapshotId, source_ref: ElementRef,
    destination_ref: ElementRef, duration: Annotated[float, Field(ge=0.1, le=1, allow_inf_nan=False)] = 0.5,
    image_points: DragImagePoints | None = None) -> ActionResult:
    """Drag between permitted elements; prefer refs over optional screenshot points.

    Image points require a fresh screenshot map and local fallback permission.
    Both endpoints must remain inside their explicitly permitted elements.
    """
    return await get_runtime().action(target_id, snapshot_id, source_ref, 'drag',
        destination_ref=destination_ref, duration=duration,
        image_points=image_points.model_dump() if image_points is not None else None)


async def browser_open(url: Annotated[str, Field(min_length=1, max_length=2048)]) -> dict[str, str]:
    """Open a locally approved HTTP(S) origin in a server-owned isolated browser context."""
    return await get_runtime().open_browser(url)


async def computer_screenshot(target_id: TargetId, snapshot_id: SnapshotId, crop: Rect | None = None,
    max_dimension: Annotated[int, Field(ge=64, le=1920)] = 1280) -> list[TextContent | ImageContent]:
    """Capture one allowed target with separate permission and return a scoped image map.

    Crop is relative to the target capture, not the desktop. Input coordinates
    from the returned image require its map_id and the same fresh snapshot.
    """
    png, metadata = await get_runtime().screenshot(target_id, snapshot_id, crop, max_dimension)
    return [TextContent(type='text', text=json.dumps(metadata)), Image(data=png, format='png').to_image_content()]


async def move_mouse(target_id: TargetId, snapshot_id: SnapshotId, map_id: MapId,
    x: Annotated[int, Field(ge=0)], y: Annotated[int, Field(ge=0)],
    duration: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 0.5) -> ActionResult:
    """Last-resort pointer movement using a fresh target/snapshot-bound screenshot map.

    Requires local interaction and fallback permission; native input additionally
    requires focus-disruption permission and an already foreground target.
    """
    return await get_runtime().move(target_id, snapshot_id, map_id, x, y, duration)


class WaitResult(BaseModel):
    requested_seconds: float
    elapsed_seconds: float


async def computer_wait(seconds: Annotated[float, Field(ge=0, le=10, allow_inf_nan=False)] = 1.0) -> WaitResult:
    """Wait at most ten seconds without blocking other requests; observe state afterwards."""
    runtime = get_runtime()
    started = time.monotonic()
    try:
        with runtime.stop.track():
            await asyncio.sleep(seconds)
    except asyncio.CancelledError:
        raise ComputerError('CANCELLED', 'The wait was cancelled.') from None
    return WaitResult(requested_seconds=seconds, elapsed_seconds=max(0, time.monotonic() - started))


SCOPED_TOOLS = (computer_observe, focus_window, computer_click, computer_type, computer_press_keys,
    computer_scroll, browser_open, computer_screenshot, move_mouse, computer_double_click,
    computer_drag, computer_wait)
