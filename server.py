"""Entry point for the local computer-use MCP server."""

import logging

from mcp.server import MCPServer

from src.logging_config import configure_logging
from src.tools.desktop import get_mouse_position, get_screen_size
from src.tools.monitors import list_monitors
from src.tools.screenshot import take_screenshot
from src.tools.status import computer_get_status

__all__ = ['get_mouse_position', 'get_screen_size', 'list_monitors', 'take_screenshot', 'mcp', 'computer_get_status']

logger = logging.getLogger("computer_use.server")

mcp = MCPServer("computer-use")

# Expose the desktop functions as MCP tools.
mcp.tool()(get_screen_size)
mcp.tool()(get_mouse_position)
mcp.tool()(list_monitors)
mcp.tool()(take_screenshot)
mcp.tool()(computer_get_status)


def main() -> None:
    """Start the MCP server over standard input/output."""
    configure_logging()
    logger.info("Starting computer-use MCP server over stdio")
    try:
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("Server interrupted by operator")
    finally:
        logger.info("Computer-use MCP server stopped")


if __name__ == "__main__":
    main()
