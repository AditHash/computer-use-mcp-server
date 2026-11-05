"""Run with `uv run python demo_client.py` to try the MCP tools."""

import argparse
import asyncio
import base64
import logging
import os
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from src.logging_config import configure_logging
from src.stdio_transport import logged_stdio

logger = logging.getLogger("computer_use.client")


async def main(include_screenshot: bool = False) -> None:
    """Call the desktop tools, optionally requesting and saving a screenshot."""
    configure_logging()
    server_path = Path(__file__).resolve().with_name("server.py")
    server = StdioServerParameters(
        command=sys.executable,
        args=[str(server_path)],
        # MCP subprocesses do not inherit every custom environment variable.
        env={
            "COMPUTER_USE_ALLOW_SCREENSHOTS": os.environ.get("COMPUTER_USE_ALLOW_SCREENSHOTS", "0"),
            "PYTHONIOENCODING": "utf-8",
        },
    )

    # The client owns the server subprocess and closes it when this block ends.
    logger.info("Connecting to the local MCP server")
    async with Client(logged_stdio(server), read_timeout_seconds=15) as client:
        tools = await client.list_tools()
        logger.info("Discovered %d tools", len(tools.tools))
        print("Available tools:", [tool.name for tool in tools.tools])

        tool_names = ['computer_get_status', 'get_screen_size', 'get_mouse_position', 'list_monitors']
        if include_screenshot:
            tool_names.append("take_screenshot")

        for name in tool_names:
            logger.info("Calling %s", name)
            result = await client.call_tool(name, {})
            if result.is_error:
                logger.error("Tool %s returned an error", name)
                print(f"{name} failed:")
                for item in result.content:
                    if item.type == "text":
                        print(item.text)
            else:
                logger.info("Tool %s completed", name)
                if name == "take_screenshot":
                    for item in result.content:
                        if item.type == "image":
                            output = Path(__file__).resolve().parent / "screenshots" / "screenshot.png"
                            output.parent.mkdir(exist_ok=True)
                            output.write_bytes(base64.b64decode(item.data))
                            print("Screenshot saved to:", output)
                else:
                    print(f"{name}:", result.structured_content)

    logger.info("Demo client disconnected")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Try the local computer-use MCP tools.")
    parser.add_argument("--screenshot", action="store_true", help="Request and save an opt-in screenshot.")
    args = parser.parse_args()
    asyncio.run(main(include_screenshot=args.screenshot))
