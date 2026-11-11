---
tags: []
aliases:
  - Structured procedure Skill projection
index: "[Architecture decisions](_index.md)"
---

# Structured procedure Skill projection

## Status

Accepted for the first `separate-directory` implementation slice.

## Purpose

A selected structured procedure must compile into a bounded Agent Skill directory that contains every authenticated file required to execute the procedure.

## Context

The cumulative Markdown projection emits one file for hosts that accept one always-loaded instruction document. This single-file artifact cannot carry a script required by an on-demand procedure. By contrast, an Agent Skill is a directory whose entrypoint may depend on sibling references and scripts. The existing [multi-file artifact model](multi-file-artifact-model.md) and [Agent Skill target](agent-skills-as-target-surface.md) already provide the host adapters, ownership sidecar, installation transaction and rollback boundary required by that directory.

The first consumer is a procedure whose operation uses a Python helper for guarded Git-index publication. The helper implements part of the operation rather than part of one procedure or one deployment manifest. Therefore, the dependency must follow the operation when another procedure reuses it.

## Decision

### Selection and placement

A composition manifest with `mechanism: separate-directory` selects exactly one root procedure in its first schema version. The manifest declares the Skill name through `target`, its scope and `invocation`. The `invocation` value is a non-empty unique list drawn from the closed vocabulary `model` and `user`. The selected procedure's `purpose` supplies the Skill description. A purpose that violates either host's description contract fails validation; Eutaxis neither truncates nor replaces it.

The Skill name is one portable path segment of at most 64 UTF-8 bytes. It must match `[a-z][a-z0-9]*(?:-[a-z0-9]+)*` and must not equal a case-insensitive platform device name: `con`, `prn`, `aux`, `nul`, `com1` through `com9`, or `lpt1` through `lpt9`. These constraints form the strict shared subset of the two host contracts and the supported installation filesystems. Invalid values fail before an adapter resolves the artifact directory. Eutaxis never sanitizes or truncates a Skill name. Planted failures cover traversal strings and names admitted by only one host.

Semantic resolution remains unchanged. The structured-Skill planner starts from one authenticated resolved procedure. The planner retrieves each exact action operation from the authenticated live catalog and closes those operations over their support-resource references. The first planner rejects any additional root declaration, a root of another kind or a selected operation without a non-empty authored method. A later planner may admit verified runner availability under a separate contract; the first planner does not accept a runner as a substitute.

The planner issues an authenticated `StructuredSkillPlan`. The plan retains the manifest, scope, Skill name, invocation routes, exact procedure, exact operations, ordered operation support references, resource identities and destinations, retained byte carriers, and the authority state of the resolution, catalog and acquired resources. Rendering accepts only this issued plan and re-authenticates its complete state before it constructs an artifact. No support closure is added to `ResolvedCompilationUnit` and the renderer does not recompute the closure.

### Acquired text resources

Each acquisition source descriptor may declare a `resources` list beside its declaration `files`. The source descriptor's exact acquired `root` owns both collections. The first resource entry has this closed form:

```yaml
resources:
  - id: oikos/publish-index
    path: declarations/resources/publish-index.py
    media-type: text/x-python; charset=utf-8
```

The resource identifier must belong to the source namespace. Resource identifiers and `(namespace, path)` coordinates are unique across one acquisition manifest. A resource path cannot also occur in `files`. Unreferenced resources are admitted to the acquired collection but do not enter a rendered closure.

The corresponding source-lock row repeats `id`, `path` and `media-type`, and adds `sha256`. Exact list correspondence binds every manifest resource to one lock row. The source content revision covers the ordered declaration-file locks and resource locks. The retained authority state binds the source descriptor identity, namespace, resource identifier, source path, media type, digest and content revision to the retained bytes.

The exact acquired source root resolves every resource path. Source paths and destinations use lowercase ASCII POSIX segments that match `[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?`, separated by `/`. A segment's stem before its first `.` cannot equal `con`, `prn`, `aux`, `nul`, `com1` through `com9`, or `lpt1` through `lpt9`. Absolute paths, empty segments, `.` or `..` segments, backslashes and repeated paths are invalid. The retained-directory boundary reads every component without following symbolic links and proves that the opened file remains below the acquired root. The renderer performs no later filesystem read. Planted failures include `con.py`, `com1.txt` and a segment with a trailing dot.

