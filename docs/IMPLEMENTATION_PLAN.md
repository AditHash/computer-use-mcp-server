# Codex Implementation Plan

Work **sequentially**, recording what is implemented and actually tested after each phase. Don't build every adapter at once. Favor a functional, secure vertical slice. Keep unimplemented APIs explicitly unavailable rather than using fake successes.

## Phase 0 — Project bootstrap and API verification

**Tasks**
- Initialize uv Python >=3.12 package with src/ layout, pyproject.toml, uv.lock, and .gitignore.
- Add project console script named **computer-use-mcp**.
- Add dependencies: official MCP Python SDK v2, Pydantic, Playwright >=1.64; optional Windows deps pywinauto, MSS, PyAutoGUI; dev deps pytest, pytest-asyncio, Ruff.
- Confirm MCPServer import and stdio run syntax against the installed SDK. Keep version constraints compatible and reproducible.
- Add minimal tests, Windows-aware CI strategy, and README commands.

**Done when:** uv sync, uv run computer-use-mcp, uv run pytest, and uv run ruff check . work on the supported environment; the process responds to MCP client discovery/handshake, and stdout has no log noise.

## Phase 1 — Typed core and read-only observation slice

**Tasks**
- Define backend interface, target registry, snapshot/ref registry, permission engine, domain error types.
- Implement computer_get_status, computer_list_targets, and computer_observe against a deterministic dummy adapter.
- Use opaque target IDs and per-target snapshot IDs; stale refs are invalidated.
- Configure deny-by-default capabilities and redact sensitive dummy fields.

**Done when:** a local MCP client can discover tools, observe the dummy target, and receive reliable typed errors. Unit tests cover authorization and stale refs.

## Phase 2 — Native Windows accessibility

**Tasks**
- Add window discovery with stable identity checks, allowlists, and explicit current-window registration.
- Add pywinauto UIA observe + activation, with Win32 fallback for supported legacy controls.
- Use a worker with COM initialization/thread ownership, serialization, and timeouts.
- Avoid elevated/UAC windows and unsafe fields; verify policy before actions.

**Done when:** a live Windows test can inspect a permitted Notepad window and activate a harmless UI control using an issued ref. Unsupported UIA patterns return clear errors. Manual Windows test instructions are committed.

## Phase 3 — Managed browser accessibility

**Tasks**
- Launch an isolated Playwright Chromium context; do not attach to a personal profile.
- Implement browser_open, browser target registration, AI ARIA snapshots, ref resolution, semantic click/fill/scroll, navigation checks.
- Handle frames, navigation invalidation, redirects, tab closure, and disallowed origin restrictions.
- Use a local deterministic test HTML page for end-to-end tests.

**Done when:** a server-owned browser tab can be observed and a safe button clicked or a normal textbox filled via its snapshot ref, with denied/expired refs failing closed.

## Phase 4 — Screenshots and bounded input fallback

**Tasks**
- Add computer_screenshot with a distinct permission and size limits.
- Add element-bound physical input first; explicit opt-in screenshot-coordinate fallback only as the last resort.
- Implement physical/logical pixel conversion, DPI awareness, monitor bounds, foreground checks, and serialization of input.
- Expose safe bounded keypress and scrolling with per-tool limits; respect cancellation and emergency stop.

**Done when:** disabled fallback is rejected by tests; allowed fallback works in an isolated desktop fixture; multi-monitor tests pass or an exact limitation is documented.

## Phase 5 — Hardening, packaging, and readiness

**Tasks**
- Test security policies, injection-resistant handling of UI labels, target changes, sensitive controls, and failure recovery.
- Add docs for MCP client integration and local policy configuration; keep stdio logs on stderr.
- Verify cold start, worker cleanup, browser shutdown, repeated observations, and basic memory/latency characteristics.
- Produce a reproducible wheel with uv build; test console entry point in a clean local environment.
- Prepare TestPyPI/PyPI checklist **without publishing** until the operator explicitly requests it.

**Done when:** docs/TEST_PLAN.md acceptance matrix passes on Windows, the README reflects actual features, and the CLI runs from the installed wheel.

## Expected deliverables

- Python source in src/computer_use_mcp/, real MCP tools and backends.
- pyproject.toml, uv.lock, type-safe request/result models, documented local policy.
- Unit tests runnable without desktop UI and opt-in Windows/browser integration tests.
- Updated docs with demonstrated commands and honest limitations.

## Definition of done for all phases

- Tests exist and their actual results are reported.
- No silent fallback to uncontrolled mouse/keyboard input.
- No action succeeds solely based on a model-provided assertion of permission.
- Errors are typed, finite, and redacted.
- No changes to public tool contracts without updating docs and tests.

## Codex kickoff instruction

Start Phase 0 immediately. Work toward the Phase 1 read-only MCP slice, then implement native and browser backends one at a time. Check installed APIs rather than copying old snippets. If a dependency is unavailable on the current OS, test with a mock adapter and clearly label Windows manual tests as **not run**.
