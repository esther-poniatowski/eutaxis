---
tags: []
aliases:
  - Audit Protocol
index: "[Design Documentation — Methods](_index.md)"
---

# Audit protocol

This file is the **operational contract**. It governs the mandatory workflow for every unit edit and every section draft under eutaxis. No text is returned before this protocol completes.

The protocol fixes the *shape* of the workflow — its phases, their order, and the output gate — and defers the substance of each phase to the project's declared rules. Every project that deploys eutaxis populates the per-phase checks with its own rules, vocabulary, forbidden strings, and linters. This file remains silent on those specifics.

---

## Critical warning

Do not use fluency, idiomatic register, or resemblance to canonical examples as evidence of compliance. Standard prose patterns — nominalization, passive indirection, heavy compound terms, imperative openings, conclusions before grounding — are common failure modes to guard against, rather than acceptable defaults. Apply every check mechanically to every sentence, including:

- carried-over text from source units (the single highest source of missed violations, because it already "sounds right");
- Markdown link texts (every link text is a sentence and must pass all checks independently);
- callout bodies and contribution bullets;
- bold-label paragraphs.

---

## Mandatory generation workflow

Execute every phase in order. Do not return output until Phase 7 passes.

---

### Phase 0 — Scope decision

Before drafting, decide exactly one of the following:

- **Full-treatment mode**: the complete development belongs in this unit, including setup, development, result, interpretation, and edge cases.
- **Pointer mode**: only a pointer belongs here. Write a single linking sentence and cross-link to the source unit.

Do not mix modes in the same unit. If content currently exists in both modes, decide which to keep and delete the other.

---

### Phase 1 — Structure pass

Before drafting any prose, establish:

