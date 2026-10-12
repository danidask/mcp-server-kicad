# Human–AI co-design direction

This fork extends mcp-server-kicad into one agent-agnostic MCP server for
incremental electronic design with KiCad 11 development builds, initially on
Windows. Python 3.13 is the server development baseline. The engineer retains
control, and reasoning stays in the external agent; the server executes,
validates, and enforces design policies without requiring an LLM provider.

This is a product direction, not a description of capabilities already shipped.
The 109 existing file tools operate offline; `get_live_snapshot` adds
experimental read-only IPC observation ([setup and evidence](ipc-observation.md)).
Unsaved GUI edits remain unverified. See [the migration plan and capability
matrix](kicad11-migration.md) for evidence, gaps, and the next bounded milestone.
Keep the existing unified interface and file-preserving implementation; do not
replace this project wholesale or require users to operate a second routing MCP
server.

## Alternating engineering turns

1. **Schematic collaboration.** Create or improve an authorized block. After the
   engineer edits values, symbols, wiring, labels, hierarchy, or annotation,
   inspect the actual current document and explain implications. Review is
   read-only unless modifications are authorized. Never regenerate an old
   schematic over newer work.
2. **Approval and synchronization.** Explicit engineering approval freezes a
   particular schematic revision. Record its semantic baseline, including
   component choices, hierarchy, and connectivity. PCB tasks cannot alter that
   intent. Relevant subsequent edits make approval stale; preserve those edits
   and require renewed approval. A PCB synchronization preserves existing
   placement/routing where possible and reports removals, replacements, net
   changes, and other potentially destructive effects before applying them.
3. **Placement collaboration.** Operate inside the authorized object/property
   scope and mechanical/electrical constraints. Preserve native footprint locks,
   fixed placements, orientations, and project protections. Manual edits are
   preserved by default but can be changed with explicit scope authorization;
   observing an external edit does not permanently freeze that object.
4. **Incremental routing.** Start from verified current copper and rules. Route
   only authorized nets/regions/items, preserving protected tracks and vias.
   Respect widths, clearances, allowed layers, via limits, keepouts, differential
   pairs, lengths, and applicable custom rules. A router backend must declare
   which constraints it represents; reject or explicitly gate mandatory
   unsupported constraints rather than dropping them.
5. **Durable handoff.** Project-associated storage records policies, approvals,
   baselines, authorizations, and operation evidence so restarts and new clients
   continue the same engineering work. Conversation memory is insufficient.

The initial editing model is alternating human and server turns, with serialized
server writes. Detect conflicts without claiming that preflight checks remove
all races with the GUI. Do not attribute an external change to a particular
person without evidence.

## Authoritative state and scoped operations

An open editor's state, including unsaved changes, is authoritative. Explicit
instance, project, document, and hierarchical object identity must be resolved
before inspection or planning. Never pick the first instance arbitrarily.
File workflows remain useful for closed documents and isolated offline copies;
they cannot silently substitute for a missing live capability.

Every mutating server entry point, including legacy tools and subprocess-backed
operations, must eventually share the same policy boundary:

1. Read current state and policies.
2. Build a scoped plan with preconditions and expected effects.
3. Obtain approval when existing authorization does not cover that scope.
4. Re-read relevant state and revalidate rules/protections immediately before
   application; reject plans whose assumptions are stale.
5. Apply only the authorized changes.
6. Validate and report the actual effects, provenance, and remaining violations.

Use identities and semantic state fingerprints, not just reference designators,
coordinates, file mtimes, or dirty flags. Recheck long-running placement/routing
results before importing them. Distinguish verified server-authored changes from
external changes; uncertain mutation outcomes require inspection before retry
to prevent duplicates.

## Preservation, recovery, and validation

Retain the [CST and atomic-write rules](adr-cst-substrate.md) for offline editing.
Live operations instead prove semantic preservation of unrelated objects,
connectivity, geometry, and policies; KiCad may serialize differently. Validate
native commit/undo semantics on the pinned build before relying on them. There
is no assumed transaction across schematic, board, and project settings.

Recovery cannot blanket-restore files, reset Git, or repeatedly undo the GUI:
that can erase unrelated engineering work. Multi-step operations need explicit
boundaries, recorded completed effects, and scoped reconciliation. Timeouts may
mean the change already happened, so inspect before retrying.

ERC checks schematic electrical rules. DRC checks PCB design rules and geometric
constraints. Evidence must identify the reviewed revision and applicable
settings; CLI or temporary-copy validation must consistently represent unsaved
documents, hierarchy, libraries, and project rules. Compare pre/post results for
the current phase: an unfinished board can legitimately have unrouted nets.
Never weaken rules, insert exclusions, or change circuit intent merely to make
validation pass. Passing ERC/DRC is necessary evidence, not proof of functional
correctness or manufacturing readiness.

Use deterministic geometry/connectivity/routing execution and independent
validation. Placement must consider the actual outline, courtyards, keepouts,
protected positions/orientations, and user constraints. The LLM selects intent
and strategy; it is not the geometric validity oracle.

## Selective reuse and compatibility

For each external addition, first record the missing capability and acceptance
criteria, then inspect its implementation/dependencies. Record repository,
commit, license, attribution, and compatibility with our pinned KiCad/backend
architecture. Decide reuse, adaptation, or independent implementation; flag
license conflicts before copying and add regression coverage before exposure.
No external design code is incorporated in this foundation iteration.

Preserve existing tool contracts where practical and document unavoidable
breaking changes. Maintain a manageable upstream relationship. Keep version
special cases behind a small backend layer and detect runtime capabilities;
unsupported operations fail clearly before modifying designs.

## Evidence required before autonomy expands

The capability matrix must separately record implementation, unit tests, real
integration tests with exact KiCad/bindings versions, and unsupported/unverified
behavior. Mocks cannot establish KiCad compatibility. Disposable representative
projects must demonstrate:

- manual schematic edits followed by review and scoped edits, with hierarchy,
  connectivity, and stable identities preserved;
- observation of unsaved changes and invalidation of stale schematic approval;
- exact preservation of locked placements and protected manual copper;
- stale-plan rejection and revalidation of long-running results;
- interrupted/failed operations preserving unrelated work and inspecting
  ambiguous outcomes before retries;
- project policy/approval continuity after server and client restarts.

If integration is unavailable, report it as not run and provide a reproducible
procedure. Do not turn skips into passes.
