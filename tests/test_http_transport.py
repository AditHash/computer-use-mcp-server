"""Check separate-server HTTP operation and preserve stdio startup."""

import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp import Client

import server


class StartupTests(unittest.TestCase):
    def test_app_selection_is_resolved_at_server_startup(self):
        with patch.object(server, 'configure_logging'), patch.object(server, 'configure_allowed_applications') as configure, patch.object(server.mcp, 'run'):
            server.main(http=True, allow_apps=['notepad'])
        configure.assert_called_once_with(['notepad'])

    def test_default_startup_preserves_stdio(self):
        with patch.object(server, 'configure_logging'), patch.object(server.mcp, 'run') as run:
            server.main()
        run.assert_called_once_with(transport='stdio')

    def test_http_is_bound_only_to_loopback(self):
        with patch.object(server, 'configure_logging'), patch.object(server.mcp, 'run') as run:
            server.main(http=True)
        run.assert_called_once_with(transport='streamable-http', host='127.0.0.1', port=8000)


class HTTPTransportTests(unittest.TestCase):
    def test_demo_connects_to_existing_server_and_leaves_it_running(self):
        root = Path(__file__).resolve().parent.parent
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        url = f'http://127.0.0.1:{port}/mcp'
        environment = dict(os.environ, COMPUTER_USE_ALLOW_SCREENSHOTS='0', COMPUTER_USE_ALLOWED_APPS='[]', PYTHONIOENCODING='utf-8')

        with tempfile.TemporaryFile(mode='w+b') as server_logs:
            process = subprocess.Popen(
                [sys.executable, '-u', '-c', f'from server import main; main(http=True, port={port})'],
                cwd=root, env=environment, stdout=server_logs, stderr=server_logs,
            )
            try:
                deadline = time.monotonic() + 15
                while True:
                    if process.poll() is not None:
                        self.fail('HTTP server exited before accepting connections')
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                            break
                    except OSError:
                        if time.monotonic() >= deadline:
                            self.fail('HTTP server did not become ready')
                        time.sleep(0.05)

                # Client-only permission cannot authorize a separately started server.
                client_environment = dict(environment, COMPUTER_USE_ALLOW_SCREENSHOTS='1')
                demo = subprocess.run(
                    [sys.executable, '-c', f'import asyncio; from demo_client import main; asyncio.run(main(server_url={url!r}))'],
                    cwd=root, env=client_environment, capture_output=True,
                    text=True, encoding='utf-8', timeout=20, check=False,
                )
                self.assertEqual(demo.returncode, 0, demo.stderr)
                self.assertIn("computer_get_status: {'status': 'ready'", demo.stdout)
                self.assertIn("get_computer_info: {'os_name':", demo.stdout)
                self.assertIn("get_computer_resources: {'cpu_percent':", demo.stdout)
                self.assertIn("computer_list_targets: {'result': []}", demo.stdout)
                self.assertIn("get_active_window: {'result': None}", demo.stdout)
                self.assertIn("'screenshots': False", demo.stdout)
                self.assertNotIn('computer_use.server', demo.stderr)
                self.assertIsNone(process.poll(), 'Client exit must not stop the server')

                async def reconnect():
                    async with Client(url, read_timeout_seconds=5) as client:
                        result = await client.call_tool('computer_get_status', {})
                        self.assertFalse(result.is_error)

                asyncio.run(reconnect())
                server_logs.seek(0)
                logs = server_logs.read().decode('utf-8', errors='replace')
                self.assertIn('computer_use.server', logs)
                self.assertIn('src.tools.status', logs)
                self.assertNotIn('computer_use.client', logs)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
