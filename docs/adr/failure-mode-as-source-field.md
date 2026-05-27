---
tags: []
aliases:
  - Failure-mode classification as a source field
index: "[Architecture decisions](_index.md)"
---

# Failure-mode classification as a source field

## Status

Proposed.

Closes [silent-failure-classification](../open-questions/silent-failure-classification.md).

## Context

[silent-failure-rules-as-always-on](silent-failure-rules-as-always-on.md) introduced the **silent-failure test** as the discriminator between always-on-body placement and on-demand-skill placement. The test is sound as a verbal criterion but unoperationalised: borderline rules drift between authors and across revisions, the compiler cannot refuse misplacement, and a later reviewer cannot verify that a placement decision was correct without reconstructing the failure mode.

The first concrete consumer that needs this resolved is the Skills-compilation path on the rule-set surface. Today the commands subsystem accepts only `regime: user-invoked` sources, where activation is explicit and the rule body loads before any irreversible action. Extending the path to model-invoked rule-set artifacts — the route that retires the heuristic router in oikos `instructions/tasks/` — requires the compiler to refuse routing a silent-failure rule through model-judgment-gated activation.

The open question recorded three concrete sub-questions: author-side classification, compiler-side enforcement, and audit recoverability. The candidate resolution it sketched (binary `failure-mode` field, author checklist, compiler refusal gate) has held up under session review. This ADR ratifies that candidate with one refinement: the field is required on every source that the compiler may route to a model-invoked artifact, with no default value, so that an unclassified source surfaces at validation time rather than absorbing the conservative-silent default and over-routing to the always-on body.

## Decision

Authored sources that the compiler may emit as Agent Skills carry a `failure-mode` field with one of two values:

- `silent` — violating the rule produces irreversible state mutation (filesystem, environment, git, external-service, permission). Late activation is harmful; the rule cannot be safely deferred to model judgment.
- `visible` — violating the rule produces a reviewable defect (weaker prose, missing comparison, suboptimal artifact). Late activation is recoverable at review time.

The field is **mandatory** on every source the Skills-compilation path consumes (the existing `commands` subsystem and any future rule-set / procedure adapter under it). An unclassified source raises a typed validation error naming the source path and the missing field.

**Author-side classification checklist.** A source's `failure-mode` is `silent` if any of these hold; otherwise `visible`:

1. Violation mutates filesystem, environment, git, or external-service state.
2. Violation widens permissions, installs software, or sends messages to external systems.
3. Violation writes to shared user files (`AGENTS.md`, `CLAUDE.md`, settings files) outside the compiler's ownership region.
4. The rule is needed to *decide* whether a skill or procedure is invoked — i.e. it gates routing, not output.
5. When in doubt, classify as `silent`.

A `visible` classification asserts none of the above. The checklist is reproduced verbatim in the source-schema documentation so authors apply the same gate the compiler enforces.

**Required-visibility refinement for `silent` sources.** Silent sources additionally declare `required-visibility`:

- `pre-invocation` — the rule is needed before deciding which procedure applies. Such a rule cannot ship as any skill; it stays in the always-on body.
- `pre-action` — explicit user invocation can load the rule before the first irreversible action. Such a rule may ship as a user-invoked skill, with the activation gate satisfying visibility.

`visible` sources do not declare `required-visibility`.

**Compiler-side enforcement.** The renderer refuses to emit:

- a skill that admits model invocation (`"model" in invocation`) from any source carrying `failure-mode: silent`. Misplacement raises `FailureModeError` before any artifact is written.
- a skill from a source carrying `failure-mode: silent` with `required-visibility: pre-invocation` regardless of `invocation`. Such a rule routes only to the always-on body.

The `invocation` field is itself a list whose members are the permitted invocation routes (`user`, `model`). It supersedes the single-valued `regime` field considered in earlier drafts: a binary single-value scheme cannot express the common case where both the user and the model may legitimately invoke the same skill, since the native platforms expose the binary "block model invocation: yes/no" only on the model side and the user side is always permitted.

The enforcement is unconditional. `eutaxis check` surfaces misplacements before generation runs. There is no `--force` escape for these checks; the matrix is small enough that authors fix the placement, not the gate.

**Audit recoverability.** Each source carries the checklist outcome inline in its frontmatter. A later reviewer reads the field directly. The compiler check is reproducible from the source; no out-of-band classification record is required.

## Discarded alternatives

- **Three-level scale (`silent | mixed | visible`).** Rejected as not actionable: a `mixed` source is exactly the case where the classification is at the wrong granularity. Mixed sources split at the rule level once structured templates land; until then, the file-level classification is conservative-silent, which is the safe failure mode.
- **Default to `silent` when omitted.** Rejected after weighing it against the alternative of requiring the field. A default would silently absorb unclassified sources into the conservative bucket — exactly the drift the open question called out. The compiler raising on a missing field forces a classification decision at authoring time.
- **Advisory classification, no compiler refusal.** Rejected: the gate exists only in author discipline, which is the failure mode the silent-failure test was meant to close.
- **Carry classification on rules, not sources.** Deferred. The rule-template migration ([rule-template-format-and-vocabulary](../open-questions/rule-template-format-and-vocabulary.md)) will add per-rule fields; until then, the file-level classification is conservative. The current sources are mostly mono-axis at the file level once the four-axis decomposition lands, so the file-level classification is close to the rule-level classification it will eventually replace.
- **Classification stored in a sidecar registry rather than frontmatter.** Rejected: a sidecar is a second source of truth; the frontmatter field travels with the source through copy, rename, and cross-repository sharing.

## Rationale

The decision closes the open question while keeping the schema surface small: one mandatory enum, one conditional sub-field, one compiler gate. The default-to-silent variant was attractive for ergonomics but loses the diagnostic signal — a source with no thought given to placement is indistinguishable from one whose author concluded `silent`. Requiring the field makes the absence of a classification a typed error, which is the property the open question's "author-side classification" sub-question called out.

The required-visibility sub-field carries the distinction between rules that gate routing and rules that govern an already-invoked procedure. Without it, every `silent` rule would over-route to the always-on body, defeating the user-invoked-skill route that the existing `clean-memory` command depends on.

## Consequences

- The `commands` subsystem source schema gains two fields: `failure-mode` (mandatory, `silent | visible`) and `required-visibility` (mandatory when `failure-mode: silent`, values `pre-invocation | pre-action`). The loader raises a typed error when the fields are missing or invalid.
- The compiler check refuses to emit a skill admitting model invocation from a `failure-mode: silent` source, and any skill from a `failure-mode: silent` source whose `required-visibility` is `pre-invocation`. Both rejections name the source and the violated rule.
- The existing `clean-memory` command must declare its `failure-mode`. By the checklist it is `silent` (mutates filesystem state) with `required-visibility: pre-action` (explicit user invocation loads the skill before the action runs); its `invocation` is `[user]`. The migration commit adds these fields.
- The author checklist is documented under `docs/guide/` so authors apply the same gate the compiler enforces. The checklist is reproduced verbatim, not paraphrased.
- The Phase 1 always-on regime adapter, when it lands, consumes the same field to decide whether a rule belongs in the always-on body or can ship as a skill that admits model invocation.
- The rule-template migration ([rule-template-format-and-vocabulary](../open-questions/rule-template-format-and-vocabulary.md)) will move the classification from the source-level frontmatter to per-rule fields. The file-level field stays as the source-level placement summary; the per-rule field is the fine-grained version.
- The open question [silent-failure-classification](../open-questions/silent-failure-classification.md) is closed by this ADR.
