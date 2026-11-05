# Proposed MCP Tool Contracts (v0.1)

The target-scoped v0.1 API below remains a **design contract**. The current
learning prototype implements the smaller tools described here first.

The same tool contracts are available over default stdio and opt-in loopback
HTTP (`server.py --http`). The demo client uses HTTP to connect to the server
started in another terminal. Permission flags always belong to the server's
environment, independently of how the client was started.

## Implemented learning tools

| Tool | Inputs | Response | Permission |
| --- | --- | --- | --- |
| get_screen_size | none | width, height in Windows desktop coordinates | read-only metrics |
| get_mouse_position | none | x, y in Windows desktop coordinates | read-only metrics |
| list_monitors | none | list of index, left, top, width, height, is_primary in physical pixels | read-only metrics; no screenshot grant needed |
| take_screenshot | none | MCP image content, MIME image/png, no structured output | local COMPUTER_USE_ALLOW_SCREENSHOTS=1 |
| computer_get_status | none | status, desktop_supported, available_tools, permissions | safe read-only status; no desktop grant required |
| get_computer_info | none | os_name, os_release, os_version, architecture, cpu_model, cpu_logical_cores, cpu_physical_cores | read-only system facts |
| get_computer_resources | none | cpu_percent, memory, system_disk | read-only system metrics |
| computer_list_targets | optional kind=desktop/browser | list of target_id, name, kind; currently desktop only | local COMPUTER_USE_ALLOWED_APPS executable allowlist |
| get_active_window | none | result containing target_id, name, kind or null | same local application discovery allowlist |

`take_screenshot` captures the entire primary display in physical pixels. It
accepts no file path, crop, target ID, or permission parameter. Permission is
checked before opening MSS, on every call. It is disabled by default. It
returns a tool error containing PERMISSION_DENIED, UNSUPPORTED,
OUT_OF_BOUNDS, or BACKEND_UNAVAILABLE when appropriate. Maximum size is
16 million pixels and 10 MiB of PNG bytes. The capture object is created and
closed within one call; image data stays out of application logs and files.

`list_monitors` reads display metadata only and never calls the capture API.
It excludes MSS's combined-desktop entry, supports negative monitor origins,
and reports a primary display. Its indices describe the current enumeration;
they are not stable target IDs. Its MCP structured output wraps the list in
`result`. Backend failure returns BACKEND_UNAVAILABLE, and other operating
systems return UNSUPPORTED.

`computer_get_status` returns `status=ready` when the server can respond; it does
not test desktop access or invoke capture APIs. `desktop_supported` indicates
Windows support. `available_tools` is read from the active MCP server registry.
`permissions.screenshots` reflects whether the same local flag used by the
screenshot tool is exactly `1`; it reports configuration, not backend readiness.
`permissions.interaction` remains false. Status itself requires no desktop grant
and remains callable on unsupported platforms. No hostname, username, paths,
environment dump, image data, or operating-system handles are returned. The SDK
injects the handler's context; it is not a client-supplied argument.

`get_computer_info` returns OS and CPU facts; unknown CPU model/core counts are
null. `get_computer_resources` samples aggregate CPU usage for 0.1 seconds and
reports `memory` (total_bytes, available_bytes, used_bytes, percent) and
`system_disk` (total_bytes, used_bytes, free_bytes, percent). Only the system
disk is measured (SystemDrive on Windows, `/` elsewhere); no path is returned.
Percentages range from 0 to 100. Memory counters retain psutil's platform
semantics; `available_bytes` represents memory available to applications.
The synchronous resource handler runs on the SDK worker thread, so its short
sampling interval does not block the MCP event loop.

Both system tools require no screenshot or interaction grant and accept no
client arguments. They expose no hostname, username, IP/MAC address, serial,
process list, or file contents. Backend failures return BACKEND_UNAVAILABLE
without internal error details. Neither tool performs a write or issues refs.

`computer_list_targets` supports omitted kind or desktop. Browser kind returns
UNSUPPORTED until a managed browser backend exists. With no local allowlist it
returns an empty list without enumerating windows. The allowlist is a JSON
array of at most 32 absolute Windows `.exe` paths in COMPUTER_USE_ALLOWED_APPS;
comparisons normalize case and separators. Malformed policy fails closed with
INVALID_ARGUMENT; unsupported desktop backends return UNSUPPORTED, and native
enumeration failure returns BACKEND_UNAVAILABLE.

Window titles are read only after executable permission checks. The registry
then checks permission again before returning up to 100 targets with names
limited to 200 characters. IDs are random, server-owned, and expire after 60
seconds without rediscovery. Discovery identity includes the internal handle,
PID, process start time, executable, and window class. Those details are never
returned. Observed closed/revoked/replaced entries are removed. Listing is not
an authorization capability for actions. Same-process window-handle reuse
between scans remains a limitation requiring future accessibility validation.

For easier operator setup, `server.py --allow-app notepad` resolves a running
app name to a single exact executable path and adds that path to the existing
server-local allowlist. Repeated flags are supported. Missing/ambiguous matches
fail before the server listens; full paths undergo the same policy validation.
No partially resolved selection is applied. CLI selection is not an MCP tool
and does not grant screenshots or interaction.

