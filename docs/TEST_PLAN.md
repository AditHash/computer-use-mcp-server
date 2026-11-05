# Testing and Acceptance Matrix

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
