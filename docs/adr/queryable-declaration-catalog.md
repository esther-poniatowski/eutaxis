---
tags: []
aliases:
  - Queryable declaration catalog
index: "[Architecture decisions](_index.md)"
---

# Queryable declaration catalog

## Status

Accepted.

## Purpose

Consumers must retrieve the necessary declarations for a known context without loading every source file, while retaining a reviewable path back to the canonical YAML.

## Decision

Eutaxis loads canonical YAML into a typed in-memory catalog. A stable query API and CLI expose lookup, selection, explanation, dependency closure, and enforcement partitioning. Storage is an implementation detail behind that interface.

The first persisted acceleration structure is an optional deterministic JSON index generated from the YAML. It records identities, hashes, classifications, relations, source locations, and query fields. It is disposable and reproducible. A SQLite database is introduced only after measurements show that source scale, startup time, or query latency exceeds the JSON design; it never becomes an authoring source.

The catalog exposes at least these operations:

- retrieve a declaration or one field by stable identifier
- filter by owner, kind, axis, applicability, failure mode, visibility, and enforcement class
- resolve exceptions, conflicts, and dependencies for a typed context
- explain why each declaration was selected, omitted, waived, or overridden
- group the result into deliberation, assisted inspection, and checker invocations
- retrieve versioned evaluator and operation contracts used by those packets
- report the source hash, schema version, evaluator version, and generated-index revision used for an answer

Selection cannot guarantee a necessary-and-sufficient rule set from storage alone. Applicability classification and semantic context recognition remain substantive problems. The query contract therefore returns its context assumptions and resolution trace instead of claiming completeness without evidence.

## Query packets and target projections

Canonical YAML remains build input. A query returns a generated packet containing the effective declarations, inherited applicability, resolution trace, evaluator instructions, operation contracts when requested, and complete provenance. YAML and JSON are packet serializations, not direct access to the authoring files.

Current hosts still require Markdown cumulative files and Markdown `SKILL.md` entrypoints. Adapters render these compact activation surfaces from catalog records. A Skill may retrieve a packet only through an available explicit catalog interface; otherwise, its deployment bundles the rendered rules required for independent use. The catalog does not create an implicit pre-prompt injector.

## Discarded alternatives

- **Rendered Markdown as the only retrieval surface.** Rejected because it forces agents to load presentation syntax and unrelated rules before selection.
- **SQLite as the canonical source.** Rejected because schema review, diffs, merge resolution, and hand authoring are superior in YAML, while a database adds synchronization and migration failure modes.
- **One database query as proof of sufficiency.** Rejected because storage cannot decide whether the supplied task context was classified correctly.

## Consequences

The catalog becomes the shared boundary between parsing, registries, resolution, rendering, and checking. Renderers do not parse source files independently. Checkers and documentation generators consume the same declaration identifiers and evaluator mappings, preventing parallel registries.