`get_active_window` reads the foreground handle internally, refreshes allowed
target discovery, and verifies unchanged focus and policy before returning the
matching opaque target. Null is a successful result for an unapproved window,
missing foreground window, focus change, or empty policy. The structured result
is `{result: target-or-null}`. No raw handle, PID, or executable path is returned.
Expired registry entries cannot be matched. This has the same discovery-only
identity limitations as target listing and does not authorize any action.

No current tool issues element refs, so element stale-ref checks do not yet
apply. Target identity expiry/replacement and permission revocation are tested.
The prototype has a discovery registry, but target-specific observation and
action authorization are not implemented. Enabling the existing screenshot
tool still authorizes the whole primary display for that server process; it is
separate from both this allowlist and the planned `computer_screenshot` API.

## Common types

- **target_id**: server-issued opaque identifier. One target is one allowed Windows top-level window or one managed browser page.
- **snapshot_id**: server-issued, per-target revision token returned by observe.
- **ref**: opaque element reference from the specified snapshot. Ref alone is not an authorization token.
- **state**: enabled, visible, role, accessible name, optional rect; never expose secure input field values.
- **rect**: explicit coordinate space: screen_physical_pixels, screen_logical_pixels, or browser_css_pixels. Do not mix them.
- **result**: status, target_id, action, observation_invalidated, optional safe message; no secrets.

## Tool inventory

| Tool | Inputs | Response | Permission |
| --- | --- | --- | --- |
| computer_list_targets | optional kind=desktop/browser | opaque target IDs, names, kinds | inspect |
| computer_observe | target_id, optional max_depth | snapshot_id, accessibility text/tree, refs | inspect |
| computer_screenshot | target_id, optional crop | MCP image content + metadata, never local secret file paths | screenshot |
| computer_click | target_id, snapshot_id, ref | action result | interact |
| computer_type | target_id, snapshot_id, ref, text | action result | interact |
| computer_press_keys | target_id, keys | action result | interact |
| computer_scroll | target_id, snapshot_id, optional ref, direction, amount | action result | interact |
| browser_open | approved URL or approved page creation parameters | managed browser target_id | navigate |
| computer_get_status | no input | health + safe capabilities; no sensitive environment data | inspect |

**Do not add** generic execute_command, eval_javascript, arbitrary HTTP fetch, clipboard dump, keylogger, or unrestricted filesystem operations to v0.1.

## Example observation (illustrative)

~~~json
{
  "target_id": "t_b42",
  "snapshot_id": "s_17",
  "kind": "browser",
  "title": "Example",
  "elements": [
    {
      "ref": "e_3f",
      "role": "button",
      "name": "Save",
      "enabled": true,
      "visible": true
    }
  ]
}
~~~

Browser observations may also include Playwright's AI ARIA snapshot as text. Convert its native refs to server-issued target/revision scoped refs. Desktop observations use pywinauto/UIA and map into the same normalized structure.

## Example action (illustrative)

~~~json
{
  "target_id": "t_b42",
  "snapshot_id": "s_17",
  "ref": "e_3f"
}
~~~

Only the server determines whether this represents a permitted Save button in the selected application. **The action must fail** if a page navigated, the reference expired, the target was switched, the element is disabled, or permission was revoked.

## Structured errors

Use stable error codes with safe, actionable text:

- TARGET_NOT_FOUND / TARGET_NOT_ALLOWED
- PERMISSION_DENIED / APPROVAL_REQUIRED
- STALE_REF / ELEMENT_NOT_FOUND / ELEMENT_NOT_INTERACTABLE
- UNSUPPORTED / INVALID_ARGUMENT / OUT_OF_BOUNDS
- TARGET_NOT_FOREGROUND / OS_PERMISSION_BOUNDARY
- TIMEOUT / CANCELLED / BACKEND_UNAVAILABLE / INTERNAL_ERROR

Do not include full traces or sensitive OS paths in tool responses; send redacted diagnostics to stderr as appropriate.

## Semantics

- Observe is read-only. It must avoid reading password field values, but **can** reveal sensitive labels or page text; permission checks and output limits still apply.
- Screenshots are sensitive; require their own grant rather than automatically piggybacking on inspect.
- computer_type should only fill an identified, non-secret input control by default; password fields, token fields, payment inputs, and other sensitive fields are denied for v0.1.
- computer_press_keys must use a constrained allowlist (e.g., navigation keys); block arbitrary key sequences that launch system utilities or bypass scope.
- Browser navigation must use a configured allowed-origin list and guard redirects, pop-ups, and downloads.
- Restrict text length, snapshot depth, screenshot size, scroll counts, and per-action timeouts.
- For physical input fallback, require explicit operator opt-in and target focus verification before interaction.
- Never claim action success from the absence of an exception; verify observable state when feasible, otherwise report EXECUTED_UNVERIFIED.

## Versioning

### Additional planned primitives

The README reference review adds planned element-bound double-click and drag,
plus a bounded wait tool. They are not registered or implemented yet. Screenshot
downscaling will require explicit source/image dimensions and coordinate
mapping, with freshness and target checks before any physical-input fallback.

Stabilize schemas before the first PyPI release. Any breaking tool-name or response change requires contract tests, README updates, and a documented release note.
