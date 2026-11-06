# Claude handoff: computer-use MCP prototype

Current checkpoint: 2026-11-06. Work continued in Codex after the original handoff
request. The full roadmap is still active; this file is a continuation aid.

## Repository and user preferences

- Workspace: C:\computer-use-mcp-server. Branch: feat/complete-computer-use-roadmap.
- Root server.py is the entry point; root demo_client.py is a separate client.
  Implementation modules stay in src/tools, src/core and src/backends.
- Use uv and Python 3.14.4 from the project environment. System Python may be alpha.
- Commit identity: AditHash <176161201+AditHash@users.noreply.github.com>.
- Keep commits focused. Never rewrite/reset the user's history or prior docs.
- Default stdio has no listener. --http is explicit loopback only; server and
  client logs remain in their own terminals. No personal browser profile.
- Notepad is unavailable. Native tests use our disposable windows_app.py fixture.
- No publish/release, public listener, shell/eval/file-write tool, UAC bypass,
  credential extraction or unsafe fallback. Writes require trusted local policy.

Read AGENTS.md, README.md and docs in the prescribed order before code changes.

## Implemented

21 registered tools: original nine information/discovery/screenshot tools plus
computer_observe, focus_window, computer_click, computer_type,
computer_press_keys, computer_scroll, browser_open, computer_screenshot,
move_mouse, computer_double_click, computer_drag, computer_wait.

Core: strict local TOML policy, exact control grants, opaque expiring refs,
effective policy revisions, coordinate maps, bounded dispatch, JSON stderr audit,
and latched emergency stop. Native: owned COM worker, UIA-first semantic actions,
legacy read-only observation, process/integrity/desktop/focus checks, PrintWindow,
bounded PyAutoGUI fallback with fail-safe and unconditional owned-button release.
Browser: isolated ephemeral Chromium, owner-frame-scoped refs, protected-value
redaction, approved initial redirects, blocked writes/popups/downloads/sockets.
Pending browser input watches policy every 50ms; stop closes its context.
Screenshot policy is rechecked after awaits and before image disclosure.

Mapped drag accepts optional image_points but still requires source/destination
refs, exact local grants and endpoints within those controls. Contenteditable
fill verifies actual text. Uncertain execution errors do not imply safe retry.

Packaging: setuptools wheel + source archive, computer-use-mcp = server:cli,
MANIFEST.in includes docs/example/demo/fixtures. No publication. Example policy is
safe by default; docs/OPERATOR_POLICY.md explains configuration and limitations.

## Verified evidence

See docs/TEST_PLAN.md for exact commands. Latest full run: 89 passed, six opt-in
skips, 15 subtests passed; four additional mock physical guard cases then passed.
Ruff passed. uv sync --locked and console --help passed. Rebuilt wheel installed
in .uv-cache/wheel-acceptance; its console executable passed a real stdio handshake,
discovery of all 21 tools, empty default target list and default-denied writes
with a temporary cwd outside this repository.

Real browser acceptance covers click/type/keys/scroll/focus/double-click/drag,
scaled screenshot maps and mapped drag, contenteditable, iframe refs and invalidation,
approved redirects and loop limits, blocked-origin redirects, rejected POST,
popup closure, rejected download storage, stopped pending click plus queued action,
policy revocation during pending input, and cancelled driver startup cleanup.

Native live acceptance: four tests passed. The fifth verified focus/type/keys/
scroll, then safely failed when foreground changed before pointer movement.
An isolated retry skipped because Windows refused automatic focus. Successful
native movement/double-click/drag is NOT proven. Never weaken the focus guard.
Mock tests prove recipient/cursor checks and button release on stop/focus/fail-safe.

## Remaining work

1. Positive native physical-input acceptance needs the local operator to focus
   and leave our fixture foreground. Existing async question requested this;
   no answer was received. Optional COMPUTER_USE_WAIT_FOR_FOCUS=1 waits for it.
   Run live native tests alone, without concurrent exec commands.
2. Live mixed-DPI/negative-monitor input is unverified. Validate or define and
   enforce/document an exact supported-environment limitation; do not claim it works.
3. New .github/workflows/ci.yml runs checks/build/installed-wheel tests on Windows
   and Ubuntu. Hosted execution is not yet evidence; inspect after pushing.
4. Finish the full requirement-by-requirement security/readiness audit. Check
   browser cancellation/cleanup, observation limits, target identity and native
   pattern classification. Do not mark the goal complete from tool registration.
5. Keep README, contracts, test evidence and this handoff current. Rebuild after
   code changes and verify final artifact contents. No automatic release.

Inspect git status/log before continuing. Several focused implementation commits
were created under AditHash; do not assume the older uncommitted checkpoint.
