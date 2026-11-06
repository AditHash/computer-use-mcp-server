"""Stable, safe errors returned to MCP callers."""
from mcp.server.mcpserver.exceptions import ToolError


class ComputerError(ToolError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f'{code}: {message}')
