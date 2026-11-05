# Development, Packaging, and Distribution

## Platform

Initial development and live native automation: **Windows 10/11**, Python **3.12+**, PowerShell, uv. A GPU and LLM credentials are not required for the MCP server itself.

## Bootstrap (for Codex to implement)

~~~powershell
winget install --id=astral-sh.uv -e

# From repository root, once pyproject.toml is created:
uv sync
uv run playwright install chromium
uv run pytest
uv run ruff check .
uv run computer-use-mcp
~~~

Do not execute these commands expecting a working app yet: the repository currently contains **documentation only**.

If initializing locally, use **uv init --package** and adapt the generated metadata rather than creating a second nested project. The installed wheel must expose the console script **computer-use-mcp** from the package **computer_use_mcp**.

## Proposed dependencies

Runtime: mcp>=2,<3, pydantic, playwright>=1.64, pywinauto (Windows only), mss, pyautogui (opt-in fallback). Dev: pytest, pytest-asyncio, ruff. Codex must verify current compatible versions and pin/lock with uv, rather than treating these as a completed pyproject.toml.

## MCP entry point and stdio

The current MCP SDK uses:

~~~python
from mcp.server import MCPServer

server = MCPServer("computer-use-mcp-server")

@server.tool()
def health_check() -> str:
    return "ready"

def main() -> None:
    server.run(transport="stdio")
~~~

This is an API illustration, **not** shipped application code. Confirm tool discovery and transport against the installed SDK. On stdio, stdout is reserved for JSON-RPC messages: never print debug output or progress bars there. Log to stderr.

## Project organization

~~~text
src/computer_use_mcp/
  server.py
  core/{models,targets,refs,policy,dispatcher,errors}.py
  backends/{base,windows_uia,windows_win32,browser}.py
  fallback/{screenshots,input}.py
  tools/{observation,interaction}.py
tests/{unit,browser,windows}/
docs/
AGENTS.md
README.md
pyproject.toml
uv.lock
~~~

This layout is a starting convention; favor coherent boundaries over dogmatic folder creation. Don't create empty placeholder modules without functionality.

## Dependency and quality workflow

~~~powershell
uv add "mcp[cli]" pydantic "playwright>=1.64" mss
uv add --dev pytest pytest-asyncio ruff
uv run playwright install chromium
uv run pytest -q
uv run ruff check .
uv build
~~~

Add pywinauto and PyAutoGUI using platform-appropriate markers or optional extras after testing on Windows. Keep uv.lock versioned. Avoid mixing pip installs into the uv environment.

## Developer testing rules

- Unit tests run with fake adapters and do not depend on local windows.
- Browser tests use a dedicated temporary context/profile and local fixture.
- Windows tests are opt-in and run against a test account/VM.
- CI should run unit/browser checks on supported runners and platform-gate Windows-specific code.
- Credentials, cookies, screenshots, personal documents, and build artifacts must not be committed.

## PyPI distribution (future)

PyPI is the package registry; **pip/uv are installers**. Once the package is ready, its wheel can be built via uv build and, with explicit user approval, published using uv publish with GitHub Actions Trusted Publishing.

Potential consumer commands **after publication**:

~~~powershell
uvx computer-use-mcp-server
uv tool install computer-use-mcp-server
~~~

Package name and entry-point name are separate; verify the PyPI project name is available before committing to it. Make the package clearly Windows-first in classifiers/documentation. Playwright's browser binaries may require a one-time setup command such as **uvx --from computer-use-mcp-server playwright install chromium** or a documented application bootstrap; validate the precise installed CLI experience before release.

## Important upstream references

- https://py.sdk.modelcontextprotocol.io/
- https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/whats-new.md
- https://playwright.dev/python/docs/api/class-page
- https://docs.astral.sh/uv/
- https://pywinauto.readthedocs.io/

Do not publish to main PyPI, run uncontrolled GUI actions, or modify a user's personal browser profile while merely setting up the development environment.
