"""Real MCP serialization and validation with a private browser fixture."""
import base64
import json
from unittest.mock import patch

import pytest
from mcp import Client
from test_browser_adapter import fixture_origin as fixture_origin  # noqa: PLC0414 - expose the pytest fixture.
from test_browser_runtime import browser_policy
from test_dispatch import Banner, Source

from server import mcp
from src.core.runtime import ComputerRuntime


@pytest.mark.browser
async def test_scoped_mcp_browser_flow_image_blocks_and_validation(fixture_origin):
    engine = ComputerRuntime(Source(browser_policy(fixture_origin)), banner_factory=Banner)
    with patch('src.core.runtime._runtime', engine):
        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert len(tools.tools) == 21
            opened = await client.call_tool('browser_open', {'url': fixture_origin + '/browser.html'})
            assert not opened.is_error
            target_id = opened.structured_content['target_id']
            observed = await client.call_tool('computer_observe', {'target_id': target_id})
            assert not observed.is_error
            snapshot = observed.structured_content
            assert 'fixture-private-value' not in json.dumps(snapshot)
            captured = await client.call_tool('computer_screenshot', {'target_id': target_id, 'snapshot_id': snapshot['snapshot_id'], 'max_dimension': 640})
            assert not captured.is_error
            assert captured.structured_content is None
            assert [item.type for item in captured.content] == ['text', 'image']
            metadata = json.loads(captured.content[0].text)
            assert metadata['target_id'] == target_id
            assert base64.b64decode(captured.content[1].data)[:8] == b'\x89PNG\r\n\x1a\n'
            assert captured.content[1].mime_type == 'image/png'
            waited = await client.call_tool('computer_wait', {'seconds': 0.01})
            assert not waited.is_error
            assert waited.structured_content['elapsed_seconds'] >= 0.009
            invalid = await client.call_tool('computer_wait', {'seconds': 11})
            assert invalid.is_error
            button = next(item for item in snapshot['elements'] if item['name'] == 'Increment')
            clicked = await client.call_tool('computer_click', {'target_id': target_id, 'snapshot_id': snapshot['snapshot_id'], 'ref': button['ref']})
            assert not clicked.is_error
            repeated = await client.call_tool('computer_click', {'target_id': target_id, 'snapshot_id': snapshot['snapshot_id'], 'ref': button['ref']})
            assert repeated.is_error
            assert 'STALE_REF' in repeated.content[0].text
