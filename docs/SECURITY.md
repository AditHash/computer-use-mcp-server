# Security and Trust Boundaries

A computer-use MCP server is **high privilege**: it can observe private screen content and act as the interactive user. Treat it as security-sensitive infrastructure, even when launched locally over stdio.

## Threat model

Untrusted inputs include webpage text, accessibility labels, window titles, tool output, model instructions, image-derived coordinates, remote sites, and manipulated UI state. Risks include prompt injection, unauthorized clicks, credential disclosure, deceptive dialogs, stale-target races, and accidental destructive actions.

## Default policy

1. **Default deny:** on first run, no application/browser target is controlled. The local operator explicitly allowlists targets/origins and enables individual capability scopes.
2. **Read-only first:** target metadata and safe health information are available only within the configured visibility policy; accessibility inspection, screenshots, and interaction are separate grants.
3. **Mutations require trusted operator authorization:** not a field supplied by the model in a tool call. For v0.1 use locally edited policy + explicit target allowlist for low-risk UI interactions. High-impact actions are denied until a trusted, human-facing approval mechanism is implemented and tested.
4. **No broad system powers:** no shell execution, filesystem writes, arbitrary URL requests, process injection, elevated privileges, or secure-desktop interaction exposed as tools.
5. **Protected workflows:** deny credential/password fields, secrets, payment details, purchases, transfers, deletions, external submissions, browser security settings, and administrative dialogs by default. If the system cannot classify an action reliably, reject it.
6. **Isolated browser:** launch dedicated non-personal Playwright context/profile. Never attach to the user's personal authenticated browser by default. Do not share existing cookie stores.
7. **No remote listener:** stdio remains the default and opens no port. The explicitly requested `server.py --http` demo binds only to `127.0.0.1:8000`; do not expose it on a public HTTP address.
8. **Least disclosure:** limit depth/size of observations, redact likely sensitive controls, and avoid storing screen images or typed data in logs.
9. **Fail closed:** closed window, stale ref, changed PID, redirect outside allowlist, policy reload, timeout, UIA error, or missing approval all fail safely.
10. **Kill switch:** support immediate local shutdown/cancellation and honor PyAutoGUI's safety behavior; do not disable safety protections for convenience.

## Safe action policy

### Local HTTP demo

The loopback HTTP mode lets a separately started client connect while server
logs remain in the server's terminal. It is an opt-in local development mode,
not a remote service. It has no client authentication: other local processes
can reach the endpoint. Screenshot permission still defaults to disabled and
is read only from the server process environment. Client environment settings
cannot grant server permissions. Input actions remain unimplemented/disabled.

Propose a local file (for example a TOML config under the user's app-config directory) loaded by the process, **not editable through MCP tools**. Document exact schema when implemented. Permissions should be narrow: target/application identity, allowed browser origins, capabilities inspect/screenshot/interact/navigate, optional fallback enablement, and bounded limits.

Do not infer consent from an LLM saying "the user approved". Real authorization must originate outside model-controlled context. For v0.1, keep risky or uncertain operations unsupported; a future release may add native trusted confirmation UI.

## Browser constraints

- Check the URL before navigation and after redirects. Restrict popups/new pages and downloads.
- Prefer role/name/ref-based Playwright operations. Avoid exposing raw JavaScript evaluation and arbitrary CDP operations.
- Treat page content and hidden text as untrusted prompt-injection material.
- Explicitly forbid reading browser credential storage, autofill secrets, and personal profiles.
- Keep network interactions limited to approved browser origins, subject to any operational limitations documented after testing.

## Windows constraints

- Target discovery defaults to an empty application allowlist. COMPUTER_USE_ALLOWED_APPS is a server-local JSON array of absolute executable paths, not model-editable tool input. Only titles from those executables are read or returned. Discovery checks process creation time to detect PID reuse, issues expiring opaque IDs, and exposes no raw handles/PIDs/paths. This does not yet authorize observation or input; those operations still need fresh identity and permission checks, including same-process handle-reuse defenses.
- The local `--allow-app` startup option resolves an app name to one running executable path; ambiguous or missing names fail closed. This is an operator action outside MCP. The resulting policy remains exact-path based, and no tool can add applications to it. Active-window information is disclosed only for allowed targets and does not bring any application to the foreground.

- Respect User Interface Privilege Isolation, OS integrity boundaries, and the secure desktop. No UAC bypass.
- Restrict to the interactive operator's approved window identities; verify process and foreground state before physical-input fallback.
- Serialize physical input. Abort if focus changes or the human takes control.
- Review logical vs physical coordinate transforms and multi-monitor bounds before allowing coordinate clicks.

## Logging and privacy

Use stderr for protocol-adjacent logs. Record minimal structured audit events (action type, target alias, decision, result, time). Avoid passwords, typed text, page bodies, screenshots, clipboard contents, access tokens, and full exception payloads. Document retention and opt-in diagnostics if later added.

## Security acceptance tests

- Writes denied with default config.
- Deny unknown target, missing capability, stale ref, changed PID, disallowed origin and navigation redirect.
- Browser profile is isolated; cannot silently reuse an existing Chrome session.
- Sensitive controls denied; inspect/screenshot grants independently enforced.
- No MCP tool grants itself permissions or executes commands.
- Kill switch and timeout stop active action chains without unsafe retries.

**Review reminder:** UI automation cannot reliably infer every real-world consequence of clicking a button. Do not automatically authorize potentially destructive buttons solely by accessible name.
