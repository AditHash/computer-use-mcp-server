"""Opt-in wheel acceptance; the executable must come from a clean environment."""
import asyncio
import os
import subprocess
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters


@pytest.mark.skipif(not os.environ.get('COMPUTER_USE_INSTALLED_CLI'), reason='Build and install the wheel in a clean environment first')
async def test_installed_console_script_stdio_discovery(tmp_path):
    executable = Path(os.environ['COMPUTER_USE_INSTALLED_CLI']).resolve(strict=True)
    help_result = await asyncio.to_thread(subprocess.run, [str(executable), '--help'], cwd=tmp_path, capture_output=True,
                                 text=True, timeout=20, check=True)
    assert '--config' in help_result.stdout
    assert '--http' in help_result.stdout
    parameters = StdioServerParameters(command=str(executable), cwd=str(tmp_path), env={
        'COMPUTER_USE_ALLOWED_APPS': '[]', 'COMPUTER_USE_ALLOW_SCREENSHOTS': '0',
    })
    async with Client(parameters, read_timeout_seconds=10) as client:
        tools = await client.list_tools()
        assert len(tools.tools) == 21
        status = await client.call_tool('computer_get_status', {})
        assert not status.is_error
        assert status.structured_content['permissions']['interaction'] is False
        targets = await client.call_tool('computer_list_targets', {})
        assert not targets.is_error
        assert targets.structured_content == {'result': []}
