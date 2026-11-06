# Testing and Acceptance Matrix

## Recorded checkpoint: 2026-11-06

Environment: Windows 11, project Python 3.14.4, MCP SDK 2.3.0, Playwright 1.64.1.

| Command/check | Actual result |
| --- | --- |
| `uv sync --locked` | Passed; project installed with its console command |
| `uv run computer-use-mcp --help` | Passed |
| `uv run pytest -q` | 89 passed, 6 skipped, 15 subtests passed; four additional physical guard cases subsequently passed |
| `ruff check .` | Passed |
| `uv build` | Wheel and source distribution built locally; nothing published |
| Clean-environment wheel installation + `tests/test_installed_cli.py` | Passed real stdio discovery of 21 tools; default writes denied; empty target list |
| Browser/dispatcher acceptance | Real Chromium actions, mapped drag, contenteditable, frames, redirect limits, blocked write requests, popups/downloads, emergency stop and pending-input revocation passed |
| Opt-in `tests/test_windows_acceptance.py` | 4 passed, 1 failed: pointer movement correctly rejected loss of foreground focus |
| Isolated native physical-input retry | Skipped because Windows refused initial focus; manual operator focus still needed |

The first four native tests cover disposable-fixture UIA observe/click/type,
protected controls, nonblank PrintWindow capture, external edit invalidation,
non-activating stop banner, and cancelled-worker suppression of late effects.
The fifth verified focus, field navigation keys and list scrolling before losing
foreground during mapped pointer movement. Native pointer/double-click/drag
acceptance is therefore **not complete**. Do not reinterpret the safety rejection
as a passing positive-input test.

Run native tests only in a controlled interactive session:

```powershell
$env:COMPUTER_USE_RUN_WINDOWS_TESTS='1'
uv run pytest tests/test_windows_acceptance.py -q -rs
```

If Windows prevents automatic activation, the optional
`COMPUTER_USE_WAIT_FOR_FOCUS=1` mode waits for the local operator to focus the
fixture title bar. Keep the fixture foreground until it closes. Do not force
focus through OS bypasses. The tests use their own disposable native application;
Notepad is not required.

Wheel verification after a local build/install in a fresh environment:

```powershell
uv build
uv venv .uv-cache/wheel-acceptance --python .venv/Scripts/python.exe
uv pip install --python .uv-cache/wheel-acceptance/Scripts/python.exe dist/computer_use_mcp_server-0.1.0-py3-none-any.whl
$env:COMPUTER_USE_INSTALLED_CLI=(Resolve-Path .uv-cache/wheel-acceptance/Scripts/computer-use-mcp.exe).Path
uv run pytest tests/test_installed_cli.py -q
```

The acceptance test runs the installed executable with a temporary working
directory outside the repository. Browser integration uses only local fixture
pages in an ephemeral managed Chromium context. Mapped drag endpoints, frame
ownership/ref invalidation, popup/download restrictions, approved/disallowed
redirects, pending-input stop, policy revocation, cancelled driver startup and
late screenshot-permission revocation have passing regressions. Remaining work
includes positive live native pointer input, live mixed-DPI/multi-monitor input
or an explicit supported-environment limitation, hosted CI execution and the
final security/readiness audit.

Test behavior and security boundaries, not just tool registration. The server must be testable without a physical desktop by injecting fake adapters; live desktop tests are explicitly opt-in and run on Windows.

## Automated unit tests (all platforms)

| Area | Required assertions |
| --- | --- |
| Tool schemas | Required fields, invalid enums, oversize text, missing target/ref |
| Targets | Opaque IDs, deny unregistered target, closed/replaced process rejected |
| Snapshots | Per-target revisions, stale-ref rejection, no cross-target ref reuse |
| Permissions | Default deny, granular inspect/screenshot/interact, revocation |
| Dispatch | Correct adapter, deterministic errors, no silent physical fallback |
| Output | Truncate depth/size; redact password values and sensitive logs |
| Concurrency | Timeout, cancellation, no concurrent physical-input actions |
| Browser policy | Block disallowed origins, redirects, popups/downloads by policy |
| Security | Model cannot set/grant own permissions, no unguarded shell tool |

## Browser integration tests (managed Chromium)

Use a local static fixture served only for tests, never live accounts. Cases:

1. Launch dedicated browser context and list page target.
2. Observe buttons, textboxes, role/name, and ref tokens.
3. Click button through snapshot ref; verify DOM state changed.
4. Fill ordinary textbox through ref; verify typed value.
5. Navigate; prove previous ref becomes stale.
6. Close tab; prove target stops working.
7. Deny popup/redirect/out-of-scope URL; deny password input.
8. Verify screenshot permission is distinct from observation.
9. Assert no personal browser profile or cookies were reused.

Run with managed fixture profiles; clean them up after tests.

## Manual Windows end-to-end scenarios (Windows 10/11 only)

Use a disposable account/VM or other controlled test environment, not production apps or personal documents.

1. **Notepad:** allowlist a test instance; observe accessible controls, focus window, safely type into an ordinary test document only after enabling interact.
2. **File Explorer:** observe and select a benign folder in an isolated test directory. Never delete/rename personal files.
3. **Legacy control:** where available, show a Win32 backend fallback and record its limitations.
4. **DPI scaling:** verify 100% and 125%/150% scaling; confirm logical vs physical pixel handling.
5. **Multiple monitors:** test off-primary monitor bounds and negative screen coordinates where applicable.
6. **Foreground change:** force a different window to the front; physical fallback must abort.
7. **OS integrity:** attempt to target elevated/UAC surface; expect refusal, not bypass.

Do not mark live Windows scenarios passing unless actually executed on Windows.

## Security-specific acceptance

- Fresh installation cannot click, type, take screenshots, or navigate to arbitrary sites until operator policy authorizes them.
- The model cannot give itself authorization via a tool parameter, webpage text, UI labels, or a target name.
- Closed/replaced windows, stale refs, invalid bounds, denylisted fields, and missing approval all fail.
- Browser navigation is constrained by configured origins and isolated context.
- No secrets or full screenshots are written to logs.
- MCP stdio stdout contains only protocol data; diagnostics use stderr.
- Unknown tools are rejected; there is no arbitrary command execution API.
- Emergency stop and timeouts interrupt action sequences.

## Suggested commands (once implemented)

~~~powershell
uv sync
uv run ruff check .
uv run pytest -q
uv run pytest -q -m browser
uv run pytest -q -m windows
uv build
~~~

Mark live test suites opt-in by default. Record environment, Python/Playwright versions, and exact failures in PR descriptions. Don't replace genuine test assertions with mocks just to get green CI.
