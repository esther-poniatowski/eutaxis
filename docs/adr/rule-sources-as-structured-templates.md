# Rule sources as structured templates

## Status

Accepted.

## Context

The oikos `instructions/tasks/` rule sets are currently authored as
free-form Markdown. Each file follows an *implicit* schema that has
emerged by convention: a rule has a name (section header), a ✓
prescription block, a ✗ prohibition block, an optional **Why** line,
an optional **How to apply** line, and optional valid / invalid
example blocks. The same conventions appear across every file in
the set.

This authoring style has two attractive properties: it is the same
artifact the agent reads at runtime (no compilation step), and the
prose is dense and readable. It also has three structural defects
that block the proposed rule infrastructure:

1. **Specification and rendering are coupled.** The artifact on
   disk is, simultaneously, the source the author edits, the
   compilation input, and the final form an agent consumes. There
   is no place to express the same rule differently for two
   targets that require different surface forms — a Markdown
   bullet list for Claude code's `CLAUDE.md`, a TOML triple-quoted
   block for a Codex `developer_instructions` payload, a terse
   summary for a subagent system prompt of limited budget.
2. **The implicit schema is not enforced.** Convention-based
   structure drifts between files and between authors. A rule
   that omits its **Why** line is indistinguishable from one whose
   author judged the rationale unnecessary — the schema cannot
   tell. This blocks mechanical validation, mechanical
   summarisation, and the placement-test work tracked in
   [silent-failure-classification](../open-questions/silent-failure-classification.md)
   (which needs a `failure-mode` field that every rule must
   declare).
3. **No stable identifier algebra.** The compositional skill
   work described in
   [activation-regime-as-classification-axis](activation-regime-as-classification-axis.md)
   and refined in the session's proposal 3 ("include task A + rule
   set R1 + R2 minus rule X") requires each rule to be addressable
   by a stable identifier. A Markdown section header is not a
   stable identifier — it is editable, reorderable, and may
   collide.

The session's proposal 2 was to lift the implicit schema into an
explicit one. An initial draft retained a YAML frontmatter +
Markdown body shape, on the argument that example payloads "resist
field-level typing." That argument is incorrect: a configuration
format with cleanly delimited multi-line blocks (YAML literal block
scalars, TOML triple-quoted strings, equivalents) accepts rich
prose, code, and example content as the *value* of a typed field
without losing expressivity. The decoupling objective therefore
applies uniformly to all parts of a rule, including examples.

## Decision

Rule sources are **structured, schema-validated configuration
files**. Every canonical aspect of a rule is a typed field with
declared mandatory / optional status, not a convention-named
section in a Markdown body.

The schema commits to the following structural properties; the
exhaustive field vocabulary and the surface syntax are deferred to
[rule-template-format-and-vocabulary](../open-questions/rule-template-format-and-vocabulary.md):

1. **Each rule has a stable identifier** (`id`), independent of
   file location, section heading, or rendering order. Identifiers
   are the addressing surface for cross-rule references, for
   include/exclude composition, and for tooling
   ([identifier-and-namespace-algebra](../open-questions/identifier-and-namespace-algebra.md)
   governs the namespace shape).
2. **Each canonical rule aspect is its own field**, with a declared
   type and a declared mandatory / optional status. The minimum
   set surfaced by the session covers: prescription, prohibition,
   valid examples, invalid examples, operational check, rationale.
   The exhaustive list is the subject of the open question.
3. **Multi-line content is preserved within a field**, via the
   surface syntax's block-scalar mechanism or via schema-addressable
   tagged content blocks. A field holding prose, code, or a
   structured example is parsed as one delimited block and emitted
   unchanged to the renderer.
4. **Rendering is the adapter's responsibility.** A rule source is
   never directly read by an agent at runtime. The cross-agent
   compiler renders it to whichever target form the receiving
   surface accepts — Markdown for `CLAUDE.md`, prose paragraph for
   `developer_instructions`, summary line for a listing, etc.
   This mirrors the schema strategy already established for
   commands by
   [adapter-passthrough-source-schema](adapter-passthrough-source-schema.md).
