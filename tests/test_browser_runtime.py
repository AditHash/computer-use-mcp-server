"""Positive dispatcher acceptance against real isolated Chromium and local HTML."""
import asyncio
from unittest.mock import patch

import pytest
from playwright.async_api import Locator
from test_browser_adapter import fixture_origin as fixture_origin  # noqa: PLC0414 - expose the pytest fixture.
from test_dispatch import Banner, Source

from src.core.errors import ComputerError
from src.core.operator import OperatorPolicy
from src.core.runtime import ComputerRuntime


def browser_policy(origin):
    return OperatorPolicy.model_validate({
        'permissions': {'navigate': True, 'interact': True, 'screenshot': True, 'focus': True, 'fallback': True},
        'browser': {'allowed_origins': [origin]},
        'grants': [
            {'target': origin, 'role': 'button', 'name': 'Increment', 'actions': ['click', 'double_click', 'focus']},
            {'target': origin, 'role': 'textbox', 'name': 'Name', 'actions': ['type', 'press_keys']},
            {'target': origin, 'role': 'textbox', 'name': 'Notes', 'actions': ['type']},
            {'target': origin, 'role': 'button', 'name': 'Frame counter', 'actions': ['click']},
            {'target': origin, 'role': 'textbox', 'name': 'Frame name', 'actions': ['type']},
            {'target': origin, 'role': 'region', 'name': 'Scrollable area', 'actions': ['scroll']},
            {'target': origin, 'role': 'button', 'name': 'Drag source', 'actions': ['drag']},
            {'target': origin, 'role': 'button', 'name': 'Drop zone', 'actions': ['drag']},
        ],
    })


@pytest.mark.browser
async def test_real_browser_click_type_scroll_capture_and_stale_refs(fixture_origin):
    engine = ComputerRuntime(Source(browser_policy(fixture_origin)), banner_factory=Banner)
    try:
        target = await engine.open_browser(fixture_origin + '/browser.html')
        target_id = target['target_id']
        observation = await engine.observe(target_id)
        button = next(item for item in observation.elements if item.name == 'Increment')
        await engine.action(target_id, observation.snapshot_id, button.ref, 'click')
        page = engine.browser.pages[target_id].page
        assert await page.locator('#count').inner_text() == '1'
        with pytest.raises(ComputerError, match='STALE_REF'):
            await engine.action(target_id, observation.snapshot_id, button.ref, 'click')
        observation = await engine.observe(target_id)
        field = next(item for item in observation.elements if item.name == 'Name')
        result = await engine.action(target_id, observation.snapshot_id, field.ref, 'type', text='MCP fixture input')
        assert result.status == 'verified'
        assert await page.locator('#name').input_value() == 'MCP fixture input'
        observation = await engine.observe(target_id)
        region = next(item for item in observation.elements if item.name == 'Scrollable area')
        result = await engine.action(target_id, observation.snapshot_id, region.ref, 'scroll', direction='down', amount=2)
        assert result.status == 'verified'
        observation = await engine.observe(target_id)
        png, metadata = await engine.screenshot(target_id, observation.snapshot_id, max_dimension=640)
        assert png[:8] == b'\x89PNG\r\n\x1a\n'
        assert metadata['image_width'] == 640
        assert metadata['coordinate_space'] == 'browser_css_pixels'
        assert 'fixture-private-value' not in observation.model_dump_json()
    finally:
        await engine.close()


@pytest.mark.browser
async def test_contenteditable_fill_verifies_actual_text(fixture_origin):
    engine = ComputerRuntime(Source(browser_policy(fixture_origin)), banner_factory=Banner)
    try:
        target_id = (await engine.open_browser(fixture_origin + '/browser.html'))['target_id']
        observation = await engine.observe(target_id)
        field = next(item for item in observation.elements if item.name == 'Notes')
        result = await engine.action(target_id, observation.snapshot_id, field.ref, 'type', text='Ordinary fixture notes')
        page = engine.browser.pages[target_id].page
        assert await page.locator('#notes').text_content() == 'Ordinary fixture notes'
        assert result.status == 'verified'
    finally:
        await engine.close()


