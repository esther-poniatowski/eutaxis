---
tags: []
aliases:
  - Three-layer composition and precedence
index: "[Architecture decisions](_index.md)"
---

# Three-layer composition and precedence

## Status

Accepted. Resolves the former intra-artifact composition question.

## Purpose

Compilation must produce deterministic artifacts without reproducing the precedence hierarchy of the host. Three layers answer different questions and must not share one precedence mechanism.

## Semantic resolution inside one compilation unit

A compilation unit is the set of declarations selected by one composition manifest for one native scope and one target artifact. The semantic resolver applies applicability, exceptions, dependencies, and declared conflicts inside that unit. [Rule relations and contextual resolution](rule-relations-and-resolution.md) owns this layer.

A project composition manifest may choose project declarations and imported shared declarations for its project artifact. A personal manifest may choose declarations for a personal artifact. Such a manifest does not suppress or rewrite an artifact emitted at another native scope.

## Deterministic composition inside one artifact

The future semantic resolver alone issues a certified compilation unit. The resolver-backed unit supplies four inputs to the composer:

- the retained records
- the effective norm and criterion projection of each retained rule
- the prerequisite edges retained by the resolver
- the manifest anchor assigned to each record

The composer ignores four classes of raw input:

- edges between source records
- context predicates
- conflict policies
- membership of rule sets

Those raw inputs are unavailable to the composer. The composer cannot contradict choices certified by the resolver.

The resolver returns the certified unit and its explanation trace as one correlated result. A failed resolution may return its immutable trace through the error, but it never supplies a partial unit. The future composer validates the identifiers and one-to-one rule projections in a resolver-backed unit. It does not reevaluate applicability, exceptions, dependencies, or policies.

The current fixture-only `ResolvedCompilationUnit` predates the resolver. It contains the manifest, components, and dependencies, but no rule projections. The vertical resolver slice will replace this fixture issuance boundary atomically rather than expose a partial projected model.

The manifest declares its `sections` in order. Each `section` lists its records in order. A directly named record keeps its authored anchor. The resolver assigns an existing `(section, rank)` pair to every added record. Every prerequisite precedes its dependant. The renderer keeps the declared order of `sections`. An edge from a later `section` to an earlier one would violate that order.

Within those constraints, the composer uses a stable topological sort. The assigned rank forms the first tie-break key. The stable record identifier forms the second key. The composer rejects three malformed inputs:

- supplied edges that contain a cycle
- anchors or edge endpoints that do not exist
- manifests that name one record twice

Another layer first converts each retained record into a Markdown block. The mechanical assembler receives two inputs after those blocks exist:

- an opaque plan
- a closed dictionary keyed by record identifier

The dictionary must contain exactly the identifiers in the plan. The assembler reads each block in plan order. Manifest `sections` supply order only. The assembler emits no section labels or wrappers.

Each Markdown block must satisfy four boundary rules:

- contain non-whitespace text
- use newline characters without carriage returns
- omit a leading newline
- omit a trailing newline

The assembler preserves every other character, including internal spaces and Unicode code points. The assembler places one blank line between consecutive blocks. The assembler appends one terminal newline. The assembler uses eight-bit Unicode Transformation Format to encode the result. An empty plan emits empty bytes.

The artifact stores four values:

- manifest identifier
- native scope
- target
- canonical bytes

The derived text view decodes the canonical bytes. This metadata keeps personal and project artifacts distinct when they share a target path.

Each composition manifest declares its target mechanism explicitly. Because `target` is opaque, it does not select a mechanism. The declared mechanism fixes collision behavior:

- cumulative files concatenate the ordered sections
- separate-directory mechanisms emit one artifact per stable identifier and reject duplicate output paths
- single-slot mechanisms accept exactly one selected value; more than one value is an error unless a declared semantic resolution policy reduces them to one

The composer never uses last-writer-wins behavior. A semantic contradiction must be resolved before composition. An output-path or single-slot collision fails before rendering.

Cross-regime references are validated before emission. A cumulative entrypoint may reference a Skill only when the same plan emits that Skill or the configured registry proves that an owned compatible artifact already exists.

## Host-owned cross-scope precedence

Eutaxis emits each native scope independently. When personal and project artifacts both exist, the host decides their precedence. Eutaxis records both outputs and the documented host relation in `plan` and `explain`, but it neither selects a cross-scope winner nor removes the lower-scope artifact. This layer remains governed by [native precedence](native-precedence-over-parallel-engine.md).

## Validation and tests

The first multi-component fixture must prove:

- byte-identical ordering under repeated builds
- dependency-before-dependant ordering
- manifest-order tie-breaking for unrelated declarations
- assemble fixture-projected blocks into byte-identical output
- reject missing, additional, or non-canonical projected blocks
- accept retained prerequisites, policy results, and rule-set members not named directly in the manifest
- failure when a supplied edge contains a cycle
- failure when an anchor or edge endpoint is invalid
- reject an edge that points from a later `section` to an earlier `section`
- reject duplicate manifest membership, duplicate output paths, and multiple values for one slot
- preservation of both artifacts when the same component exists at personal and project scopes

Mechanical cumulative assembly cannot pass its implementation gate with a single-component fixture. Converting semantic records into Markdown remains a later gate.

## Consequences

Semantic resolution, artifact composition, and host precedence have separate records, data structures, and evidence. The composition manifest owns order only within one output artifact. Contextual semantic policies do not decide filesystem order, and native scope precedence does not resolve contradictions inside a generated file.
