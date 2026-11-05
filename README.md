# computer-use-mcp-server

A Python MCP server for local Windows computer control, built one small tool
at a time. Requires Windows, Python 3.14+, and uv.

Implemented: server status, computer information, resource usage, primary screen
dimensions, mouse cursor position, monitor geometry, and opt-in screenshots as MCP tools.
Allowed-window and active-window discovery are implemented; accessibility and
input actions are planned.

## Tool roadmap

These are the functions an MCP client can ask the server to run. We build and
exercise one at a time. A planned row describes future work, not a working tool.

### Working tools

| Tool | Purpose | Where it lives |
| --- | --- | --- |
| `get_screen_size()` | Read the primary display's width and height | `src/tools/desktop.py` |
| `get_mouse_position()` | Read the cursor's x/y coordinates | `src/tools/desktop.py` |
| `take_screenshot()` | Return an opt-in PNG of the primary display | `src/tools/screenshot.py` |
| `list_monitors()` | List display positions, dimensions, and the primary display | `src/tools/monitors.py` |
| `computer_get_status()` | Report readiness, registered tools, and local permissions | `src/tools/status.py` |
| `get_computer_info()` | Read OS, architecture, CPU model, and core counts | `src/tools/system.py` |
| `get_computer_resources()` | Measure CPU use, RAM, and system-disk usage | `src/tools/system.py` |
| `computer_list_targets()` | List locally allowed Windows application windows with opaque IDs | `src/tools/targets.py` |
| `get_active_window()` | Identify the focused allowed target, or return null | `src/tools/targets.py` |

### Planned tools, in suggested build order

| Order | Tool | What we need to build |
| --- | --- | --- |
| 1 | `computer_observe()` | Read an allowed target's accessibility tree and issue element refs for one observation |
| 2 | `focus_window()` | Bring an allowed window to the foreground and verify its identity |
| 3 | `computer_click()` | Activate an observed element after validating target, permission, and ref freshness |
| 4 | `computer_type()` | Fill an identified ordinary text field, with length limits and protected-field checks |
| 5 | `computer_press_keys()` | Send an allowed key or shortcut to the selected target |
| 6 | `computer_scroll()` | Scroll an allowed target by a bounded amount |
| 7 | `browser_open()` | Open approved URLs in a dedicated browser context and add managed browser target discovery |
| 8 | `computer_screenshot()` | Capture an approved window or browser target with separate screenshot permission |
| 9 | `move_mouse()` | Optional physical-input fallback within an approved target, with bounds and focus checks |
| 10 | `computer_double_click()` | Double-click a fresh, permitted element reference |
| 11 | `computer_drag()` | Drag between validated elements or bounded fallback coordinates |
| 12 | `computer_wait()` | Wait for a bounded time or an expected state before observing again |

`take_screenshot()` is our learning tool for the primary display.
`computer_screenshot()` is the future target-specific version. Accessibility
operations come before physical mouse/keyboard fallback. Browser targets will
reuse the observation and interaction tools through a browser adapter.

Screenshot improvements are also planned: target/region capture, optional
downscaling, image-size metadata, and explicit image-to-desktop coordinate
mapping. Resizing screenshots must not silently change how input coordinates
are interpreted. Headless desktops, recording, installers, and cross-platform
input are possible later projects, outside the current Windows v0.1 scope.

### Supporting functions we also need

These are internal Python helpers, not extra tools the agent can call directly.

| Area | Functions and behavior to build |
| --- | --- |
| Targets | Discover windows, register targets, and detect closed or replaced targets |
| Permissions | Load local operator policy; check target, operation, and browser origin on every request |
| Element refs | Issue refs, resolve them, and reject expired, stale, or cross-target refs |
| Coordinates | Check monitor/target bounds and convert logical, physical, and browser coordinates |
| Focus | Verify the foreground target and abort fallback input if focus changes |
| Execution | Serialize Windows actions on an owned worker; manage browser startup and cleanup |
| Verification | Observe the result of an action and report unverified outcomes honestly |
| Errors and logs | Return clear safe errors; log operation outcomes without private content |
| Stopping | Bound timeouts, support cancellation, and provide a local emergency stop |

This roadmap covers the initial Windows + isolated-browser prototype. The
details of the planned target-based API are in [Tool Contracts](docs/TOOL_CONTRACTS.md).

