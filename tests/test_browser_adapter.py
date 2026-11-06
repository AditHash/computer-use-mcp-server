"""Real Chromium against a local fixture, never a personal browser profile."""
import asyncio
import functools
import http.server
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, quote, urlsplit

import pytest

from src.backends.browser import BrowserAdapter
from src.core.errors import ComputerError
from src.core.operator import OperatorPolicy


@pytest.fixture
def fixture_origin():
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            parts = urlsplit(self.path)
            destination = parse_qs(parts.query).get('to', [''])[0]
            if parts.path == '/loop':
                self.send_response(302)
                self.send_header('Location', '/loop')
                self.end_headers()
            elif parts.path == '/redirect':
                self.send_response(302)
                self.send_header('Location', destination)
                self.end_headers()
            elif parts.path == '/redirect-image':
                data = ('<html><body><img src="/redirect?to=' + quote(destination, safe='') + '"></body></html>').encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                super().do_GET()
    handler = functools.partial(Handler, directory=str(Path(__file__).parent / 'fixtures'))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


@pytest.mark.browser
async def test_managed_browser_refs_images_and_protected_values(fixture_origin):
    policy = OperatorPolicy.model_validate({'permissions': {'navigate': True},
        'browser': {'allowed_origins': [fixture_origin]}})
    backend = BrowserAdapter(lambda: policy, lambda target: None)
    try:
        target = await backend.open(fixture_origin + '/browser.html')
        fingerprint, elements = await backend.observe(target['target_id'], 6, 200)
        assert fingerprint
        assert any(element.name == 'Increment' and element.role == 'button' for element in elements)
        assert any(element.sensitive for element in elements)
        assert 'fixture-private-value' not in repr(elements)
        assert backend.targets()[0]['target_id'] == target['target_id']
        with pytest.raises(ComputerError, match='TARGET_NOT_ALLOWED'):
            await backend.open('https://example.invalid/')
        png, bounds = await backend.capture(target['target_id'])
        assert png[:8] == b'\x89PNG\r\n\x1a\n'
        assert bounds['width'] == 1280
    finally:
        await backend.close()


@pytest.mark.browser
async def test_default_browser_permission_does_not_launch_a_browser():
    backend = BrowserAdapter(OperatorPolicy, lambda target: None)
    with pytest.raises(ComputerError, match='PERMISSION_DENIED'):
        await backend.open('http://example.test/')
    assert backend.browser is None


@pytest.mark.browser
async def test_redirects_never_contact_a_disallowed_origin(fixture_origin):
    hits = []
    class Receiver(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            hits.append(self.path)
            self.send_response(204)
            self.end_headers()
    receiver = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
    thread = threading.Thread(target=receiver.serve_forever, daemon=True)
    thread.start()
    destination = f'http://127.0.0.1:{receiver.server_port}/must-not-be-requested'
    policy = OperatorPolicy.model_validate({'permissions': {'navigate': True}, 'browser': {'allowed_origins': [fixture_origin]}})
    backend = BrowserAdapter(lambda: policy, lambda target: None)
    try:
        with pytest.raises(ComputerError):
            await backend.open(fixture_origin + '/redirect?to=' + quote(destination, safe=''))
        target = await backend.open(fixture_origin + '/redirect-image?to=' + quote(destination, safe=''))
        await backend.pages[target['target_id']].page.wait_for_timeout(300)
        assert hits == [], 'Redirects must be checked before any disallowed network contact'
    finally:
        await backend.close()
        receiver.shutdown()
        receiver.server_close()
        thread.join(timeout=2)


@pytest.mark.browser
async def test_allowed_initial_redirect_and_closed_tab_revocation(fixture_origin):
    policy = OperatorPolicy.model_validate({'permissions': {'navigate': True},
        'browser': {'allowed_origins': [fixture_origin]}})
    backend = BrowserAdapter(lambda: policy, lambda target: None)
    try:
        with pytest.raises(ComputerError, match='redirect limit'):
            await backend.open(fixture_origin + '/loop')
        assert backend.pages == {}
        target = await backend.open(fixture_origin + '/redirect?to=' + quote(fixture_origin + '/browser.html', safe=''))
        page = backend.pages[target['target_id']].page
        assert page.url == fixture_origin + '/browser.html'
        assert await backend.context.cookies() == []
        await page.close()
        with pytest.raises(ComputerError, match='TARGET_NOT_FOUND'):
            backend.ensure(target['target_id'])
        assert backend.targets() == []
    finally:
        await backend.close()


@pytest.mark.browser
async def test_browser_denies_write_requests_popups_and_download_storage():
    requests = []
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            requests.append(('POST', self.path))
            self.send_response(204)
            self.end_headers()
        def do_GET(self):
            requests.append(('GET', self.path))
            body = b'<!doctype html><html><head><title>Network fixture</title></head><body>Controlled fixture</body></html>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(body)))
            if self.path == '/download':
                self.send_header('Content-Disposition', 'attachment; filename="fixture.html"')
            self.end_headers()
            self.wfile.write(body)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    policy = OperatorPolicy.model_validate({'permissions': {'navigate': True}, 'browser': {'allowed_origins': [origin]}})
    backend = BrowserAdapter(lambda: policy, lambda target: None)
    try:
        target = await backend.open(origin + '/')
        page = backend.pages[target['target_id']].page
        succeeded = await page.evaluate("async () => { try { await fetch('/write', {method:'POST',body:'fixture'}); return true; } catch { return false; } }")
        assert not succeeded
        assert ('POST', '/write') not in requests
        async with page.expect_popup() as popup_event:
            await page.evaluate("() => { window.open('/popup'); }")
        popup = await popup_event.value
        for _ in range(100):
            if popup.is_closed():
                break
            await asyncio.sleep(0.01)
        assert popup.is_closed()
        assert backend.context.pages == [page]
        assert ('GET', '/popup') not in requests
        async with page.expect_download() as download_event:
            await page.evaluate("() => { const a=document.createElement('a'); a.href='/download'; a.click(); }")
        download = await download_event.value
        assert await download.failure() is not None
        assert backend.targets() == [{'target_id': target['target_id'], 'name': 'Network fixture', 'kind': 'browser'}]
    finally:
        await backend.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


async def test_cancelled_driver_start_closes_the_startup_manager():
    entered = asyncio.Event()
    manager = SimpleNamespace(__aexit__=AsyncMock())
    async def starting():
        entered.set()
        await asyncio.Event().wait()
    manager.start = starting
    backend = BrowserAdapter(OperatorPolicy, lambda _: None)
    with patch('playwright.async_api.async_playwright', return_value=manager):
        task = asyncio.create_task(backend._start())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    manager.__aexit__.assert_awaited_once()
    assert backend.playwright is None
