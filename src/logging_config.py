"""Shared console logging setup for the server and demo client."""

import logging
import sys


def configure_logging() -> None:
    """Send timestamped INFO-and-above logs to stderr, preserving MCP stdout."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stderr,
        # The MCP SDK may configure a handler while creating the server.
        force=True,
    )
