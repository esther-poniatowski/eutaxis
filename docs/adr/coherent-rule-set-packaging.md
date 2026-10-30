---
tags: []
aliases:
  - Coherent rule-set packaging
index: "[Architecture decisions](_index.md)"
---

# Coherent rule-set packaging

## Status

Accepted.

## Context

The structured-source decision separates the selection unit from the file unit. A rule must be selectable by stable identifier, but forcing every rule into its own file would trade one monolith for a directory of fragments. The current large modules are mostly coherent; line count alone does not show competing responsibilities.

## Decision

One YAML file holds one coherent rule set, and every rule inside it has its own stable identifier. A procedure or resolution policy occupies its own file because it has a different schema kind and maintenance rhythm. Single-rule sets remain valid when one rule forms a complete responsibility.

A split is justified when separate responsibilities, audiences, activation conditions, or maintenance rhythms compete in one file. A file is not split merely because it is long. Conversely, a one-rule file is not merged merely to reach a target count. The admission test is whether the file can be named precisely, reviewed independently, and changed without touching an unrelated concern.

Filesystem hierarchy does not encode every classification axis. Domain, reasoning axis, failure mode, activation, and ownership are orthogonal metadata queried through the catalog. Directories such as `epistemology/`, `argumentation/`, and `stylistic/` are therefore rejected as the primary organization: one hierarchy cannot represent the cross-cutting axes without duplication.

External set and member identifiers follow [external declaration identity and acquisition](external-declaration-identity-and-acquisition.md). This packaging decision remains independent of their transport and revision provenance.

## Consequences

- Migration begins by classifying existing content, not by renaming `instructions/tasks/` or splitting files by size.
- The directory rename to `instructions/rules/` and `instructions/procedures/` occurs in the same coordinated migration that introduces the new schema.
- The existing rendered-Markdown parser remains separate from the structured-source loader. After the new loader is established, `instructions/rules.py` should be assessed for a precise name such as `rendered_rules.py`; the rename is not performed before the boundary exists.
- The catalog indexes both file-level sets and member-level declarations, so loading a set and querying one rule use the same source.