### Reference projects

These projects inform the tool inventory and setup experience; the current
implementation remains Python with local permissions and opaque target IDs.

| Reference | Useful design examples |
| --- | --- |
| [anaisbetts/mcp-computer-use](https://github.com/anaisbetts/mcp-computer-use) | Rust action API, separate/batched action surfaces, and screenshot coordinate scaling |
| [codingmachineedge/lowlevel-computer-use-mcp](https://github.com/codingmachineedge/lowlevel-computer-use-mcp) | Window information tools, local HTTP clients, and documented desktop workflows |
| [domdomegg/computer-use-mcp](https://github.com/domdomegg/computer-use-mcp) | A compact mouse/keyboard/screenshot API implemented with nut.js |

## Project structure

```text
computer-use-mcp-server/
  server.py           # Creates the MCP server, registers tools, and starts it
  demo_client.py      # HTTP client that connects to the running server
  src/
    __init__.py       # Makes src a Python package
    logging_config.py # Shared stderr logging setup
    core/
      __init__.py
      policy.py       # Operator-owned application allowlist
      targets.py      # Opaque IDs, process identity, and expiry
    backends/
      __init__.py
      windows.py      # Native top-level window discovery
    tools/
      __init__.py
      desktop.py      # Windows screen and cursor tools
      monitors.py     # Display positions and dimensions
      screenshot.py   # Opt-in screenshot tool returning an MCP image
      status.py       # Readiness, registered tools, and local permissions
      system.py       # Computer facts and resource usage
      targets.py      # Allowed target listing and active-window information
  tests/              # Permission, limits, and MCP image tests
  docs/               # Design and implementation plans
  pyproject.toml      # Project metadata and dependencies
  uv.lock             # Resolved dependency versions
```

For the two-terminal demo, run `uv run server.py --http` first, then
`uv run demo_client.py` in another terminal. All tool
implementations live under `src/tools/`. To call desktop functions directly,
import them from `src.tools.desktop`.

## Lesson 1: read the screen size

Our first tool is `get_screen_size()`. It returns the primary display's width
and height in Windows desktop coordinates. Windows display scaling may affect
these coordinates; physical screenshot pixels and multiple displays come later.

Install the dependencies and call the Python function directly in PowerShell:

```powershell
uv sync
uv run python -c "from src.tools.desktop import get_screen_size; print(get_screen_size())"
```

Follow the code across the modules:

1. In `src/tools/desktop.py`, `ctypes` lets Python call native Windows functions.
2. In `server.py`, `MCPServer("computer-use")` creates the server.
3. `mcp.tool()(get_screen_size)` registers the existing function as a tool an
   agent can discover and call. This is the same registration as `@mcp.tool()`,
   applied separately so the desktop functions do not depend on MCP.
4. `get_screen_size()` calls Windows and returns a Python dictionary. Its return
   annotation describes the result; its docstring explains the tool to agents.
5. In `server.py`, `mcp.run(transport="stdio")` handles MCP messages through
   standard input/output.

The MCP SDK handles protocol messages and serialization for us. The function
body handles the Windows operation.

## Run the server and client in separate terminals

In terminal 1:

```powershell
uv run server.py --http
```

Leave it running. It listens at `http://127.0.0.1:8000/mcp` and shows server
startup, tool activity, and HTTP request logs in this terminal.

In terminal 2:

```powershell
uv run demo_client.py
```

The demo connects to that server. It does not start another server or stop the
existing one when it exits. Client logs and results appear in terminal 2.
Stop the server with Ctrl+C in terminal 1. Restart it after editing Python code.

For window discovery, open the application first and add `--allow-app` when
starting the server. For example, with Notepad open:

```powershell
uv run server.py --http --allow-app notepad
```

Repeat the option for additional running apps. The server resolves each app
name to one exact executable path; multiple matching paths are rejected as
ambiguous. You can also pass an absolute `.exe` path. This grants read-only
window discovery for that server session, not screenshot or input permission.

HTTP is opt-in and fixed to loopback. Plain `uv run server.py` still uses stdio
for MCP harnesses and opens no listening port. That mode waits for protocol
messages on stdin; the HTTP demo cannot connect to a standalone stdio process.
Avoid `print()` inside the server: stdout carries MCP messages in stdio mode.

For a harness that accepts `mcpServers` configuration:

```json
{
  "mcpServers": {
    "computer-use": {
      "command": "C:\\computer-use-mcp-server\\.venv\\Scripts\\python.exe",
      "args": ["C:\\computer-use-mcp-server\\server.py"]
    }
  }
}
```

Run `uv sync` first and adjust the absolute paths if you move the project.

## Lesson 2: read the mouse position

Try the second implemented tool directly:

```powershell
uv run python -c "from src.tools.desktop import get_mouse_position; print(get_mouse_position())"
```

## Lesson 3: call the tools through MCP

Keep `uv run server.py --http` running in terminal 1. In terminal 2:

```powershell
uv run python demo_client.py
```

The demo connects to the running server over Streamable HTTP, discovers its
tools, and calls the read-only tools with empty argument dictionaries. It prints
tool errors as errors rather than treating them as successful results. Closing
the client connection leaves the server running.

In `demo_client.py`, `await` waits for each server response, and
`async with Client(...)` manages the connection's lifetime. Client output is
printed to its own terminal; server logs stay in the server terminal.

## Lesson 4: capture a screenshot

`take_screenshot()` returns an MCP image, rather than a dictionary. It uses
[MSS](https://python-mss.readthedocs.io/stable/) to capture the primary Windows
display, encodes it as PNG bytes in memory, and returns the SDK's
[Image helper](https://py.sdk.modelcontextprotocol.io/servers/media/).

Screenshots require separate local permission. The server checks its own
`COMPUTER_USE_ALLOW_SCREENSHOTS` environment variable; tool arguments cannot
enable this permission. The normal demo only calls the desktop metrics tools.

To enable screenshots, set permission in the **server terminal before starting
the server**. Stop any existing server first, then run in terminal 1:

```powershell
$env:COMPUTER_USE_ALLOW_SCREENSHOTS = "1"
uv run server.py --http
```

In terminal 2:

```powershell
uv run demo_client.py --screenshot
```

Setting the environment variable only in terminal 2 does not grant the server
permission. The server has its own process environment. To disable permission,
stop the server, run `Remove-Item Env:COMPUTER_USE_ALLOW_SCREENSHOTS` in terminal 1,
then restart it.

The demo receives the image and saves it as `screenshots/screenshot.png`.
This folder is ignored by Git. The
server itself does not save screenshots. Without permission, the tool returns
`PERMISSION_DENIED` before opening the capture backend.

This learning tool captures the whole primary display, including visible
private content. It does not yet support selecting a window or cropping.
Screenshots use physical pixels, which can differ from the desktop coordinate
units returned by the other tools when Windows display scaling is enabled.
The limits are 16 million pixels and 10 MiB of encoded PNG data.

Run the checks without capturing your real screen:

```powershell
uv run python -m unittest discover -s tests -v
```

Tests use a synthetic image. A live Windows screenshot is a separate manual check.

## Lesson 5: list connected monitors

```powershell
uv run python -c "from src.tools.monitors import list_monitors; print(list_monitors())"
```

Each result contains `index`, `left`, `top`, `width`, `height`, and `is_primary`.
Coordinates use physical pixels; a display left of the primary display may have
a negative `left`. Monitor indices are local to the current result, not stable
IDs. No screenshot permission is needed because this reads geometry only. The
demo also calls this tool by default and prints its MCP result under `result`.

## Lesson 6: check server status

With `uv run server.py --http` running in terminal 1, run in terminal 2:

```powershell
uv run demo_client.py
```

The demo calls `computer_get_status()` first. Its result contains:

- `status`: `ready` means the server can respond, not that desktop APIs were tested.
- `desktop_supported`: whether this is a Windows process; interactive desktop access is not probed.
- `available_tools`: the current registered tool names, including status itself.
- `permissions.screenshots`: whether the local screenshot environment flag is exactly `1`.
- `permissions.interaction`: always `false` until guarded input actions are implemented.

The function reads no screen content or private system details. The SDK supplies
its `ctx` argument internally; the client still calls it with `{}`. That context
lets it read the server's actual tool registry without a duplicated list.

## Lesson 7: computer information and resources

`get_computer_info()` describes the computer: OS name/release/version, CPU
architecture and model, and physical/logical CPU core counts. If a CPU detail
cannot be determined, that field is `null` rather than an invented value.

`get_computer_resources()` reports a live snapshot: CPU usage sampled over
0.1 seconds, memory total/available/used, and the system disk's total/used/free
space. Size fields end in `_bytes`; percentage fields range from 0 to 100.
For display, divide bytes by `1024 ** 3` to get GiB. Other drives, GPU metrics,
and per-process resource usage are not included yet.

Both tools are read-only and require no screenshot permission. They return no
username, hostname, network address, serial number, process list, or file paths.
They use Python's `platform` module and [psutil](https://psutil.io/).

Try them directly:

```powershell
uv run python -c "from src.tools.system import get_computer_info; print(get_computer_info())"
uv run python -c "from src.tools.system import get_computer_resources; print(get_computer_resources())"
```

Or restart `uv run server.py --http` in terminal 1, then run
`uv run demo_client.py` in terminal 2. The demo calls both new tools, and server
status automatically includes them in its registered tool list.

## Lesson 8: discover allowed application targets

`computer_list_targets()` returns `target_id`, `name`, and `kind` for visible,
titled windows from allowed executables. The default result is an empty list:
no apps are allowed until the local operator configures them. Browser targets
are not implemented; requesting `kind="browser"` returns `UNSUPPORTED`.

For a manual Notepad check, open Notepad first. Stop the running server, then
run this command in the server terminal:

```powershell
uv run server.py --http --allow-app notepad
```

In the client terminal:

```powershell
uv run demo_client.py
```

This grants discovery of windows from that exact executable path, including
their titles; it grants no clicks, typing, screenshots, or other interactions.
The startup flag resolves the running app to a full executable path and adds
it to the local allowlist. If the app is not open or the name resolves to
multiple executables, startup fails with a clear error. This resolution is only
available to the local operator at startup, never as an MCP permission argument.

Advanced setup can still use `COMPUTER_USE_ALLOWED_APPS`, a JSON array of up to
32 absolute `.exe` paths in the server environment. Wildcards and invalid paths
are rejected. Existing environment grants are preserved when `--allow-app` adds
another app. Restart the server after changing either configuration source.

The registry keeps matching IDs while the same window/process identity is
rediscovered, with a 60-second idle expiry. Closed windows, revoked apps, and
observed process replacements lose their previous IDs. No handles, PIDs,
executable paths, or process creation times are returned. Output is limited to
100 targets and 200 characters per name; logs contain counts, not window names.

This is discovery only. Future observation/actions must revalidate targets;
these IDs are not permission grants. Win32 metadata alone cannot reliably
detect a window handle destroyed and reused inside the same still-running
process between discovery calls. Accessibility identity checks are still
needed before we implement actions.

To revoke application discovery, stop the server and restart without the
`--allow-app` option. If you previously set the advanced environment variable,
remove `Env:COMPUTER_USE_ALLOWED_APPS` in the server terminal as well.

## Lesson 9: identify the active allowed window

`get_active_window()` returns the same `target_id`, `name`, and `kind` used by
target listing. It refreshes discovery and checks that focus did not change
during the query. Its MCP result is wrapped under `result`, containing either
the target or `null`.

If your terminal is focused and only Notepad is allowed, `null` is expected.
The tool does not reveal the identity of unapproved foreground applications.
It never focuses, opens, or changes a window. The demo calls it automatically.

## Logging

The server and demo client use Python's built-in `logging` module. No extra
dependency is needed. `src/logging_config.py` configures INFO-and-above messages
with a timestamp, level, module name, and message. Both processes log to stderr
in their own terminals. The demo does not redirect or relay server logs.

Server startup, shutdown, tool calls, and failures are logged. Desktop results
and cursor coordinates are not included in application log messages. The demo
still prints tool results to its own stdout for learning; the server reserves
stdout for MCP messages. Logs are not automatically saved to files.

Run `uv run server.py --http` in terminal 1 for `computer_use.server` and
`src.tools.*` logs. Run `uv run demo_client.py` in terminal 2 for
`computer_use.client` logs and results. If the server is not running, the demo
exits with a message asking you to start it.

## Next lessons

Next, implement allowed target observation before input actions.
Before adding actions, introduce permission checks, bounded coordinates, and a
way to stop automation. Each tool should be understandable
as an ordinary Python function before we connect it to an agent.

Reference: [official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).
