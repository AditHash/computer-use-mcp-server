# Architecture

## Goal and supported environment

Build one **local stdio MCP process** that exposes a common computer-use API while delegating operating-system and browser specifics to isolated adapters. v0.1 targets Windows 10/11 interactive sessions and an **isolated Playwright Chromium profile**. This is not a remote desktop service.

The learning demo additionally supports explicit `server.py --http` startup,
using Streamable HTTP on `127.0.0.1:8000/mcp`. The demo client connects to this
existing process. It neither creates nor owns the server. Plain server startup
preserves stdio for MCP harnesses. Logs stay with the process that emits them.

## Components

~~~text
MCP Client / AI Agent
        |
        | MCP stdio (stdout reserved for protocol)
        v
MCPServer + validated tool handlers
        |
        v
Policy engine -- Target registry -- Audit sink
        |
        v
Dispatcher / reference resolver / action coordinator
        |
        +--> Desktop adapter (UIA first; Win32 as needed)
        |       +--> dedicated Windows worker / COM lifecycle
        |
        +--> Browser adapter (Playwright async API)
        |       +--> isolated browser context + pages
        |
        +--> bounded fallback: MSS screenshots, physical input
~~~

## Layer responsibilities

**MCP server:** register typed tools, validate request shape, map domain errors to safe structured results, supervise shutdown, and communicate over stdio.

**Target registry:** discover available local windows and managed browser pages; assign opaque target IDs; retain PID/process identity and browser-context ownership internally; reject expired/closed/replaced targets.

**Observation service:** request a backend-specific accessibility snapshot; normalize useful element fields (role, accessible name, value presence, enabled/visible state, bounds where supported), and return an observation revision. Never expose password values.

**Reference resolver:** issue short-lived target + revision scoped opaque refs. Resolve only refs the server issued for that exact target and revision. Re-check element identity, state, and bounds before acting. Do not rely on a Windows runtime ID remaining stable across UI mutations.

**Policy engine:** operator-owned local config; allowlisted applications and browser origins; read/write grants; risk classification; screenshot/clipboard redaction policy; deny by default; no approval through model-supplied Boolean parameters.

**Action coordinator:** one bounded operation per request, with target-specific serialization, cancellation/timeout, policy checks, stale-element handling, and clear result/error codes.

**Audit sink:** minimal records of timestamp, target alias, operation, policy decision, and result; no text typed, credentials, snapshots, or image bytes.

## Backend adapters

Define a typed abstract adapter interface with operations: list_targets(), observe(target), activate(element), fill(element, text), press_keys(target, keys), scroll(target, direction, amount), and screenshot(target). Unsupported functionality returns UNSUPPORTED rather than falling through silently.

**Windows desktop:** start with pywinauto backend="uia". Inspect native UIA attributes and supported control patterns, using programmatic Invoke/Value/Toggle where available. Use backend="win32" only for clearly recognized legacy controls. Perform UIA operations on an initialized/owned COM thread; route from async handlers using a worker and bounded requests. Do not attempt UAC/secure-desktop automation or privileged cross-integrity interactions.

**Browser:** Playwright async API. Own contexts/pages created by the server; use page.aria_snapshot(mode="ai") (Playwright >=1.64), page.get_by_ref(ref), and semantic get_by_role locators. Playwright's built-in ref is relative to its latest snapshot; **wrap** it behind the server's own target/revision contract. Use navigation, locator click/fill, and screenshot through Playwright where available, not OS mouse clicks.

**Fallback:** only after semantic interaction is unavailable and the operator enabled it. First use currently validated element bounds, then opt-in screenshot/coordinate input. Normalize Windows physical pixels versus browser CSS pixels, DPI scaling, browser viewport offsets, and multiple monitors. Check foreground target, bounds, occlusion where measurable, and user interruption.

## Observation and ref lifecycle

1. Resolve the requested target and enforce read permission.
2. Produce accessibility data and a monotonically increasing per-target observation revision.
3. Issue opaque references (for example: e_ab12) stored with target/revision/expiry and backend-native locator.
4. Action request supplies target_id, snapshot_id, and element ref.
5. Check owner, target identity, expiry, snapshot revision, element state, and policy **again** before dispatch.
6. After actions likely to change layout/navigation, invalidate previous snapshot references.
7. Return STALE_REF when old refs are used; require a fresh observe call.

Never trust a caller-provided PID or browser URL as a replacement for target ownership checks.

## Concurrency and lifecycle

- Browser operations use Playwright asyncio and explicit browser/context teardown.
- Windows operations are serialized on a dedicated worker with COM initialization and predictable cleanup.
- Global physical mouse/keyboard fallback is serialized across targets; never run concurrent physical actions.
- Bound and cancel long-running work. Closing a window, navigation, or losing focus fails safely.
- Keep the MCP server runnable without a GPU, external LLM API key, or network service listener.

## Future extensions (not v0.1)

macOS Accessibility/Quartz, Linux AT-SPI and Wayland-specific backends, remote transport with authentication, and an optional native Rust helper. Do not introduce these before the Windows + browser vertical slice is reliable.
