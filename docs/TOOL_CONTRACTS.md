# Proposed MCP Tool Contracts (v0.1)

The target-scoped v0.1 API below remains a **design contract**. The current
learning prototype implements the smaller tools described here first.

## Implemented learning tools

| Tool | Inputs | Response | Permission |
| --- | --- | --- | --- |
| get_screen_size | none | width, height in Windows desktop coordinates | read-only metrics |
| get_mouse_position | none | x, y in Windows desktop coordinates | read-only metrics |
| list_monitors | none | list of index, left, top, width, height, is_primary in physical pixels | read-only metrics; no screenshot grant needed |
| take_screenshot | none | MCP image content, MIME image/png, no structured output | local COMPUTER_USE_ALLOW_SCREENSHOTS=1 |

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

These tools issue no element refs, so stale-ref checks do not apply. This
prototype does not implement the planned target registry or per-window
authorization; enabling screenshots authorizes the whole primary display for
that server process. It is separate from the planned `computer_screenshot` API.

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

Stabilize schemas before the first PyPI release. Any breaking tool-name or response change requires contract tests, README updates, and a documented release note.
