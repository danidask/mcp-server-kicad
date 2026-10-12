# KiCad 11 foundation audit and migration plan

Status: foundation audit plus experimental read-only IPC follow-up, 2026-10-12.
The original audit below remains historical evidence; the follow-up is recorded
in [ipc-observation.md](ipc-observation.md). It adds a read-only backend and
`get_live_snapshot` (110 total tools; project registry 25), with native headless
reads verified and GUI unsaved-state acceptance still not run. No live design
mutation or design policy service is added. Product requirements are in
[co-design.md](co-design.md); durable development rules are in
[AGENTS.md](../AGENTS.md) and [development.md](development.md).

## Audited checkout and architecture

Audit starts at `486364b2eb50a21102deee91c60493de4eb70437` (package `0.20.1`).
The initial working state contains one staged user change: `.gitignore` adds
`tmp_*.*`. Preserve its bytes and staged state. The audit describes this
checkout, not the upstream README or a PyPI installation.

`server.py` merges five `MCPServer` registries via the private tool manager;
there are 109 tools (schematic 42, PCB 34, project 24, symbol 5, footprint 4).
`models.py` supplies structured schemas. `_shared.py` supplies paths, annotation
presets, subprocess handling, and atomic replacement. No runtime module imports
an LLM SDK or requires a model provider. Runtime dependencies are MCP and
typing-extensions (with MCP's transitive dependencies); kiutils is a dev fixture
and independent test oracle, not the runtime parser.

File tools use `_cst.py` and shared byte readers/writers. Schematic wiring uses
`_connectivity.py`, with preservation/connectivity evidence in
[adr-routing-safety.md](adr-routing-safety.md). `_netlist_import.py` provides
stdlib-only helpers, including the wx initialization that legacy scripts import
by name. There is no IPC import/backend, persisted approval baseline, common
authorization service, or live-document target registry.

Current auto-discovery chooses the highest versioned Windows CLI installation.
That is useful offline executable discovery, but cannot resolve the intended
live instance. Defaults are resolved at import from parameters/environment or a
single project in cwd. PCB CST caching uses mtime and size. None of these proves
that an open GUI document or relevant unsaved state is current.

## Pinned investigation baseline

[kicad11-baseline.json](kicad11-baseline.json) records immutable source identities
and the installed binary digest. These are investigation pins, not a declaration
that the combination has passed GUI integration or a new server dependency.

| Component | Exact baseline / evidence | Qualification |
|---|---|---|
| Server | Python 3.13; dependencies in `uv.lock` | Separate from KiCad's Python; local interpreter is CPython 3.13.15 |
| KiCad Windows development build | `10.99.0-5265-g0616634034`, built 2026-10-12 07:34:13; source `0616634034fa1a8c92c141c293342cbef2f68dff` | Installed under `C:/Program Files/KiCad/10.99`; this is development toward 11, not a released 11.0 |
| Official bindings candidate | `kicad-python` source `87b945a0d56b26a78bf547db9771ff9bf3a057ea`, declaring `0.9.0.dev0` | Inspected source only; not added to server dependencies or integration-tested |
| Candidate protocol submodule | KiCad source `dcadf9baa30d43d7d1b3d0342345f05ec0da26e1` | Different from installed KiCad commit; wire/semantic compatibility must be tested |
| Released bindings comparator | PyPI `kicad-python==0.8.0`, built against `10.0.6-0-gcaf7377e9c` | Wheel inspected and installed in an isolated Python 3.13 environment; not assumed equivalent to development docs |

The installed CLI's `version`, `version --format commit`, and
`version --format about` establish the exact build. Its executable SHA-256 is
`aae90c59af9737060aa2f7b5d005486f3b444d6b99420d7ca07ef8bccb904f95`.
It lists `api-server`, and that command's help accepts an optional project,
board, or schematic plus `--socket`. Help is evidence of command availability,
not proof of all headless operations. Repository pcbnew discovery returns
`(None, None)` and `pcbnew_major()` returns `None`. The install includes Python
3.12 DLLs, which do not establish a usable pcbnew interpreter.

Do not install a moving nightly or an unpinned bindings branch. For a repeatable
IPC experiment, use the recorded KiCad source/build and bindings commit plus
its protocol submodule. Before promoting it to a runtime extra, build and hash
the wheel, lock all transitive dependencies, record its generated API version,
and pass the GUI acceptance tests below. The original installer URL/hash is
not available from this checkout; the CLI digest identifies this local binary
but does not reproduce the entire distribution. Archive/hash the exact
installer and library payloads or publish a pinned source-build recipe before
introducing a KiCad 11 CI gate. That reproducibility gap is explicit.

## Official API evidence and limitations

The [IPC overview](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/) and
[add-on documentation](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/)
were consulted on 2026-10-12. They distinguish KiCad 9/10 GUI-only PCB IPC from
KiCad 11 schematic, export, and headless extensions, and warn that development
bindings documentation can exceed PyPI releases. Windows uses named pipes;
plugin-launched endpoint/token environment variables identify an instance.
Do not log tokens or guess the default endpoint in a multi-instance workflow.

Concrete candidate methods were checked in immutable official source:

- [bindings `kicad.py`](https://gitlab.com/kicad/code/kicad-python/-/blob/87b945a0d56b26a78bf547db9771ff9bf3a057ea/kipy/kicad.py):
  `get_open_documents`, `get_version`, `get_api_version`, `ping`, `get_schematic`,
  headless startup, and headless document open/close are present. Convenience
  `get_board()`/`get_schematic()` choose `docs[0]`; our backend must enumerate and
  explicitly select instead. GUI open/close is documented as unsupported.
- [bindings `schematic.py`](https://gitlab.com/kicad/code/kicad-python/-/blob/87b945a0d56b26a78bf547db9771ff9bf3a057ea/kipy/schematic.py)
  has `get_hierarchy`, `get_items`, `get_symbols`, `get_netlist`, and export jobs.
  [schematic documentation](https://docs.kicad.org/kicad-python/schematic.html)
  labels development additions with placeholder release numbers. These are
  source/documented candidates, not a verified installed package API.
- [bindings `board.py`](https://gitlab.com/kicad/code/kicad-python/-/blob/87b945a0d56b26a78bf547db9771ff9bf3a057ea/kipy/board.py)
  has board item/net/rule inspection, `refill_zones`, and `import_netlist`.
  [board documentation](https://docs.kicad.org/kicad-python/board.html) describes
  busy/refill polling. Lock enforcement, scoped import effects, and transaction
  boundaries still need experiments on the installed build.
- Installed-build source handlers
  [schematic](https://gitlab.com/kicad/code/kicad/-/blob/0616634034fa1a8c92c141c293342cbef2f68dff/eeschema/api/api_handler_sch.cpp)
  and [PCB](https://gitlab.com/kicad/code/kicad/-/blob/0616634034fa1a8c92c141c293342cbef2f68dff/pcbnew/api/api_handler_pcb.cpp)
  register schematic hierarchy/netlist/export and PCB items, rules,
  refill/import/export handlers. This corroborates implementation in the source
  matching the local commit; no GUI behavior is inferred from registration.
- Neither inspected handler nor candidate wrapper exposes an identified ERC/DRC
  execution job. Exports and design-rule getters are not validation jobs.
  Retain CLI validation for isolated revision-consistent copies pending a
  verified live validation path. Do not invent `Schematic.run_erc()`.
- The [legacy bindings notice](https://dev-docs.kicad.org/en/apis-and-binding/pcbnew/)
  states SWIG removal is planned for KiCad 11. We measured discovery failure
  here; do not equate that with proving absence from every KiCad 11 build.

The editor handlers answer their own document types. M1 must verify the actual
manager/standalone editor endpoint topology rather than assume one endpoint
can inspect both editors; support an explicitly associated schematic/PCB
target pair if needed, validating that both belong to the intended project.

The released 0.8.0 wheel contains a `Schematic` class and schematic query
methods, but its `KiCad` class lacks `get_schematic()` and the `headless`
constructor parameter shown in development source. Its generated protocol
version is KiCad 10.0.6. Presence of schematic Python code does not prove a
working GUI schematic API. The candidate development build adds protobuf,
pynng, jsonschema, and zstandard dependencies; its package build regenerates
protos from the KiCad submodule. Both Python and native transport compatibility
must be verified, not inferred from `requires-python >=3.9`.

## Initial compatibility matrix

Status columns are independent: **I** = current implementation, **U** = existing
unit/fixture coverage, **N** = real KiCad 11 native/GUI integration. Test file
presence establishes coverage exists, not that a run passed. Local results are
recorded below. No row currently has verified live GUI integration.

| Tool family and source anchors | Current backend | Proposed backend | I / U / N; known gaps |
|---|---|---|---|
| Schematic inspection: `get_schematic_summary`, `list_schematic_*`, `get_symbol_pins`, `get_pin_positions`, `get_net_connections` — `schematic.py:183–584`, `_connectivity.py` | CST + local geometry/connectivity | IPC selected schematic, hierarchy and netlist | Yes / `test_read_tools`, `test_connectivity`, routing oracles / GUI not run; disk excludes unsaved edits |
| Schematic edits: placement, properties, wires/labels/junctions, power/no-connect/text, `wire_pins_to_net`, `connect_pins` — `schematic.py:584–2146` | CST + templates + deterministic wiring planner | Scoped IPC items behind policy service | Yes / write, routing, validity, ladder tests / live unsupported; no common protection/approval boundary |
| Schematic validation and unconnected pins — `schematic.py:2177`, `run_erc:2263` | CLI ERC on file | Verified live job if available; otherwise consistent isolated snapshot + CLI | Yes / `test_cli_analysis`, routing oracles / one native CLI fixture passes on pinned development build; live ERC not verified; no identified IPC ERC job |
| Schematic exports/netlist/BOM — `schematic.py:2322`, `project.py:1615` | CLI exports | IPC export jobs where verified | Yes / CLI export tests / candidate handlers inspected; unsaved export consistency not tested |
| Project creation and library-table scaffolding — `project.py:160–255` | CST files + project JSON | Explicit offline creation; later verified document operations | Yes / `test_project_tools` / GUI open/create coverage not assumed |
| Hierarchy reads/validation/instances/cross-sheet nets — `project.py:795–1197` | CST + `_connectivity.py` | IPC hierarchy, sheet paths and connectivity | Yes / project/connectivity/hierarchy tests / repeated-sheet identity must be tested |
| Hierarchy mutations, annotation, reorder/duplicate/flatten — `project.py:256–794,1198–1614` | CST, sometimes multiple files | Scoped IPC with explicit multi-document boundaries | Yes / `test_new_sch_tools`, project and preservation tests / not atomic across files; live equivalents unverified |
| PCB inspection — `pcb.py:1866–2117` | CST | IPC Board queries on explicit document | Yes / `test_pcb_read_tools` / no unsaved state; cache mtime+size is not conflict protection |
| Footprint placement/move/removal — `pcb.py:2118,2669,2816`; orientation helpers | CST + harvested libs + transform helpers | IPC items and native transformations gated by server protections | Yes / placement and R2/R3 tests / `move_footprint` does not refuse native locks |
| Placement/bounds/board checks — `check_placement:2772`, `get_footprint_bounds:5134`, `validate_board:5186` | CST deterministic geometry | Geometry over live snapshot + native DRC evidence | Yes / geometry/PCB tests / `check_placement` checks origin rather than full courtyard; not a complete legal-placement solver |
| Copper/zone/keepout/text/graphic edits and cleanup — `pcb.py:2831–3134,3314–3493,3592` | CST | Scoped IPC items with shared policy | Yes / PCB write/validity tests / no universal copper protection or scoped authorization |
| Net classes — `set_net_class`, `pcb.py:3494` | Direct `.kicad_pro` JSON atomic replacement | Verified project/rule IPC; offline JSON for closed projects | Yes / PCB write tests / does not round-trip full custom rule/differential/length policy |
| Zone fill — `fill_zones:3135`, `_FILL_ZONES_SCRIPT` | pcbnew subprocess `LoadBoard`, `ZONE_FILLER`; CST applies computed fill | IPC `Board.refill_zones` candidate | Yes / fill/freerouting/ladder tests / usable pcbnew not found here; IPC effects/timeouts untested |
| Schematic→PCB sync — `update_pcb_from_schematic:3187`, `_apply_netlist_cst`, `_netlist_import.py` | CLI netlist + CST import (not pcbnew) | Live approved netlist + verified IPC import/diff | Yes / `test_netlist_import`, R3 swap tests / locks preserve swap/deletion, but fields/nets still update; Component Class and variants gaps documented in tool |
| PCB DRC/exports — `pcb.py:4433–4800` | CLI DRC and PDF/SVG/DXF/Gerber/drill/3D/positions/IPC-2581 exports | Verified IPC export jobs; CLI validation on consistent copies | Yes / CLI, DXF, IPC-2581 tests / no identified IPC DRC job; open-state/settings capture unverified |
| Autorouting — `autoroute_pcb:4963`, `_freerouting.py` | CST keepout promotion → pcbnew DSN → Java Freerouting → pcbnew SES/SaveBoard routed copy → CST text repair, optional CLI DRC | One internal router backend; verified transport + scoped live application | Yes / `test_freerouting` mainly mocks / legacy discovery fails; latest-release auto-download unpinned; custom-rule/pair/length fidelity and protected-copper preservation unverified |
| Symbol and footprint library reads/authoring — `symbol.py:190–415`, `footprint.py:75–167` | CST/library templates | Keep explicit offline library workflows; verified IPC library access where appropriate | Yes / symbol/footprint/library tests / document/library target and live library editing not verified |
| Library SVG/upgrade — `symbol.py:416–end`, `footprint.py:168–end` | CLI SVG; scratch-copy upgrade, bounded backup and atomic landing | Retain explicit offline upgrades; IPC export only if verified | Yes / access/helper/validity tests / per-file atomicity, not whole-library transaction; no implicit live rewrite |
| Jobsets/version — `project.py:1715,1730` | CLI jobset/version | IPC version/capability diagnostics; jobset offline until effects constrained | Yes / CLI analysis tests / arbitrary jobset side effects need the future common policy boundary |

## Safety and client-workflow audit

`_atomic_write` is valuable per-file durability and preservation infrastructure;
it does not serialize semantic operations or prevent overwriting changes made
after a read. `_BOARD_CACHE` can miss equal-size/equal-mtime external edits.
Reference-based tool contracts also need stable identity/hierarchy support.
`move_footprint` and other general writers do not share `_fp_locked` checks;
netlist swap/deletion uses that helper but still updates locked footprints'
fields/nets. Placement edge/keepout checks are advisory. Routing reloads its
input for SES import after a long external job without verifying an unchanged
semantic snapshot. The routed copy can overwrite an existing output, and DRC
is optional. None establishes the required protected incremental-routing
contract. Do not run these paths against an open project as a live workaround.

| Existing check/workflow | What it actually enforces | Agent-independent equivalent or gap |
|---|---|---|
| `hooks/hooks.json` PreToolUse | Blocks Claude Read/Write/Edit by KiCad extension | Host-specific only; shell/other clients are outside it. AGENTS applies the rule to contributors; shared server policy is still required for all MCP writes |
| `hooks/session-start` | Injects `skills/using-kicad/SKILL.md` into Claude sessions | Optional context injection; generic clients need durable documentation and server capabilities/errors, not a mandatory Claude Skill tool |
| Six `skills/*` files | Datasheet/library verification, planning, reviewer gates, ERC/DRC/export workflow | Preserve useful checklists; client dispatch is optional. Review remains read-only; scope approval and phase-aware validation must move to common server policy |
| `agents/bom-reviewer.md`, `schematic-plan-reviewer.md`, `code-reviewer.md` | Independent library, pin/math/plan, and code-quality review instructions | Usable by any reviewer; reviewer verdict is not the user's engineering approval. Persist evidence/approval separately |
| `.pre-commit-config.yaml` | Locked uv ruff lint/format | Already client-independent; preserved |
| `.coderabbit.yaml` | Review criteria from configured guideline documents | Explicit `AGENTS.md` and `docs/development.md` patterns verified against official schema; original detailed review rules remain selected. Hosted PR ingestion not tested locally |
| pytest output/preservation/geometry/connectivity judges and CI | Offline validity, durability, independent semantics and platform gates | Retain; add pinned GUI tests for unsaved changes, identity, protections, stale plans, and failures |

The optional plugin's full-design pipeline and zero-violation manufacturing
gates cannot replace incremental scope authorization or phase-aware review.
Its source currently speaks in terms of Claude `Skill`, `Task`, and `TodoWrite`;
those integrations remain optional and are not made server requirements.

## Migration sequence and decisions for review

1. **Read-only live observation (M1, partial).** `_ipc.py` and
   `get_live_snapshot` now provide explicit enumeration and native observation
   within the five existing registries. Headless schematic/PCB reads and token
   rejection passed on the pinned build; the GUI criteria below remain open.
   See [setup, provenance and current evidence](ipc-observation.md).
2. **State/policy foundation (M2).** Propose project-side storage, semantic
   fingerprints, persistent operation IDs, approval staleness, protected
   object/net/property scopes, and all-write enforcement. Inventory every
   legacy entry point so none bypasses policy. Add stale/ambiguous-outcome tests.
3. **One scoped mutation (M3).** Verify native transaction semantics and handoff
   boundaries, then implement one authorized edit with preservation/conflict
   evidence. Expand to schematic approval and PCB synchronization only afterward.
4. **Placement and routing (M4+).** Deterministic geometry and current-state
   snapshots precede an internal router. Pin its binary/hash and map supported
   rules before any protected incremental routing is exposed.

Proposals needing the engineer's approval before implementation:

- A project-associated `.kicad-mcp/` sidecar with versioned policies, approval
  baselines, scoped plans, operation journal, and evidence references; decide
  what is shared in Git versus local endpoint/session data. Never store tokens
  in shared policy/history.
- Explicit per-request/session live targets and capability negotiation, with
  separate offline mode. Preserve old tool names where practical, but open or
  unresolved documents must not receive implicit disk writes. Decide the
  deprecation path for path-only mutation contracts.
- A small backend API (target resolution, capabilities, semantic snapshot,
  validation snapshot, scoped application), with all writes passing a common
  policy service. Version conditions remain there, not in each MCP tool.
- Promote the recorded development bindings candidate only after M1 passes;
  then add a pinned optional dependency/wheel and reproducible Windows KiCad 11
  CI artifacts. Retain existing 9/10 offline gates rather than replacing their
  evidence with an unverified nightly gate.

Python development and CI use 3.13 exclusively. Packaging retains the >=3.13
floor, with only 3.13 advertised and tested. This is a packaging change,
not a change to KiCad's bundled interpreter. Tool schemas/contracts are otherwise
preserved in this foundation iteration.

## M1 acceptance criteria and reproducible local procedure

The smallest complete milestone is to identify the intended KiCad instance,
inspect its open schematic and board, then observe subsequent unsaved manual
edits. A CLI version probe alone is insufficient.

Acceptance criteria:

- An explicit endpoint/token plus expected project/document identity resolves
  the target. Enumeration rejects missing/ambiguous/wrong documents and never
  selects `docs[0]` implicitly. Token changes/restarts invalidate the session.
- Diagnostic output records exact server Python, binding package/source and
  generated protocol version, connected KiCad version/build, document
  identities/types/hierarchy, and tested capabilities. Tokens are redacted.
- Read live schematic symbols, hierarchy and connectivity; read board
  footprints, pads, nets, tracks/vias, native locks, and relevant rules where
  actually supported. Unsupported fields are explicit; never substitute disk
  data while presenting it as a live observation.
- Take fresh snapshots before/after a manual symbol-value/wire change and a
  footprint-position change **without saving**. Report the actual changed
  identities, fields, geometry and connectivity; unchanged objects retain
  identity. Assert disk digests remain unchanged during unsaved observations.
- Reconnect/restart the MCP client and repeat observation; open a second KiCad
  instance and prove explicit targeting/ambiguity refusal. Missing IPC fails
  clearly without a file fallback. No design mutator is exposed by this probe.
- Commit disposable fixture/evidence tooling and integration results tied to
  the exact pins. Unit mocks cover errors but cannot satisfy the GUI criteria.

Local procedure for M1 (not an assertion that this foundation supplies it):

1. Reproduce/hash the pinned KiCad distribution and bindings wheel; install the
   latter with pinned dependencies in a Python 3.13 uv environment. Compare its
   generated protocol version with the selected build and record differences.
2. Copy representative schematic/hierarchy/PCB/project/rule/library fixtures to
   a disposable directory. Open both editors in the intended instance and
   enable the IPC API. Record their initial disk digests.
3. Obtain endpoint/token through the chosen KiCad IPC launch mechanism; pass
   them explicitly to the diagnostic without writing tokens to logs. Use
   `get_open_documents` for each type and construct document-scoped wrappers
   from the matched specifiers rather than convenience first-document getters.
4. Capture snapshot A. In the GUI change a component value and connectivity,
   then move a footprint, leaving all unsaved. Capture B and assert semantic
   differences/identity and unchanged disk digests. Save, capture C, and verify
   the expected saved transition without treating serialization noise as edits.
5. Repeat after client restart and with a second instance. Exercise wrong
   project/document, disconnected endpoint, unsupported capability, and busy
   editor errors. Preserve all evidence and exact versions; GUI skips are skips.

Headless IPC may provide useful automated read fixtures after verifying it on
isolated copies, but cannot prove that GUI unsaved edits are observed. No GUI
instance was running during this foundation audit, and the M1 GUI demonstration
is **not run**.

## Foundation commands and results

All tests use disposable fixtures, not an engineer's project. Existing 9/10 CI
configuration is evidence of intended gates, not proof of runs here. No new
tests or backend behavior were added; the Python/configuration changes are
checked by existing metadata, schemas, registry, and client-artifact tests.

The completed focused command before migration was:

```powershell
uv run --frozen pytest -q -ra tests/test_config.py tests/test_packaging_metadata.py tests/test_skills.py tests/test_skill_tool_coverage.py tests/test_tool_schemas.py tests/test_tool_annotations.py tests/test_server_instructions.py tests/test_unified_server.py tests/test_mcpb_manifest.py
```

| Check actually run | Outcome |
|---|---|
| `git status --short`, staged diff, source/history/instruction/CI inventory | Original commit recorded above; staged `.gitignore` preserved; no commit or engineer-project mutation |
| Original `uv sync --frozen --all-extras --dev`, interpreter/CLI/pcbnew probes | Python 3.10.20 environment synced; exact CLI build found; usable pcbnew interpreter not found |
| Original focused pytest command above | **218 passed, 1 skipped**, 10.14 s; skip is executable-mode check on Windows |
| Original `ruff check .`, `ruff format --check .`, `pyright`, CST self-check | Lint/format passed; pyright **0 errors, 62 warnings**; `cst self-check OK` |
| Original `pytest -n 4 -q -ra`, then `pytest -n 8 -q -ra -x` | Both deliberately interrupted after slow native runs; failure/error indicators appeared before interruption. No full-suite verdict. Forced worker shutdown messages are interruption artifacts, not additional compatibility findings |
| Original focused native/CST attempt: `pytest -n 4 -q -ra tests/test_cli_analysis.py tests/test_cli_sch_export.py tests/test_cli_pcb_export.py tests/test_cst.py tests/test_cli_resolution.py` | Interrupted; no complete native-subset verdict |
| `git archive` of original HEAD, isolated original `uv sync --frozen --all-extras --dev`, `pytest -q tests/test_cli_resolution.py::test_stock_install_resolves_pcbnew` | **1 failed** on original Python 3.10.20: CLI found, pcbnew interpreter absent. This isolates the same pre-existing assumption exposed on 3.13 |
| `uv lock`; old/new package-version-set comparison | No introduced package versions; obsolete `exceptiongroup`/`tomli` and unused lock branches/artifacts pruned. Existing supported Windows 3.13 package versions retained |
| New `uv sync --frozen --all-extras --dev`, `uv run --frozen python -c "import sys; print(sys.version)"`, `uv lock --check` | Locked environment built successfully on **CPython 3.13.15**; lock check passes. Initial replacement was blocked by VS Code services; moving the old environment aside allowed the rebuild |
| New focused command above **plus `tests/test_cli_resolution.py`** | **235 passed, 1 failed, 1 skipped**, 5.23 s. The failure is `test_stock_install_resolves_pcbnew`, reproduced on the unmodified original checkout; not hidden or marked passing |
| New extended focused command above plus `tests/test_cst.py` and `tests/test_cli_resolution.py` | Interrupted during the native CST cases; no complete verdict; not a passing integration run |
| `uv run --frozen pytest -q -ra tests/test_cli_analysis.py::TestRunErc::test_clean_schematic` | **1 passed**, 11.49 s, on exact KiCad development build above; tests CLI report production and fixture loading only, not functional circuit correctness or GUI unsaved state |
| New `uv run --frozen ruff check .`, `ruff format --check .`, `pyright`, CST self-check | Lint/format passed; pyright **0 errors, 59 warnings**; `cst self-check OK` |
| Isolated `uv venv --python 3.13`, `uv pip install ... kicad-python==0.8.0`, import/signature inspection | Install/import succeeds (including native pynng/cffi dependencies); released API differs from development candidate. No GUI IPC query performed |
| Official docs/source/schema downloads; CLI help/version/hash; baseline JSON, local documentation-link and instruction-preservation checks; `git diff --check` | Pins/links valid; engineering guidance retained with documented adaptations; whitespace check passed. CodeRabbit schema supports the explicit patterns; hosted ingestion not tested |

Logs and the isolated original checkout are in
`%TEMP%/kicad-foundation-20261012/`. An ignored, partially removed old environment
remains at `tmp_foundation.venv`: automatic approval review rejected both
recursive cleanup and bounded named-file cleanup, reporting only “blocked by
policy.” The active `.venv` is the rebuilt Python 3.13 environment.

Not run: GUI IPC/unsaved manual-edit demonstration, candidate 0.9.0.dev0 package
build/runtime checks, locked-placement/protected-copper live tests, policy and
recovery integration, nightly Hypothesis profile, Python 3.14 locally, other
platforms or hosted CI/reviewer workflows. The full native suite has no completed
passing result here. Further native error indicators from interrupted runs
have not been individually diagnosed. Do not certify KiCad 11 compatibility
for all 109 tools from this foundation evidence.

## Files changed and substantive adaptations

| Files | Purpose |
|---|---|
| `CLAUDE.md` → root `AGENTS.md`; `docs/development.md` | Agent-neutral durable instructions; original detailed architecture/tests/CI/release guidance preserved in the linked guide |
| `docs/co-design.md`, this plan, `docs/kicad11-baseline.json` | Product direction separated from implementation claims; source-backed backend matrix, immutable investigation pins, gaps, approval decisions, and M1 acceptance criteria |
| `docs/adr-cst-substrate.md` | Add scope clarification: byte identity remains mandatory offline; live IPC needs semantic preservation, without rewriting historical evidence |
| `README.md`, `CONTRIBUTING.md` | Lead with generic local-checkout usage, state current offline limitations, document Python baseline and optional published client integrations |
| `.coderabbit.yaml` | Explicitly select both concise instructions and preserved detailed review criteria |
| `skills/using-kicad/SKILL.md` | Preserve optional plugin workflow; remove false universal-capability claim and clarify read-only reviews/scoped incremental authorization |
| `.python-version`, `pyproject.toml`, `uv.lock` | Python 3.13 development/floor/lint/type baseline; preserve locked dependency versions without unrelated upgrades |
| Six `.github/workflows/*.yml` | Server Python 3.13 selected across lint/native/nightly/release/platform workflows; retain existing KiCad 9/10 gates |
| `mcpb/pyproject.toml`, `mcpb/manifest.json` | Bundle runtime requirement agrees with server floor; placeholder release versions unchanged |
| `mcp_server_kicad/models.py`, `mcp_server_kicad/pcb.py`, `tests/test_ladder_r1_tokens.py` | Only docstrings/comments: remove stale supported-Python claim and update instruction filename; executable behavior unchanged |

No optional Claude configuration file, plugin identifier, hook event, or client
environment variable is renamed. Preservation and validation rules are retained;
the substantive policy clarification is that client workflow/reviewer gates are
not server enforcement or engineering approval. Raising the runtime floor to
3.13 is the only intentional compatibility break in this iteration.
