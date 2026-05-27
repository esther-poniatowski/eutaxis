---
tags: []
aliases:
  - "Rule-set granularity: one file per rule vs one file per rule-set"
index: "[Open architectural questions](_index.md)"
---

# Rule-set granularity: one file per rule vs one file per rule-set

**Severity.** Medium. **Phase-blocking.** Phase 1 (rule-template migration). **Origin.** Refinement of session proposal 2, recorded in [rule-sources-as-structured-templates](../adr/rule-sources-as-structured-templates.md).

## Question

[rule-sources-as-structured-templates](../adr/rule-sources-as-structured-templates.md) decides that rules are addressable by stable identifiers, but does not decide whether each identifier corresponds to its own file or to an entry inside a file that holds a coherent rule-set.

Two packaging schemes are possible:

- **One file per rule.** Each rule lives in its own file; the file's name is (or contains) the rule's identifier. Compositional selection by identifier maps directly onto filesystem operations.
- **One file per rule-set, with internal identifiers.** A file holds a coherent group of related rules; each rule inside the file declares its own identifier. The file is the loading unit; the identifier is the selection unit.

The choice is not purely cosmetic. The decision shapes:

- **Authoring locality.** Closely related rules cross-reference each other ("see also [[no-forward-references]]"), and editing them together is the dominant access pattern.
- **Loading granularity.** A skill that activates "conceptual reasoning" typically wants the whole rule-set, not three of its eleven rules; bulk loading is more common than single-rule loading.
- **Filesystem footprint.** The current `instructions/tasks/` set has on the order of fifty rules across eight files; per-rule packaging would mean fifty files, growing as the set grows.
- **Index and discovery overhead.** Cross-rule lookup at scale benefits from larger files (fewer file opens), whereas single-rule lookup benefits from per-rule files (no internal indexing needed).

## Current state

- All current oikos `instructions/tasks/` files are rule-sets with multiple rules per file.
- The eutaxis commands subsystem packages each command as its own directory (one identifier, one artifact); this concerns on-demand skills, not rules.
- The schema decision in [rule-sources-as-structured-templates](../adr/rule-sources-as-structured-templates.md) is neutral on packaging — it requires only that each rule have a stable identifier, not that each identifier have its own file.
- Prior art in the gnomon project (`docs/design/2-architecture/data-formats.md`) commits to a **single-export convention** for declaration files: a file's YAML frontmatter declares an `exports:` list of the identifiers the file exposes, and a linter warns when an object-definition file declares more than one entry. The convention is enforced softly so a file may still bundle auxiliary declarations tightly bound to a lead declaration when warranted. This is direct precedent for the leaning resolution below: one file per coherent set, with internal identifiers, plus a linter for sprawl.

## Architectural components that depend on this

- The migration plan from the current Markdown rule sets to structured templates.
- The rule-template format choice ([rule-template-format-and-vocabulary](rule-template-format-and-vocabulary.md)) — a format that holds many rules per file should support a list or map of rule entries; a format that holds one rule per file can have a flatter top-level shape.
- The identifier algebra ([identifier-and-namespace-algebra](identifier-and-namespace-algebra.md)) — file-per-rule-set packaging implies a two-level identifier (`<set-id>.<rule-id>` or equivalent), which affects the namespace.

## Candidate resolution

**One file per rule-set, with per-rule internal identifiers, is the leaning resolution**, recorded by the oikos maintainer during session discussion. The rationale:

- Most rules are small (a prescription, a prohibition, a couple of examples) and editing one in isolation is rare.
- Groups of rules tend to cohere around a behavioural aspect (the ten rules under `conceptual-reasoning` collectively shape how the agent reasons; loading three of them in isolation is uncommon).
- The dominant loading scenario is the whole rule-set, which rule-set packaging optimises directly.
- Per-rule identifiers preserve the option to compose more finely ("include the conceptual-reasoning set, except `genuine- contributions`") without forcing the filesystem layout to match the composition algebra.
- Direct precedent exists in the gnomon project's single-export convention: file-level `exports:` frontmatter lists the identifiers a file exposes, with a soft linter warning when a file lists more than one entry. The convention applies to rules by inversion: a rule-set file lists the rule `id`s it contains, and the linter inverts the warning to flag files with *too few* rules (a rule-set of one suggests the file should merge with a related set) or *too many* rules without a unifying behavioural aspect.

Three sub-questions to settle before landing:

1. **Identifier shape.** Whether per-rule identifiers are *flat-globally-unique* (`motivation-first`) or *namespaced by rule-set* (`conceptual-reasoning.motivation-first`). The namespaced form is more robust against collisions across rule-sets and is consistent with how the existing prompt-family identifiers are scoped in [prompt-family-as-primary-unit](../adr/prompt-family-as-primary-unit.md).
2. **Single-rule files as an escape hatch.** Whether a one-rule file is permitted (a rule-set of size one), and if so, whether the format degrades gracefully (no required `rules:` list wrapper when only one rule is present).
3. **Cross-set composition syntax.** How a skill declares "include set A, plus rule B from set C, minus rule D from set A" — the algebra is unspecified and couples to the format choice.

## Decision required before

The first migration pass from the current oikos `instructions/tasks/` files to structured templates. The filesystem layout is committed by that pass and is harder to change retroactively than the schema fields are.
