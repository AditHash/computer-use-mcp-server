"""Entry point for the local computer-use MCP server."""

import argparse
import logging

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from src.core.policy import configure_allowed_applications
from src.logging_config import configure_logging
from src.tools.desktop import get_mouse_position, get_screen_size
from src.tools.monitors import list_monitors
from src.tools.screenshot import take_screenshot
from src.tools.status import computer_get_status
from src.tools.system import get_computer_info, get_computer_resources
from src.tools.targets import computer_list_targets, get_active_window

__all__ = [
    "computer_get_status", "computer_list_targets", "get_computer_info", "get_computer_resources",
    "get_active_window", "get_mouse_position", "get_screen_size", "list_monitors", "take_screenshot", "mcp",
]

logger = logging.getLogger("computer_use.server")

mcp = MCPServer("computer-use")

# Expose the desktop functions as MCP tools.
mcp.tool()(get_screen_size)
mcp.tool()(get_mouse_position)
mcp.tool()(list_monitors)
mcp.tool()(take_screenshot)
mcp.tool()(computer_get_status)
mcp.tool()(get_computer_info)
mcp.tool()(get_computer_resources)
mcp.tool()(computer_list_targets)
mcp.tool()(get_active_window)


def main(http: bool = False, port: int = 8000, allow_apps: list[str] | None = None) -> None:
    """Start stdio by default, or an explicitly enabled loopback HTTP server."""
    configure_logging()
    try:
        if allow_apps:
            configure_allowed_applications(allow_apps)
            logger.info("Configured read-only discovery for the selected applications")
        if http:
            logger.info("Starting computer-use MCP server at http://127.0.0.1:%d/mcp", port)
            mcp.run(transport="streamable-http", host="127.0.0.1", port=port)
        else:
            logger.info("Starting computer-use MCP server over stdio")
            mcp.run(transport="stdio")
    except ToolError as error:
        logger.error("%s", error)
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        logger.info("Server interrupted by operator")
    finally:
        logger.info("Computer-use MCP server stopped")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the local computer-use MCP server.")
    parser.add_argument("--http", action="store_true", help="Listen on 127.0.0.1:8000 for the demo client.")
    parser.add_argument("--allow-app", action="append", default=[], metavar="APP", help="Allow discovery of a running app (e.g. notepad) or full .exe path. Repeat for more apps.")
    args = parser.parse_args()
    main(http=args.http, allow_apps=args.allow_app)
