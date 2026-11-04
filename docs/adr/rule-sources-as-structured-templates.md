---
tags: []
aliases:
  - Rule sources as structured templates
index: "[Architecture decisions](_index.md)"
---

# Rule sources as structured templates

## Status

Accepted.

## Context

The oikos `instructions/tasks/` rule sets are currently authored as free-form Markdown. Each file follows an *implicit* schema that has emerged by convention: a rule has a name (section header), a ✓ prescription block, a ✗ prohibition block, an optional **Why** line, an optional **How to apply** line, and optional valid / invalid example blocks. The same conventions appear across every file in the set.

This authoring style has two attractive properties: it is the same artifact the agent reads at runtime (no compilation step), and the prose is dense and readable. It also has three structural defects that block the proposed rule infrastructure:

1. **Specification and rendering are coupled.** The artifact on disk is, simultaneously, the source the author edits, the compilation input, and the final form an agent consumes. There is no place to express the same rule differently for two targets that require different surface forms — a Markdown bullet list for Claude code's `CLAUDE.md`, a TOML triple-quoted block for a Codex `developer_instructions` payload, a terse summary for a subagent system prompt of limited budget.
2. **The implicit schema is not enforced.** Convention-based structure drifts between files and between authors. A rule that omits its **Why** line is indistinguishable from one whose author judged the rationale unnecessary — the schema cannot tell. This blocks mechanical validation, mechanical summarisation, and the placement-test work tracked in [silent-failure-classification](../open-questions/silent-failure-classification.md) (which needs a `failure-mode` field that every rule must declare).
3. **No stable identifier algebra.** The compositional skill work described in [activation-regime-as-classification-axis](activation-regime-as-classification-axis.md) and refined in the session's proposal 3 ("include task A + rule set R1 + R2 minus rule X") requires each rule to be addressable by a stable identifier. A Markdown section header is not a stable identifier — it is editable, reorderable, and may collide.

The session's proposal 2 was to lift the implicit schema into an explicit one. An initial draft retained a YAML frontmatter + Markdown body shape, on the argument that example payloads "resist field-level typing." That argument is incorrect: a configuration format with cleanly delimited multi-line blocks (YAML literal block scalars, TOML triple-quoted strings, equivalents) accepts rich prose, code, and example content as the *value* of a typed field without losing expressivity. The decoupling objective therefore applies uniformly to all parts of a rule, including examples.

## Decision

Rule sources are **structured, schema-validated configuration files**. Every canonical aspect of a rule is a typed field with declared mandatory / optional status, not a convention-named section in a Markdown body.

The schema commits to the following structural properties; [YAML declaration schema](yaml-declaration-schema.md) fixes the architecture, while the versioned JSON Schema is the exhaustive field contract:

1. **Each rule has a stable identifier** (`id`), independent of file location, section heading, or rendering order. Identifiers are the addressing surface for cross-rule references, for include/exclude composition, and for tooling; [external declaration identity and acquisition](external-declaration-identity-and-acquisition.md) governs their cross-repository namespace and revision provenance.
2. **Each canonical rule aspect is its own field**, with a declared type and a declared mandatory / optional status. Normative content separates modality, subject, applicability, and action; examples and criteria refer to the norm identifiers they illustrate or test.
3. **Multi-line content is preserved within a field** through YAML block scalars. A field holding Markdown prose, code, or an example is parsed as one delimited value and emitted through the relevant adapter.
4. **Projection is the adapter's responsibility.** A canonical source is never itself injected into an agent session. The compiler renders a native artifact or produces a normalized, provenance-bearing YAML or JSON query packet. Markdown remains necessary for hosts that require it; a Skill without guaranteed catalog access bundles a rendered fallback. This mirrors the schema strategy already established for commands by [adapter-passthrough-source-schema](adapter-passthrough-source-schema.md).
5. **The schema is validated at load time.** A rule that omits a mandatory field, or contains a field outside the declared vocabulary, fails the compiler with a clear error. Convention- based drift is replaced by mechanical refusal.

## Discarded alternatives

- **Keep free-form Markdown as the source form.** Rejected on the three structural defects in the context section: coupled specification/rendering, unenforced schema, no stable identifier algebra.
- **YAML frontmatter plus a convention-shaped Markdown body.** Rejected because the ✓, ✗, rationale, and example sections remain implicit. A typed tagged-Markdown hybrid remains a fallback only if the YAML pilot demonstrates a material defect.
- **JSON with escaped multi-line content.** Rejected: JSON has no comment syntax, no block-string mechanism, and forces every newline in prose or example content into `\n` escapes. The schema is enforceable but the source becomes hostile to hand-authoring.
- **Custom language with bespoke block delimiters.** Rejected because a custom format needs a dedicated parser, validator, and editor integration. YAML and Markdown meet the same structural criteria with existing tools.

## Rationale

Structured templates deliver three properties simultaneously, none of which the current Markdown approach can:

- **Per-target rendering** — the same rule source can be emitted as a Markdown bullet list for one surface, a TOML string for another, or a one-line summary for a third, without parallel prose copies.
- **Stable identifier algebra** — every rule has an addressable identifier, which is the precondition for compositional skills and for refactor-safe cross-references.
- **Mechanical validation** — a schema can refuse rules that omit a mandatory field, declare an unknown field, or contradict declared constraints. Convention-based drift becomes a load-time error, not a review-time observation.

The decision aligns with the architectural posture already established by [adapter-passthrough-source-schema](adapter-passthrough-source-schema.md) and [compiler-not-runtime-activation](compiler-not-runtime-activation.md): sources are typed configurations; targets are rendered artifacts; the adapter is the compilation surface.

## Consequences

- The [YAML declaration schema](yaml-declaration-schema.md) defines the vocabulary, modality, contracts, and fallback condition.
- A projection must be implemented per target surface. Native Markdown renderers and normalized query packets both derive from the catalog; the pattern reuses the slots established by [adapter-passthrough-source-schema](adapter-passthrough-source-schema.md).
- Rule identifiers become referenceable surfaces with stability requirements equivalent to ADR identifiers; external sources follow [external declaration identity and acquisition](external-declaration-identity-and-acquisition.md).
- File-level packaging follows [coherent rule-set packaging](coherent-rule-set-packaging.md).
- A migration pass is required for the current oikos `instructions/tasks/` set. Each existing free-form rule is reauthored as a structured template entry. The migration is scoped to the always-on body and the on-demand skill body separately, per the placement rule of [silent-failure-rules-as-always-on](silent-failure-rules-as-always-on.md).
- Authoring is heavier than free-form Markdown. The cost is paid once per rule and recovered every time a rule is consumed by a new surface, mechanically validated, or composed into a skill.
