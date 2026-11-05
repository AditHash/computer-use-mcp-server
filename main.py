import ctypes
import sys

from mcp.server import MCPServer


mcp = MCPServer("computer-use")


@mcp.tool()
def get_screen_size() -> dict[str, int]:
    """Return the primary screen width and height in Windows desktop coordinates.

    Coordinates may be scaled by Windows DPI settings. This reads the display
    size without taking a screenshot or moving the mouse.
    """
    if sys.platform != "win32":
        raise RuntimeError("get_screen_size currently supports Windows only.")

    # Windows defines metric 0 as primary screen width and 1 as height.
    user32 = ctypes.windll.user32
    width = user32.GetSystemMetrics(0)
    height = user32.GetSystemMetrics(1)
    if width <= 0 or height <= 0:
        raise RuntimeError("Windows could not report the primary screen size.")

    return {"width": width, "height": height}


if __name__ == "__main__":
    mcp.run(transport="stdio")