@pytest.mark.browser
async def test_real_mapped_drag_uses_downscaled_image_endpoints(fixture_origin):
    engine = ComputerRuntime(Source(browser_policy(fixture_origin)), banner_factory=Banner)
    try:
        target_id = (await engine.open_browser(fixture_origin + '/browser.html'))['target_id']
        observation = await engine.observe(target_id)
        source = next(item for item in observation.elements if item.name == 'Drag source')
        destination = next(item for item in observation.elements if item.name == 'Drop zone')
        _, metadata = await engine.screenshot(target_id, observation.snapshot_id, max_dimension=640)
        def center(element):
            return (int((element.rect.left + element.rect.width / 2) * metadata['scale_x']),
                    int((element.rect.top + element.rect.height / 2) * metadata['scale_y']))
        sx, sy = center(source)
        dx, dy = center(destination)
        await engine.action(target_id, observation.snapshot_id, source.ref, 'drag', destination_ref=destination.ref,
            image_points={'map_id': metadata['map_id'], 'source_x': sx, 'source_y': sy,
                          'destination_x': dx, 'destination_y': dy})
        page = engine.browser.pages[target_id].page
        assert await page.locator('#drop_state').inner_text() == 'dropped'
    finally:
        await engine.close()


@pytest.mark.browser
async def test_child_frame_refs_are_wrapped_and_invalidated_after_navigation(fixture_origin):
    engine = ComputerRuntime(Source(browser_policy(fixture_origin)), banner_factory=Banner)
    try:
        target_id = (await engine.open_browser(fixture_origin + '/frames.html'))['target_id']
        page = engine.browser.pages[target_id].page
        await page.frame_locator('iframe').locator('#frame_increment').wait_for()
        observation = await engine.observe(target_id)
        assert 'child-private-value' not in observation.model_dump_json()
        button = next(item for item in observation.elements if item.name == 'Frame counter')
        await engine.action(target_id, observation.snapshot_id, button.ref, 'click')
        assert await page.frame_locator('iframe').locator('#frame_count').inner_text() == 'clicked'
        observation = await engine.observe(target_id)
        field = next(item for item in observation.elements if item.name == 'Frame name')
        await engine.action(target_id, observation.snapshot_id, field.ref, 'type', text='frame fixture input')
        assert await page.frame_locator('iframe').locator('#frame_name').input_value() == 'frame fixture input'
        observation = await engine.observe(target_id)
        field = next(item for item in observation.elements if item.name == 'Frame name')
        await page.frames[1].goto(fixture_origin + '/frame-child.html?revision=2')
        with pytest.raises(ComputerError, match='STALE_REF'):
            await engine.action(target_id, observation.snapshot_id, field.ref, 'type', text='must not be typed')
    finally:
        await engine.close()


@pytest.mark.browser
async def test_stop_closes_context_with_pending_click_and_denies_queued_action(fixture_origin):
    engine = ComputerRuntime(Source(browser_policy(fixture_origin)), banner_factory=Banner)
    try:
        target_id = (await engine.open_browser(fixture_origin + '/browser.html'))['target_id']
        page = engine.browser.pages[target_id].page
        await page.evaluate('''() => {
            const blocker = document.createElement('div');
            blocker.setAttribute('aria-hidden', 'true');
            blocker.style.cssText = 'position:fixed;inset:0;z-index:99999;background:transparent';
            document.body.append(blocker);
        }''')
        observation = await engine.observe(target_id)
        button = next(item for item in observation.elements if item.name == 'Increment')
        entered = asyncio.Event()
        closed = asyncio.Event()
        engine.browser.context.on('close', lambda *_: closed.set())
        original_click = Locator.click
        async def pending_click(locator, *args, **kwargs):
            entered.set()
            return await original_click(locator, *args, **kwargs)
        with patch.object(Locator, 'click', pending_click):
            active = asyncio.create_task(engine.action(target_id, observation.snapshot_id, button.ref, 'click'))
            await asyncio.wait_for(entered.wait(), 5)
            await asyncio.sleep(0.1)
            assert not active.done()
            assert await page.locator('#count').inner_text() == '0'
            queued = asyncio.create_task(engine.action(target_id, observation.snapshot_id, button.ref, 'click'))
            engine.stop.stop()
            results = await asyncio.wait_for(asyncio.gather(active, queued, return_exceptions=True), 5)
        assert all(isinstance(result, ComputerError) and result.code == 'CANCELLED' for result in results)
        await asyncio.wait_for(closed.wait(), 5)
        assert page.is_closed(), 'Pending Playwright input must lose its context, preventing delayed clicks'
        assert engine.browser.pages == {}
    finally:
        await engine.close()


