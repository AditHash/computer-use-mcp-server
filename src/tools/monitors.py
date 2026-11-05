"""Read display geometry without capturing screenshots."""

import logging
import sys
from typing import TypedDict

from mcp.server.mcpserver.exceptions import ToolError
from mss import MSS, ScreenShotError

logger = logging.getLogger(__name__)


class MonitorInfo(TypedDict):
    """One monitor's position and dimensions in physical screen pixels."""

    index: int
    left: int
    top: int
    width: int
    height: int
    is_primary: bool


def list_monitors() -> list[MonitorInfo]:
    """List Windows monitors and their physical-pixel bounds.

    Each monitor covers left <= x < left + width and top <= y < top + height.
    Left/top may be negative. Indices describe this call, not stable target IDs.
    This reads display geometry only; it does not capture pixels.
    """
    if sys.platform != "win32":
        raise ToolError("UNSUPPORTED: Monitor discovery currently supports Windows only.")

    logger.info("Listing connected monitors")
    try:
        with MSS() as display:
            primary = display.primary_monitor
            # Entry 0 describes the combined desktop, not an individual monitor.
            result: list[MonitorInfo] = [
                {
                    "index": index,
                    "left": monitor["left"],
                    "top": monitor["top"],
                    "width": monitor["width"],
                    "height": monitor["height"],
                    "is_primary": monitor == primary,
                }
                for index, monitor in enumerate(display.monitors[1:], start=1)
            ]
    except (ScreenShotError, OSError):
        logger.error("Windows monitor discovery failed")
        raise ToolError("BACKEND_UNAVAILABLE: Windows could not list the displays.") from None

    logger.info("Listed %d monitors", len(result))
    return result
