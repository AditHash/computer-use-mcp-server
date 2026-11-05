# computer-use-mcp-server

A Python MCP server for local Windows computer control, built one small tool
at a time. Requires Windows, Python 3.14+, and uv.

Implemented: primary screen dimensions, mouse cursor position, monitor geometry, and opt-in
primary-display screenshots as MCP tools. Accessibility and input actions are planned.

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

### Planned tools, in suggested build order

| Order | Tool | What we need to build |
| --- | --- | --- |
| 1 | `computer_get_status()` | Report server health, supported features, and which permissions are enabled |
| 2 | `computer_list_targets()` | Discover allowed application windows and managed browser tabs; assign target IDs |
| 3 | `computer_observe()` | Read an allowed target's accessibility tree and issue element refs for one observation |
| 4 | `focus_window()` | Bring an allowed window to the foreground and verify its identity |
| 5 | `computer_click()` | Activate an observed element after validating target, permission, and ref freshness |
| 6 | `computer_type()` | Fill an identified ordinary text field, with length limits and protected-field checks |
| 7 | `computer_press_keys()` | Send an allowed key or shortcut to the selected target |
| 8 | `computer_scroll()` | Scroll an allowed target by a bounded amount |
| 9 | `browser_open()` | Open an approved URL in a dedicated browser context owned by the server |
| 10 | `computer_screenshot()` | Capture an approved window or browser target with separate screenshot permission |
| 11 | `move_mouse()` | Optional physical-input fallback within an approved target, with bounds and focus checks |

`take_screenshot()` is our learning tool for the primary display.
`computer_screenshot()` is the future target-specific version. Accessibility
operations come before physical mouse/keyboard fallback. Browser targets will
reuse the observation and interaction tools through a browser adapter.

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

## Project structure

```text
computer-use-mcp-server/
  server.py           # Creates the MCP server, registers tools, and starts it
  demo_client.py      # Example client that launches and calls the server
  src/
    __init__.py       # Makes src a Python package
    logging_config.py # Shared stderr logging setup
    stdio_transport.py # Forwards child-server logs to the demo terminal
    tools/
      __init__.py
      desktop.py      # Windows screen and cursor tools
      monitors.py     # Display positions and dimensions
      screenshot.py   # Opt-in screenshot tool returning an MCP image
  tests/              # Permission, limits, and MCP image tests
  docs/               # Design and implementation plans
  pyproject.toml      # Project metadata and dependencies
  uv.lock             # Resolved dependency versions
```

Run from the repository root with `uv run python server.py`. All tool
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

## Run as an MCP server

```powershell
uv run python server.py
```

This waits for an MCP client. It is not an interactive terminal prompt. Press
Ctrl+C to stop it. Avoid `print()` inside the server: stdout carries MCP messages.

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

```powershell
uv run python demo_client.py
```

There is no need to start `server.py` separately. The demo starts it as a child
process using the same Python interpreter, connects over stdio, discovers the
tools, and calls both with empty argument dictionaries. It prints tool errors
as errors rather than treating them as successful results. When the connection
closes, the child server is shut down.

In `demo_client.py`, `await` waits for each server response, and
`async with Client(...)` manages the connection's lifetime. Client output is
printed to its own terminal; the server's stdout remains reserved for MCP.

## Lesson 4: capture a screenshot

`take_screenshot()` returns an MCP image, rather than a dictionary. It uses
[MSS](https://python-mss.readthedocs.io/stable/) to capture the primary Windows
display, encodes it as PNG bytes in memory, and returns the SDK's
[Image helper](https://py.sdk.modelcontextprotocol.io/servers/media/).

Screenshots require separate local permission. The server checks its own
`COMPUTER_USE_ALLOW_SCREENSHOTS` environment variable; tool arguments cannot
enable this permission. The normal demo only calls the desktop metrics tools.

To enable screenshots for a demo session in PowerShell:

```powershell
$env:COMPUTER_USE_ALLOW_SCREENSHOTS = "1"
uv run python demo_client.py --screenshot
Remove-Item Env:COMPUTER_USE_ALLOW_SCREENSHOTS
```

The demo forwards this permission to its child server, receives the image, and
saves it as `screenshots/screenshot.png`. This folder is ignored by Git. The
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

## Logging

The server and demo client use Python's built-in `logging` module. No extra
dependency is needed. `src/logging_config.py` configures INFO-and-above messages
with a timestamp, level, module name, and message. Both processes log to stderr.
`src/stdio_transport.py` forwards the child server's stderr through the demo
process so its logs are visible in the same terminal, including on Windows.

Server startup, shutdown, tool calls, and failures are logged. Desktop results
and cursor coordinates are not included in application log messages. The demo
still prints tool results to its own stdout for learning; the server reserves
stdout for MCP messages. Logs are not automatically saved to files.

The demo launches its own stdio server. A server started manually in a separate
terminal does not receive the demo's calls. Run `uv run demo_client.py` and watch
that terminal for both `computer_use.server` and `computer_use.client` messages.

## Next lessons

Add and exercise one function per lesson: mouse movement, clicking, and typing.
Before adding actions, introduce bounded
coordinates and a way to stop automation. Each tool should be understandable
as an ordinary Python function before we connect it to an agent.

Reference: [official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).
