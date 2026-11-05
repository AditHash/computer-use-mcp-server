"""Forward a stdio server's logs through the parent process's terminal."""

import os
import sys
from contextlib import asynccontextmanager
from threading import Thread

from mcp.client.stdio import StdioServerParameters, stdio_client


@asynccontextmanager
async def logged_stdio(server: StdioServerParameters):
    """Keep protocol data separate while making child stderr visible on Windows."""
    read_fd, write_fd = os.pipe()

    def forward_logs() -> None:
        with os.fdopen(read_fd, "r", encoding="utf-8", errors="replace") as stream:
            for line in stream:
                sys.stderr.write(line)
                sys.stderr.flush()

    # A pipe works even when the SDK starts a hidden Windows subprocess whose
    # inherited console handles cannot display output. The parent prints it.
    reader = Thread(target=forward_logs, name="server-log-reader", daemon=True)
    try:
        with os.fdopen(write_fd, "w", encoding="utf-8") as errlog:
            reader.start()
            async with stdio_client(server, errlog=errlog) as streams:
                yield streams
    finally:
        # Closing the writer lets the reader drain buffered lines and exit.
        if reader.ident is not None:
            reader.join(timeout=1)
