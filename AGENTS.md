# Codex Instructions — Computer Use MCP Server

## Mission

Implement an **accessibility-first MCP server for Windows native applications and an isolated Chromium browser**. The repository starts with design documents only. Treat them as the product contract; implement **incrementally**, verify with tests, and report what is still incomplete.

## Read these files before coding (in order)

1. README.md
2. docs/ARCHITECTURE.md
3. docs/TOOL_CONTRACTS.md
4. docs/SECURITY.md
5. docs/IMPLEMENTATION_PLAN.md
6. docs/TEST_PLAN.md
7. docs/DEVELOPMENT.md

If requirements conflict, prioritize **SECURITY.md**, then **TOOL_CONTRACTS.md**, then **ARCHITECTURE.md**, then the implementation plan.

## Fixed initial stack

- Python >=3.12; manage dependencies, venv, locks, running, and packaging with **uv**.
- Official MCP Python SDK **v2**: use **from mcp.server import MCPServer**, not older FastMCP v1 import examples.
- pywinauto for Windows UIA/Win32; Playwright **>=1.64** for browser ARIA snapshots and refs.
- MSS for screenshots and PyAutoGUI only for bounded physical-input fallback.
- Pydantic, pytest, Ruff; use standard typing and clear dependency boundaries.
- Target **Windows 10/11** for actual desktop automation. Non-Windows CI may run pure unit tests.

## Non-negotiable design principles

1. **Observe first.** Accessibility trees and element-bound actions take precedence over screenshot guessing.
2. Keep the MCP transport, target registry, desktop adapter, browser adapter, input fallback, and policy engine separate.
3. Every mutating action requires server-side authorization. Never rely solely on the model saying it has permission.
4. Start with read-only mode. Write actions require an explicit local operator policy; sensitive actions remain denied in v0.1.
5. Element refs must be **target-scoped, revision-scoped, opaque, and expiring**. Never trust raw handles, process IDs, CSS/XPath, window titles, or arbitrary element indices from the model as authorization.
6. Validate target allowlists, URL restrictions, coordinate bounds, timeouts, input lengths, and process identity on every operation.
7. **Never** implement unguarded shell/PowerShell, process injection, arbitrary file edits, credential extraction, UAC bypass, or secure-desktop interaction as MCP tools.
8. No implicit use of the user's existing authenticated Chrome profile. Use a dedicated Playwright context/profile.
9. Logs go to **stderr**, never stdout in stdio mode. Avoid logging secrets, typed content, and raw screenshots.
10. UIA COM/thread and Playwright async lifecycles must be explicit. Avoid blocking the entire MCP event loop with desktop API calls.
11. Do not claim Windows UIA is universally effective; inaccessible controls need a deliberate, permission-checked fallback.
12. Do not publish, release, merge to another repo, or enable remote access unless the user explicitly requests it.

## Coding workflow

- Execute the phases in **docs/IMPLEMENTATION_PLAN.md** in order. Aim for a functioning thin vertical slice, not a broad untested scaffold.
- Before implementation, inspect the latest official SDK and Playwright APIs and pin compatible versions in pyproject.toml / uv.lock.
- Add failing tests for each contract, then code, then run the relevant tests. Do not fabricate test results.
- For new MCP tools, update docs/TOOL_CONTRACTS.md and add permission + stale-ref tests.
- Prefer small focused modules, typed results, explicit errors, and deterministic tests with mock adapters.
- Keep imports of Windows-only packages isolated so unit tests can run on another OS.
- Update README.md to distinguish implemented features from planned features.
- After each phase, summarize changed files, commands executed, actual results, and remaining limitations.

## Minimum completion bar for v0.1

- A pip-installable/uv-runnable local stdio MCP CLI using a Python project entry point.
- Target listing + accessibility observation for an allowed Windows window and an isolated browser tab.
- An action path that validates policies, opaque refs, and revision freshness for both backends.
- Disabled-by-default writes; safe controls that can be explicitly enabled by an actual local operator.
- Screenshot fallback only when enabled, with correct DPI/multi-monitor handling or an explicit limitation.
- Automated unit tests plus documented Windows/browser end-to-end scenarios.
- No network listener by default; no live secret-bearing sessions in integration tests.

**First coding task:** implement Phase 0 and Phase 1 of docs/IMPLEMENTATION_PLAN.md, verify a working stdio handshake and a read-only dummy target, then proceed in small verified increments.