@pytest.mark.browser
async def test_policy_revocation_aborts_pending_browser_input(fixture_origin):
    engine = ComputerRuntime(Source(browser_policy(fixture_origin)), banner_factory=Banner)
    active = None
    try:
        target_id = (await engine.open_browser(fixture_origin + '/browser.html'))['target_id']
        page = engine.browser.pages[target_id].page
        await page.evaluate('''() => {
            const blocker = document.createElement('div');
            blocker.setAttribute('aria-hidden', 'true');
            blocker.style.cssText='position:fixed;inset:0;z-index:99999';
            document.body.append(blocker);
        }''')
        observation = await engine.observe(target_id)
        button = next(item for item in observation.elements if item.name == 'Increment')
        entered, closed = asyncio.Event(), asyncio.Event()
        engine.browser.context.on('close', lambda *_: closed.set())
        original = Locator.click
        async def pending_click(locator, *args, **kwargs):
            entered.set()
            return await original(locator, *args, **kwargs)
        with patch.object(Locator, 'click', pending_click):
            active = asyncio.create_task(engine.action(target_id, observation.snapshot_id, button.ref, 'click'))
            await asyncio.wait_for(entered.wait(), 5)
            engine.source.policy.permissions.interact = False
            await asyncio.wait_for(closed.wait(), 1)
            result = (await asyncio.gather(active, return_exceptions=True))[0]
        assert isinstance(result, ComputerError) and result.code == 'CANCELLED'
        assert page.is_closed()
        assert engine.stop.event.is_set()
    finally:
        await engine.close()
        if active is not None:
            await asyncio.gather(active, return_exceptions=True)


@pytest.mark.browser
async def test_real_browser_double_click_drag_keys_focus_and_mapped_pointer(fixture_origin):
    engine = ComputerRuntime(Source(browser_policy(fixture_origin)), banner_factory=Banner)
    try:
        target = await engine.open_browser(fixture_origin + '/browser.html')
        target_id = target['target_id']
        page = engine.browser.pages[target_id].page
        observation = await engine.observe(target_id)
        button = next(item for item in observation.elements if item.name == 'Increment')
        await engine.action(target_id, observation.snapshot_id, button.ref, 'double_click')
        assert await page.locator('#count').inner_text() == '2'
        observation = await engine.observe(target_id)
        source = next(item for item in observation.elements if item.name == 'Drag source')
        destination = next(item for item in observation.elements if item.name == 'Drop zone')
        await engine.action(target_id, observation.snapshot_id, source.ref, 'drag', destination_ref=destination.ref, duration=0.5)
        assert await page.locator('#drop_state').inner_text() == 'dropped'
        observation = await engine.observe(target_id)
        field = next(item for item in observation.elements if item.name == 'Name')
        await engine.action(target_id, observation.snapshot_id, field.ref, 'type', text='navigation')
        observation = await engine.observe(target_id)
        field = next(item for item in observation.elements if item.name == 'Name')
        await engine.action(target_id, observation.snapshot_id, field.ref, 'press_keys', keys=['HOME', 'ARROWRIGHT'])
        assert await page.locator('#name').evaluate('(el) => el.selectionStart') == 1
        observation = await engine.observe(target_id)
        button = next(item for item in observation.elements if item.name == 'Increment')
        await engine.action(target_id, observation.snapshot_id, button.ref, 'focus')
        assert await page.locator('#increment').evaluate('(el) => document.activeElement === el')
        observation = await engine.observe(target_id)
        _, metadata = await engine.screenshot(target_id, observation.snapshot_id, max_dimension=640)
        await engine.move(target_id, observation.snapshot_id, metadata['map_id'], 5, 5)
        assert await page.evaluate('window.lastPointer') == [10, 10]
    finally:
        await engine.close()