1. the central question of the unit (recorded in the project's central-question callout, e.g. `[!QUESTION]`);
2. the contribution bullets (recorded in the project's contribution callout, e.g. `[!QUOTE] Originality`), each fitting the project-declared contribution-statement pattern;
3. the roadmap items (recorded in the project's roadmap callout, e.g. `[!TIP] Roadmap`), each naming a section's role in the chain rather than a result;
4. the assumptions or applicability conditions (recorded in the project's applicability callout, e.g. `[!WARNING] Applicability`);
5. the block anchors required by downstream cross-references;
6. whether any project-declared structured artifact (summary table, comparison matrix, diagram) is required by the unit's content.

Verify the contribution/roadmap separation: if a roadmap item states a result or novelty claim, move it to contributions. If a contribution bullet describes the path without stating a result, move it to the roadmap.

---

### Phase 2 — Draft pass

Write the body in dependency order within each section. The default order is:

1. purpose and problem statement;
2. setup and definitions;
3. development;
4. result statement;
5. interpretation;
6. specializations and examples;
7. edge cases and boundary conditions.

Projects that need a different default order declare it in their structural rules. After completing each section, verify the section dependency chain by checking what this section receives from the preceding section. If the answer is "nothing", reorder or add a missing connecting step.

---

### Phase 3 — Sentence audit

For every sentence in the draft — including sentences carried over from earlier drafts, link texts, callout bodies, and bold-label paragraphs — apply the project-declared sentence checks in order. Do not rely on whether the sentence "sounds wrong."

The project's style rules declare the concrete tests. The categories below are the canonical surface every project must cover:

- **Style discipline.** Nominalization, passive voice, heavy compound modifiers, and other style-level patterns the project bans.
- **Framing.** Sentences that describe the act of establishing a result instead of stating it; vague procedural nominalizations whose operands are implicit.
- **Modifier discipline.** Hyphenated pre-nominal modifiers that encode prepositional or clausal relationships; stacked-modifier sequences.
- **Opening discipline.** Sentence openings forbidden by the project (typically imperative verbs that should be rephrased declaratively).
- **Named referent.** Symbols, identifiers, or technical tokens appearing in qualifiers or conditions without naming the object they refer to.
- **Link text.** Markdown link texts that name a container, procedure, or analysis instead of a result, object, or property.
- **Display reference.** Sentences immediately after a display block (table, equation, code fence) that begin with a bare pronoun rather than a descriptive noun phrase.

The project's style file declares the literal forms of each test (regular expressions, banned tokens, examples).

---

### Phase 4 — Structural audit

After completing the draft, verify at paragraph and section level:

**Section dependency.** For each section after the first, identify what it receives from the preceding section. If nothing, the section is misplaced or a connecting step is missing.

**Paragraph dependency.** For each paragraph after the first in a section, check whether removing the preceding paragraph would break this one. If not, a logical connector is missing or the preceding paragraph is redundant.

**Preview–conclusion redundancy.** If a section opens with a preview of the result and closes with a restatement of it, delete one. Do not state the same result at both ends of a section.

**Contributions–body redundancy.** If a body paragraph restates a contribution bullet without adding new content, delete the restatement or compress it to a back-reference.

**Takeaway justification.** A concluding paragraph must add implications, limiting cases, or connections beyond the formal statement. If it only restates the result in words, delete it.

**Callout dispatch.** If the central-question callout body describes what the unit achieves, move it to contributions. If a roadmap item announces a result or novelty claim, move it to contributions. If a contribution bullet describes the path without stating a result, move it to the roadmap.

---

### Phase 5a — Forbidden-string search

Search the final Markdown text for each entry in the project-declared forbidden-string list. Any match outside code blocks requires revision before proceeding. The list lives in the project's style rules, and this phase enforces it mechanically.

### Phase 5b — Semantic audit

Search for semantic equivalents of forbidden patterns even when the literal string is absent. Revise any sentence that:

- places a process nominalization as the grammatical subject with an existence verb;
- names a procedure as the grammatical object of a unit-centered or section-centered sentence;
- uses a relation noun (comparison, coupling, independence, modulation, …) without naming the operands;
- uses a link text that names a procedure, container, or analysis rather than a result or object.

Projects extend this list with domain-specific semantic patterns.

---

### Phase 6 — Linter

Run the project-declared linters on all modified files. The path and entry point of each linter live in the project's tooling configuration.

Fix all reported issues before proceeding. Linter compliance is necessary but not sufficient — the linter does not catch all violations covered by Phase 3.

---

### Phase 7 — Output gate

Return the text only when all of the following are true:

- Phase 3: no sentence fails any of the project's sentence checks;
- Phase 4: no structural redundancy or callout dispatch violation remains;
- Phase 5: no entry from the forbidden-string list appears outside code blocks, and no semantic equivalent appears either;
- Phase 6: every project-declared linter reports no issues.

If any condition is false, return to the appropriate phase and revise. Do not return partial output.

---

## Internal checklist (do not expose in output)

Internally maintain a per-sentence checklist during Phase 3 and a per-section checklist during Phase 4. Do not include these checklists in the final unit unless explicitly requested.

---

## Quality tiers for rules outside the hard-blocker set

Project-declared rules that do not appear in the hard-blocker list fall into the following tiers:

**Tier B — Structural blockers** (required when applicable; revise before output)

- opening-callout order;
- contribution / roadmap separation;
- applicability-callout placement;
- ordering of formal results relative to interpretation (project-declared);
- interpretation sentence after each non-trivial display element (project-declared);
- introduction of new objects by role before notation (project-declared);
- anchors on the first content line; no heading-slug links;
- single-source-of-truth for any development the project marks reusable;
- structured-artifact requirements for multi-case units (project-declared).

**Tier C — Quality improvements** (revise unless there is a strong reason not to)

- sentence-length thresholds set by the project;
- paragraph coherence and explicit connectors;
- bold-label consistency across sections;
- style homogeneity of takeaway formats;
- inline-enumeration conversion to a bulleted list;
- assumption motivation before the formal statement.
