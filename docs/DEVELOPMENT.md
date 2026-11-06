# Development, Packaging, and Distribution

The prototype targets Windows 10/11, Python 3.14+, PowerShell and uv. Browser
and pure unit tests also run without native Windows APIs. No GPU or LLM service
is required. Never use personal documents or authenticated browser profiles in tests.

## Setup and running

```powershell
uv sync --locked
uv run playwright install chromium
uv run computer-use-mcp --help
uv run server.py
```

Plain startup uses stdio; stdout is reserved for MCP protocol messages and logs
go to stderr. The installed command calls root `server:cli`. For the separately
started demo server/client, use `uv run server.py --http`, then
`uv run demo_client.py` in another terminal. HTTP is opt-in and loopback-only.

Use `--config PATH` with a local copy of `policy.example.toml`. See
[operator policy](OPERATOR_POLICY.md) for exact permissions and grants. Input,
screenshots and browser navigation are disabled by default. No tool edits policy.

## Project organization

Root `server.py` owns registration/startup and `demo_client.py` is the separate
learning client. MCP handlers live in `src/tools/`; trusted policy, targets,
observations and dispatch in `src/core/`; Windows and browser code in
`src/backends/`. This intentionally preserves the user-requested root entry point
and src modules rather than introducing a second server module.

The official MCP SDK v2 provides `MCPServer`. Browser code uses Playwright AI ARIA
snapshots and server-wrapped refs. Native APIs are imported lazily on an owned
COM worker. `pyproject.toml` declares runtime and development dependencies;
`uv.lock` resolves them. Always use uv/the project interpreter rather than the
machine's unrelated Python alpha installation.

## Checks and builds

```powershell
uv run pytest -q
uv run ruff check .
uv build
```

Browser tests use local fixtures and owned ephemeral Chromium contexts. Native
integration is explicitly opt-in and uses `tests/fixtures/windows_app.py`, not
Notepad. Run live native tests alone: concurrent commands or human focus changes
can make physical-input checks abort. Exact commands and current evidence are in
[TEST_PLAN.md](TEST_PLAN.md).

The setuptools wheel includes root server.py and the src package. The console
command is `computer-use-mcp`. Verify the installed wheel from outside the checkout
using `tests/test_installed_cli.py`; do not infer package completeness from an
import while the repository is the working directory. MANIFEST.in includes docs,
the example policy, the demo client, and fixture sources in the source archive.

The CI workflow runs unit/browser checks, Ruff, builds, and clean-environment
installed-CLI acceptance on Windows and Ubuntu. Native UI tests remain manual;
GitHub-hosted CI is not evidence for real interactive Windows behavior.

## Release checklist (no automatic publishing)

- Pass all applicable checks and document exact remaining platform limitations.
- Verify stdio discovery and default-denied permissions from the installed wheel.
- Review artifact contents; exclude private policy, images, logs and personal data.
- Review tool schema changes against TOOL_CONTRACTS.md.
- Obtain an explicit publishing request before TestPyPI/PyPI or a GitHub release.

No package has been published by this workflow. uv build creates local artifacts
only; CI has no publishing step or write permission.

Upstream references: [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk),
[Playwright](https://playwright.dev/python/docs/api/class-page),
[uv](https://docs.astral.sh/uv/),
[setuptools configuration](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html).