5. **The schema is validated at load time.** A rule that omits a
   mandatory field, or contains a field outside the declared
   vocabulary, fails the compiler with a clear error. Convention-
   based drift is replaced by mechanical refusal.

## Discarded alternatives

- **Keep free-form Markdown as the source form.** Rejected on the
  three structural defects in the context section: coupled
  specification/rendering, unenforced schema, no stable identifier
  algebra.
- **Untyped YAML frontmatter + Markdown body (hybrid).** Rejected
  after session discussion. The frontmatter portion buys identifier
  and metadata typing, but the Markdown body retains the same
  convention-based structure as the current files: the ✓ / ✗ / Why /
  examples blocks remain section headers, parseable only by
  agreement, not by schema. The hybrid preserves authoring
  ergonomics but does not deliver the decoupling objective. This
  rejection does not apply to a typed, tag-delimited Markdown hybrid
  whose content blocks are schema-addressable fields.
- **JSON with escaped multi-line content.** Rejected: JSON has no
  comment syntax, no block-string mechanism, and forces every
  newline in prose or example content into `\n` escapes. The
  schema is enforceable but the source becomes hostile to
  hand-authoring.
- **Custom DSL with bespoke block delimiters.** Rejected on tooling
  cost: a custom format would require a parser, a validator, editor
  support, and a migration plan, none of which are justified when
  existing configuration and Markdown layers can satisfy the
  structural requirements.

## Rationale

Structured templates deliver three properties simultaneously, none
of which the current Markdown approach can:

- **Per-target rendering** — the same rule source can be emitted
  as a Markdown bullet list for one surface, a TOML string for
  another, or a one-line summary for a third, without parallel
  prose copies.
- **Stable identifier algebra** — every rule has an addressable
  identifier, which is the precondition for compositional skills
  and for refactor-safe cross-references.
- **Mechanical validation** — a schema can refuse rules that omit
  a mandatory field, declare an unknown field, or contradict
  declared constraints. Convention-based drift becomes a load-time
  error, not a review-time observation.

The decision aligns with the architectural posture already
established by
[adapter-passthrough-source-schema](adapter-passthrough-source-schema.md)
and
[compiler-not-runtime-activation](compiler-not-runtime-activation.md):
sources are typed configurations; targets are rendered artifacts;
the adapter is the compilation surface.

## Consequences

- A schema must be defined. The minimum field set is sketched in
  this ADR; the exhaustive vocabulary, mandatory / optional
  declarations, and the surface syntax (YAML, TOML, other) are
  the subject of
  [rule-template-format-and-vocabulary](../open-questions/rule-template-format-and-vocabulary.md).
- A renderer must be implemented per target surface. The
  cross-agent compiler grows a per-adapter rule renderer; the
  pattern reuses the slots established by
  [adapter-passthrough-source-schema](adapter-passthrough-source-schema.md).
- Rule identifiers become referenceable surfaces with stability
  requirements equivalent to ADR identifiers; they couple to
  [identifier-and-namespace-algebra](../open-questions/identifier-and-namespace-algebra.md).
- File-level packaging of rules is independent of the schema
  decision; whether a file holds one rule or a coherent rule-set
  is deferred to
  [rule-set-granularity](../open-questions/rule-set-granularity.md).
- A migration pass is required for the current oikos
  `instructions/tasks/` set. Each existing free-form rule is
  reauthored as a structured template entry. The migration is
  scoped to the always-on body and the on-demand skill body
  separately, per the placement rule of
  [silent-failure-rules-as-always-on](silent-failure-rules-as-always-on.md).
- Authoring is heavier than free-form Markdown. The cost is paid
  once per rule and recovered every time a rule is consumed by a
  new surface, mechanically validated, or composed into a skill.