An operation declares each support dependency in this closed form:

```yaml
support-resources:
  - resource: oikos/publish-index
    destination: scripts/publish-index.py
```

The support list preserves authored order for semantic comparison. Each `(resource, destination)` pair must be unique. The operation owns the dependency. The composition manifest owns placement only through the selected closure and does not restate the dependency or its bytes.

The first resource contract admits only `text/x-python; charset=utf-8`. Acquisition decodes the retained bytes as strict UTF-8. Artifact assembly re-encodes the exact string as UTF-8 without newline or Unicode normalization and requires equality with the retained bytes. The first slice preserves no executable mode. `SKILL.md` invokes the helper through a selected Python interpreter rather than as an executable path.

The renderer reserves `SKILL.md`, `.eutaxis-owned.json`, `agents/openai.yaml` and `references/contract.md` for generated files. The lowercase path grammar and exact-path uniqueness exclude case and Unicode-normalization aliases on the supported filesystems.

### Compact entrypoint and complete contract

The renderer emits a compact `SKILL.md` that identifies the procedure and requires the agent to read `references/contract.md` before its first action. The reference file contains the complete resolved procedure and operation contracts. Every acquired support resource is copied byte-for-byte to its declared destination.

The caller supplies separate positive byte limits for `SKILL.md` and the complete artifact. Rendering fails when either limit is absent or exceeded. The entrypoint count is the final UTF-8 byte length of host-specific `SKILL.md`, including frontmatter. The complete count is the sum of final UTF-8 content bytes for every file, including adapter metadata and the ownership sidecar after their final hashes have been written. Paths do not contribute. Both limits are checked before publication.

The artifact file order is deterministic: entrypoint, complete contract, support resources ordered by the UTF-8 byte order of `(resource identifier, destination)`, then adapter and ownership files in the order defined by the existing renderer.

### Authority and collisions

The external planner authenticates the resolution and live catalog before it issues the complete operation and resource closure. The renderer re-authenticates the issued plan before it issues the artifact. It reads resource bytes only from retained byte carriers in that plan. A declaration path cannot cause a render-time filesystem read.

The renderer deduplicates repeated references to the same resource identity and destination. The semantic comparison retains each operation's authored support list and compares its exact ordered pairs. The renderer rejects:

- a missing or undeclared resource identity;
- one identity assigned to different destinations in one closure;
- different identities assigned to the same destination;
- a destination that collides with a generated file;
- changed resource authority or bytes;
- a support reference selected by cumulative Markdown.

The cumulative renderer remains a single-file projection. It rejects an operation with support resources until that operation declares a complete single-file fallback under a future contract.

### Adapter and installer boundary

One adapter-neutral `SkillRenderInput` carries the exact fields `name`, `description`, `scope`, `invocation`, `entrypoint_body`, `contract_file`, `resources` and `adapter_passthrough`. The structured renderer leaves `adapter_passthrough` empty in the first slice. The existing command renderer converts its established source model into the same input. Both routes then call one shared artifact assembler; neither fabricates the other route's source model.

The structured renderer supplies the canonical Skill entrypoint, complete contract and support resources through this input. Existing host adapters add native metadata, and the existing `RenderedArtifact` installer owns planning, diff, publication, rollback and removal. Eutaxis does not introduce a second installer for structured Skills.

## Acceptance evidence

The first slice requires:

- reviewed Codex and Claude golden directories containing `SKILL.md`, `references/contract.md`, the support script, `.eutaxis-owned.json` and host metadata where applicable;
- exact-byte comparison between every rendered support file and its acquired source;
- planted failures for missing resources, path traversal, reserved-path and destination collisions, stale authority, absent methods and both budget limits;
- an Oikos deployment preview in which every reference from the generated Skill resolves inside the artifact; and
- a recovery test that restores the prior Skill after a failed publication.

## Consequences

The structured batch-procedure pilot can activate without adding its full contract to the always-loaded instruction file. The cumulative process-core projection remains a separate optimization problem: production activation requires a compact always-on representation rather than a larger prompt budget.
