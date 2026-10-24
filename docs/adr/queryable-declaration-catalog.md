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

## Initial static boundary

The first catalog slice provides read-only access to an already validated registry. An exact key retrieves either an unversioned record or a versioned contract. The retrieved value is the registered object itself. Therefore, this catalog adds no second semantic model.

The static boundary excludes the following work:

- deciding whether a context satisfies a predicate
- finding prerequisite records
- applying conflict policies
- explaining why a record is effective or excluded
- assigning enforcement work
- producing query packets or Markdown

The resolver performs the first five items. The projection boundary produces the packets and Markdown.

The source schema and the `index-revision` field evolve independently. The JSON arrays use these orders:

- sources by portable path
- declarations by identifier
- contracts by kind, identifier, and version
- normalized conflict pairs lexically

Each source path is relative to an explicit source root and uses `/` as its separator. The builder rejects a source outside that root. Before parsing YAML, the loader hashes the exact source bytes with `hashlib.sha256`. The validated registry retains that digest. Consequently, the index can use the retained digest without reading the source again.

Each indexed record contains the following fields:

- its stable identifier and kind
- its static query fields
- its relations and containing rule set
- its portable source coordinates

The source coordinates contain a relative file path and a path through the YAML tree. The same coordinates contain line and column numbers that start at one. The index omits the following data:

- timestamps and absolute paths
- resolver results and packets
- rendered content

The serializer writes compact JSON as `utf-8` bytes. Identical inputs produce identical bytes, followed by one newline.

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
