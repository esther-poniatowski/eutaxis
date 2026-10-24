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

The semantic resolver alone issues a certified compilation unit. The unit supplies three inputs to the composer:

- the retained records
- the prerequisite edges retained by the resolver
- the manifest anchor assigned to each record

The composer ignores four classes of raw input:

- edges between source records
- context predicates
- conflict policies
- membership of rule sets

Those raw inputs are unavailable to the composer. The composer cannot contradict choices certified by the resolver.

The manifest declares its `sections` in order. Each `section` lists its records in order. A directly named record keeps its authored anchor. The resolver assigns an existing `(section, rank)` pair to every added record. Every prerequisite precedes its dependant. The renderer keeps the declared order of `sections`. An edge from a later `section` to an earlier one would violate that order.

Within those constraints, the composer uses a stable topological sort. The assigned rank forms the first tie-break key. The stable record identifier forms the second key. The composer rejects three malformed inputs:

- supplied edges that contain a cycle
- anchors or edge endpoints that do not exist
- manifests that name one record twice

The target mechanism fixes collision behavior:

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
- accept retained prerequisites, policy results, and rule-set members not named directly in the manifest
- failure when a supplied edge contains a cycle
- failure when an anchor or edge endpoint is invalid
- reject an edge that points from a later `section` to an earlier `section`
- reject duplicate manifest membership, duplicate output paths, and multiple values for one slot
- preservation of both artifacts when the same component exists at personal and project scopes

The cumulative renderer cannot pass its implementation gate with a single-component fixture.

## Consequences

Semantic resolution, artifact composition, and host precedence have separate records, data structures, and evidence. The composition manifest owns order only within one output artifact. Contextual semantic policies do not decide filesystem order, and native scope precedence does not resolve contradictions inside a generated file.
