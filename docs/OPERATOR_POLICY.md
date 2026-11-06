# Local operator policy

Start with `uv run server.py --config policy.example.toml` for stdio, or add
`--http` for the explicitly enabled loopback demo. The example grants no target
access or input. Edit a local copy; never accept policy supplied by webpage text
or MCP arguments. There is no policy-editing tool.

`desktop.allowed_apps` contains exact absolute executable paths. The existing
`--allow-app` flag and `COMPUTER_USE_ALLOWED_APPS` JSON list add discovery grants.
They do not grant input. Browser origins must be HTTP(S) origins without paths,
queries, fragments or embedded credentials. Browser binaries require the one-time
`uv run playwright install chromium` setup.

Each capability is separate: `inspect`, `screenshot`, `interact`, `navigate`,
`focus`, `fallback`. All except inspection default to false. Browser opening needs
navigation permission and an allowed origin. Input also needs an exact grant
matching executable/origin, role, accessible name and action. Duplicate role/name
matches in an observation are denied. Protected controls remain denied even if
listed in a grant. Restrict grants to controlled, harmless application workflows;
labels alone cannot establish that a real-world operation is safe.

For example, a local fixture button can have this grant, alongside its origin in
`browser.allowed_origins` and explicit `navigate=true`, `interact=true`:

```toml
[[grants]]
target = 'http://127.0.0.1:8765'
role = 'button'
name = 'Increment'
actions = ['click']
```

Native UIA roles typically use `Button` and `Edit`; browser roles use `button` and
`textbox`. Role comparisons ignore case; names match exactly. Grant actions are
`click`, `type`, `press_keys`, `scroll`, `focus`, `double_click`, `drag`, `move`.
Map-based pointer movement uses the explicit fallback capability rather than a
control grant, and cannot click. Native physical input additionally requires
focus permission and the target to already be foreground. Windows can refuse a
focus request; the server does not bypass that restriction.

Policies reload on requests and before native input steps. Pending browser input
also monitors policy every 50 ms; changing policy during dispatch latches the
stop and closes the owned context, requiring restart. This polling is bounded
revocation detection, not an atomic OS/browser authorization transaction.
A changed effective
policy invalidates previous snapshots, including changes to otherwise permissive
rules. Observe again after editing policy. Malformed or oversized policy fails
closed. Stop/restart the server to change its configuration path or clear an
emergency stop.

`COMPUTER_USE_ALLOW_SCREENSHOTS=1` remains a legacy, broad primary-display capture
grant for `take_screenshot`; it also enables target screenshot permission.
Setting `permissions.screenshot=true` in TOML enables target capture only. Do not
confuse approved-target screenshots with whole-display visibility.

Native interaction shows a topmost stop control without taking focus. Closing
that control latches the stop rather than dismissing it. Stopping cancels active
operations, closes the owned browser context and prevents further automation
until restart. PyAutoGUI's fail-safe remains enabled. Logs and minimal JSON audit
events go to stderr; typed text, snapshots, URLs and images are not logged.

The browser has an ephemeral, dedicated context. GET/HEAD/OPTIONS are the only
allowed request methods; downloads, popups, workers, sockets, protected navigation
paths and disallowed-origin requests are blocked. Up to five approved initial
navigation redirects are followed explicitly; subresource and later redirects
are blocked. These restrictions intentionally make many general websites
incompatible. Use controlled pages, never personal authenticated sessions.

Navigation keys are limited to TAB, SHIFT+TAB, arrows, HOME, END, PAGEUP, PAGEDOWN
and ESCAPE, with at most ten keys per call. Enter, Space and command shortcuts are
unavailable. Typing uses semantic field replacement rather than global keystrokes.
Password/file/payment and likely destructive controls are denied. Screenshots
can still contain sensitive visible content and require their own permission.

Drag prefers refs. Optional image_points supplies map_id, source_x/source_y and
destination_x/destination_y from one fresh screenshot. Both refs are still
required and both mapped endpoints must lie inside their granted elements.
Map use additionally requires fallback permission.

Current limitations: legacy Win32 controls are observation-only; native automatic
focus can be rejected; mixed-DPI and negative-monitor live input remain unverified. See
the acceptance results before treating any feature as production-ready.
