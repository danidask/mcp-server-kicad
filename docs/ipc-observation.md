# Experimental native IPC observation

`get_live_snapshot` extends the existing project registry (25 tools; unified
server 110). It enumerates an explicit IPC endpoint, then reads the selected
document from KiCad. The other 109 tools remain offline. No IPC writes, saves,
exports, routing, zone filling, policy persistence, or validation jobs are added.

This is partial M1 implementation. Native **headless** reads passed on Windows
with `10.99.0-5265-g0616634034`. GUI unsaved edits, repeated-sheet identity,
multiple GUI instances, and restart/busy behavior have not passed the GUI
acceptance gate. Do not describe M1 as complete or promote these bindings to a
runtime extra yet. Headless reads cannot prove GUI observation.

## What the reader returns

- Exact Python, installed binding package, generated API and connected KiCad
  versions; native document specifiers and opaque selection IDs.
- Schematic items (including native IDs, symbol fields, geometry and sheet
  paths), hierarchy and native netlist; PCB items (including footprint/pad
  geometry, copper and lock fields represented by the protocol), nets, board
  design rules and custom rules.
- A SHA-256 fingerprint of the observed JSON fields. Numeric values retain
  protobuf JSON conventions, including strings for 64-bit nanometer values.

The fingerprint is not a complete design revision or an approval baseline.
Unknown native protocol fields can be omitted. Dirty state and live ERC/DRC
are unsupported; returned rule settings do not constitute DRC execution.
Sections that fail are reported as errors, not substituted with disk data.
Two full consecutive reads plus re-enumeration must agree. This detects
observed changes, but is not an atomic snapshot and cannot rule out intervening
changes that return to the same state. Requests are serialized within this
server process, with no persistent design cache or automatic operation retry.

## Pinned dependencies and provenance

The concrete missing capability is observing native document state without
reading its disk file. We use the official transport/protocol, through an
explicit read-command allowlist, rather than copying editor implementation.
External sources inspected:

- [Official bindings](https://gitlab.com/kicad/code/kicad-python/-/tree/87b945a0d56b26a78bf547db9771ff9bf3a057ea),
  commit `87b945a0d56b26a78bf547db9771ff9bf3a057ea`, version `0.9.0.dev0`.
  The inspected wrapper/client code is MIT licensed; attribution remains in
  its installed package. Dependencies include protobuf, pynng, jsonschema and
  zstandard, with cffi/native transport requirements inspected in isolation.
- Protocol submodule commit `dcadf9baa30d43d7d1b3d0342345f05ec0da26e1`;
  source differs from the installed build. Protocol package initialization
  files carry GPL-3.0-or-later notices. Keep them in the separately installed
  official dependency, preserving its notices; no generated protocol or GPL
  source is copied into this MIT repository. Bundling/redistribution and any
  proposed runtime dependency need a license review before promotion.
- PyPI `0.8.0` comparator is refused: its schematic wrapper imports hierarchy
  response messages absent from its generated protocol. Wrapper presence
  alone does not establish a usable schematic API.

The pinned upstream Windows build left generated `from common...`,
`from board...`, and `from schematic...` imports unqualified. The build helper
repairs only these generated imports to `kipy.proto.*` and regenerates the
wheel RECORD hashes. The source archive lacks Git metadata, so upstream's
generated `KICAD_API_VERSION` is `unknown`; this is reported honestly, not
replaced with the connected build. Source commits and per-protocol-file hashes
are recorded separately in `build-evidence.json`. The locally tested repaired
wheel SHA-256 is
`94bf53f89b4797c57bee489f482f18f2fc164bc4509eda5d9eed45b3467d076b`.
Wheel archive timestamps/build dependencies can change that hash on rebuild;
record each artifact and freeze its environment. This is an investigation
recipe, not a reproducible KiCad installer or production dependency lock.

## Isolated build and native check

From the repository, in PowerShell, choose a **new** disposable output folder:

```powershell
$ipcBuild = Join-Path $env:TEMP 'kicad-ipc-observation-build'
uv run --frozen python tools/ipc_observation/build_bindings.py --output $ipcBuild
uv venv --python 3.13 "$ipcBuild/env"
$ipcPython = Join-Path $ipcBuild 'env/Scripts/python.exe'
uv export --frozen --all-extras --no-hashes --no-emit-project --output-file "$ipcBuild/server-requirements.txt"
$ipcWheel = (Get-ChildItem -LiteralPath "$ipcBuild/wheels" -Filter '*.whl').FullName
uv pip install --python $ipcPython -r "$ipcBuild/server-requirements.txt" $ipcWheel
uv pip install --python $ipcPython --no-deps -e .
uv pip freeze --python $ipcPython | Set-Content -Encoding utf8 "$ipcBuild/installed-requirements.txt"
$env:KICAD_IPC_NATIVE = '1'
& $ipcPython -m pytest tests/test_ipc_native.py -q
Remove-Item Env:KICAD_IPC_NATIVE
```

This downloads immutable official source commits and builds outside the
checkout. The helper refuses an existing output folder. Native tests explicitly
opt in and fail if prerequisites are missing; otherwise they skip. They launch
only disposable headless instances, verify the exact native version, read
known KiCad/kiutils fixtures and check unchanged design bytes. They bootstrap
tokens only for their own new test processes. Production observation does not
bootstrap or guess an instance. The main `uv.lock` remains unchanged.

Observed on 2026-10-12: **3 native tests passed**, covering schematic IDs,
reference/value/coordinates, hierarchy, native net membership, PCB footprint
coordinates/trace width/net/rules, repeatability, unchanged files and wrong-token
rejection. **145 focused unit/registry/schema/metadata tests passed**. Changed
Python files pass ruff lint/format and pyright. Full suite, nightly, KiCad 9/10
gates and the GUI acceptance procedure were not run for this change.

## Selecting and observing a GUI document

Enable the IPC API in the intended editor. KiCad sets `KICAD_API_SOCKET` and
`KICAD_API_TOKEN` when launching a plugin. Arrange for the MCP server process
to inherit that instance's environment through a local launcher; keep tokens
out of tool arguments, chat, shared configuration and evidence logs. Endpoint
topology between manager, standalone schematic and PCB editors still needs
measurement. Observe each explicitly selected endpoint separately.
See the [official connection and plugin launch documentation](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/).

1. Launch this checkout's server using the isolated environment's
   `mcp-server-kicad` executable. `uvx --from mcp-server-kicad` uses the released
   package and will not expose this new tool.
2. Call `get_live_snapshot(document_type="schematic")` (or `"pcb"`) without
   a document ID. An explicit `ipc://` endpoint can override the environment.
   The reader never guesses the default pipe or picks the first document.
3. Select the returned document ID and its `identity.project.path` directory.
   Pass both as `document_id` and `expected_project` in the next call. Missing,
   duplicated or wrong-project identities are refused. Instance-token mismatch,
   unsupported native calls and busy/connection/timeouts produce sanitized errors
   without a file fallback. Transport connections close after each observation.
4. On a disposable GUI project, capture A, make manual edits without saving,
   then capture B. Check stable IDs, changed values/geometry/connectivity and
   unchanged design-file digests. Repeat with a second instance, restarted
   server/editor, modal dialogs and a repeated child sheet. This procedure
   remains **not run**; record exact pins before claiming live GUI compatibility.

The IPC reader does not reroute legacy file tools. A successful observation
does not authorize writing the files of an open editor. The shared mutation
policy and transaction/undo work remain M2/M3.
