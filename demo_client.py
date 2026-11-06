"""Run with `uv run python demo_client.py` to try the MCP tools."""

import argparse
import asyncio
import base64
import logging
from pathlib import Path

from mcp import Client

from src.logging_config import configure_logging

logger = logging.getLogger("computer_use.client")


async def main(
    include_screenshot: bool = False,
    server_url: str = "http://127.0.0.1:8000/mcp",
) -> None:
    """Connect to the running server without starting or stopping its process."""
    configure_logging()
    logger.info("Connecting to the running local MCP server")
    async with Client(server_url, read_timeout_seconds=15) as client:
        tools = await client.list_tools()
        logger.info("Discovered %d tools", len(tools.tools))
        print("Available tools:", [tool.name for tool in tools.tools])

        tool_names = [
            "computer_get_status", "get_computer_info", "get_computer_resources",
            "get_screen_size", "get_mouse_position", "list_monitors", "computer_list_targets", "get_active_window",
        ]
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
    parser = argparse.ArgumentParser(description="Connect to server.py --http and try the MCP tools.")
    parser.add_argument("--screenshot", action="store_true", help="Request and save an opt-in screenshot.")
    args = parser.parse_args()
    try:
        asyncio.run(main(include_screenshot=args.screenshot))
    except KeyboardInterrupt:
        logger.info("Demo client interrupted")
    except Exception:  # noqa: BLE001 - CLI boundary: report failure without exposing protocol payloads.
        logger.error("Demo failed. Start 'uv run server.py --http' in another terminal and check its logs.")
        raise SystemExit(1) from None
