# Contributing

Thank you for your interest in contributing to mcp-server-kicad!

Read [AGENTS.md](AGENTS.md) and its linked [development guide](docs/development.md)
before making changes. The [co-design direction](docs/co-design.md) and
[KiCad 11 migration plan](docs/kicad11-migration.md) distinguish product goals
from implemented and verified capabilities. These instructions apply to any
coding agent or human contributor; the Claude plugin is an optional client.

## Development Setup

1. Fork and clone the repository:

   ```bash
   git clone https://github.com/<your-username>/mcp-server-kicad.git
   cd mcp-server-kicad
   ```

2. Install [uv](https://docs.astral.sh/uv/) and Python 3.13, then the locked environment with the dev extra, which is exactly what CI installs. `.python-version` selects the development baseline:

   ```bash
   uv sync --frozen --all-extras --dev
   ```

3. Run tests:

   ```bash
   uv run pytest -v -n auto
   ```

4. Run lints and the type check:

   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run pyright
   ```

To run the same ruff on every commit, install [pre-commit](https://pre-commit.com/) 4.4 or newer and run `pre-commit install`. Its hooks call `uv run`, so they use the ruff version `uv.lock` pins.

The server environment is separate from Python bundled with KiCad. Do not
install legacy `pcbnew` into the server environment or assume KiCad 11 exposes
it. Use the [pinned investigation baseline](docs/kicad11-baseline.json) when
evaluating IPC; its development binding candidate is not yet a server dependency.
Use `uv run --frozen mcp-server-kicad` to test the checkout. Published plugin,
`uvx`, and bundle configurations can run an upstream release instead.

## Workflow

1. Create a branch from `main` for your change.
2. Make your changes.
3. Add or update tests as needed.
4. Ensure tests and lints pass locally.
5. Open a pull request against `main`.

## Tests That Need KiCad

Tests that shell out to `kicad-cli` (ERC, DRC, exports) need KiCad installed, and so do the few that drive pcbnew's Python bindings. `kicad-cli` is found through `KICAD_CLI_PATH`, then your `PATH`, then `/Applications/KiCad/KiCad.app` on macOS, then the versioned install folders under `Program Files` and `AppData` on Windows. Without it those tests skip, and so does the autouse fixture that checks every generated schematic and board loads in `kicad-cli`, so a green run proves much less. Confirm it resolves before trusting one.

Record exact CLI/build and binding versions, actual passes/failures/skips, and
the checks not run. Mocked tests do not establish live GUI compatibility. Use
disposable fixtures; do not operate on an engineer's open project to test a file
workflow. M1's unsaved-edit integration procedure and acceptance criteria are
in the migration plan.
