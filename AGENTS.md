# Development instructions for coding agents

These instructions apply to any coding agent or human contributor. Read
[the detailed development guide](docs/development.md) before changing code; it
preserves the repository's architecture, testing requirements, CI/release
constraints, and measured engineering decisions. CodeRabbit explicitly uses
this file as review criteria in `.coderabbit.yaml`.

## Scope and direction

- Extend this repository; keep one coherent, provider-independent MCP interface.
  Model reasoning belongs to the external agent. Execution, validation, and
  protection policies belong in the server.
- Follow [the co-design direction](docs/co-design.md) and
  [the KiCad 11 migration plan/capability matrix](docs/kicad11-migration.md).
  Product goals are not claims of implemented capabilities. Do not implement
  later milestones unless the task authorizes them.
- Python 3.13 is the development and CI baseline. Use the locked uv environment;
  avoid unrelated upgrades. KiCad's bundled interpreter is a separate runtime.
- Inspect Git state first and preserve unrelated user changes. Do not reset,
  restore, or clean their work. Existing Claude client configurations, skills,
  hooks, and examples are optional integrations, not server requirements.

## Commands

```bash
uv sync --frozen --all-extras --dev
uv run --frozen pytest -v -n auto
uv run --frozen pytest tests/test_cst.py -v
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pyright
uv run --frozen python mcp_server_kicad/_cst.py
uv run --frozen mcp-server-kicad
```

Record baseline results before attributing failures to a change. Confirm the
resolved KiCad executable/version; tests can skip without it. A mocked test or
a green run with skipped native checks does not prove KiCad compatibility.
Report exactly what ran, failed, skipped, or was not run. See the development
guide for nightly profiles, fixtures, platform gates, and release checks.

## Architecture and preservation

- Preserve the five domain registries and unified server contracts where
  practical. Tools use `_shared.py` helpers/annotation presets and structured
  Pydantic output models. Update registry, annotation, schema, skill coverage,
  and all documented tool counts when changing the tool surface.
- Read [the CST ADR](docs/adr-cst-substrate.md) before changing any write path,
  and [the routing safety ADR](docs/adr-routing-safety.md) before connectivity
  or schematic-routing changes. Append evidence when a write path changes.
- Offline CST I/O is bytes-only. Preserve bytes outside authorized edits,
  refuse malformed/unsupported constructs, validate token-position inputs,
  and emit constructs from KiCad-harvested templates. Respect board net dialect
  gates. Use the footprint orientation/refusal helpers rather than editing an
  `(at)` alone. Drop cached trees before mutation and never cache a partial edit.
- Route package file writes through `_shared._atomic_write`; use scratch copies
  for subprocess rewrites. Atomic replacement provides per-file durability,
  not semantic correctness, conflict detection, or a multi-file transaction.
  Preserve the documented library-upgrade and routed-copy exceptions.
- Reads use `_read_kicad_bytes` or `_require_kicad_path`; output directories use
  `_ensure_dir`. Preserve actionable bad-path and process-crash contracts.
- `_netlist_import.py` must remain stdlib-only and importable by name from
  KiCad's separate interpreter while legacy subprocesses still use it.

## Safe collaboration

- Open editor state, including unsaved changes, is authoritative. Current file
  tools are offline tools. Never silently write disk files for open documents,
  or fall back from unavailable IPC to file mutation. Resolve instance, project,
  document, hierarchy, and stable identities explicitly; reject ambiguity.
- A review request is read-only unless edits are authorized. Preserve external
  changes by default; explicit authorization can permit scoped changes.
  Do not assume who authored an external edit.
- New live writes must share server policy checks for approval baselines,
  locks/protections, object/property scope, fresh preconditions, and serialized
  writes. Re-read before planning and application; mtime/size and dirty flags
  alone are insufficient. Do not expose a bypass through another tool/backend.
- Relevant schematic edits make approval stale. PCB work cannot silently change
  approved component choices or circuit topology. Long-running results must be
  checked against current state before application.
- Verify native transaction/undo boundaries on the pinned build. On timeout or
  ambiguous outcomes inspect before retry. Recovery must preserve unrelated
  edits; do not blanket-restore files, reset Git, or repeatedly undo the GUI.
- Validate semantic preservation for IPC, byte preservation for offline edits.
  ERC is schematic electrical validation; DRC is PCB rule/geometric validation.
  Compare results for the actual revision, settings, and design phase. Never
  weaken rules, add exclusions, or change intent just to pass a check.

## Testing and review

- Keep independent judges: KiCad, geometry/math, or a domain rule; do not assert
  an implementation's behavior merely because it produces that behavior.
  Preserve the test ladder, edit judges, output oracle, and strict xfail rules
  documented in the development guide.
- Use `kicad_placeholder` for named placeholder/malformed inputs.
  `no_kicad_validation` is only for tests whose subject is malformed data,
  never to hide invalid output. New write paths require preservation tests,
  native validation, and the existing KiCad 10 gate before exposure.
- Verify library IDs, pins, footprint geometry, connectivity, and validation
  evidence independently. Optional plugin reviewers are useful checklists;
  reviewer approval is not engineering approval and client hooks are not
  server-side enforcement. Unsupported operations must be reported clearly.
- External reuse needs a concrete requirement, inspected dependencies,
  source commit/license/attribution, compatibility evidence, and regressions
  before exposure. Flag license conflicts before copying code.
