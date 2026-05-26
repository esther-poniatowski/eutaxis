# Silent-failure classification criterion

**Severity.** Medium-High.
**Phase-blocking.** Phase 1 (always-on regime — every rule needing
placement).
**Origin.** Refinement of the router-vs-skill conversion proposal,
recorded in
[silent-failure-rules-as-always-on](../adr/silent-failure-rules-as-always-on.md).

## Question

[silent-failure-rules-as-always-on](../adr/silent-failure-rules-as-always-on.md)
introduces the **silent-failure test** as the discriminator between
always-on-body placement and on-demand-skill placement:

> If the rule is absent at the moment the model acts, does the
> resulting failure become visible at review time, or does it pass
> review and surface later as state corruption, security drift, or
> workflow violation?

The test is sound as a verbal criterion but is not yet
operationalised. Three concrete sub-questions:

1. **Author-side classification.** What concrete checklist does a
   rule author apply to land a binary classification? Without one,
   borderline rules (e.g. `target-fidelity` from the global
   interaction rules — edit-wrong-file is sometimes visible,
   sometimes not) drift between authors and across revisions.
2. **Compiler-side enforcement.** Can the compiler refuse to emit a
   skill that carries a silent-failure-prone rule, or is the
   classification purely advisory? If advisory, the gate exists
   only in author discipline.
3. **Audit recoverability.** When a rule has been placed in a
   skill, how does a later reviewer verify that the placement was
   correct? Re-running the test from scratch requires reconstructing
   the failure mode, which is the part most likely to drift.

## Current state

- The verbal test is stated in
  [silent-failure-rules-as-always-on](../adr/silent-failure-rules-as-always-on.md).
- No schema field on a rule carries the classification today; rule
  files in the oikos `instructions/tasks/` set do not declare a
  failure-mode field.
- No checker in the cross-agent compiler inspects placement against
  classification.

The legacy `generate` / `check` pipeline does not exercise this
question because it routes every modular rule through the
router-pointer pattern uniformly.

## Architectural components that depend on this

- The placement gate inside the Phase 1 always-on regime adapter.
- The rule-template schema (see proposal 2 in the session log;
  pending its own ADR). A `failure-mode` field needs a defined
  vocabulary if it is to be enforced.
- Cross-repository source acquisition
  ([cross-repository-source-acquisition](cross-repository-source-acquisition.md))
  — an external rule fragment shipping with the wrong
  classification is harder to detect than a permission widening,
  because the artifact emitted is plain instruction content rather
  than a privilege grant.

## Candidate resolution

The candidate resolution has three parts that should land together:

1. **A binary `failure-mode` field on every rule**, with values
   `silent` and `visible`. Default is `silent` — a rule whose
   author has not classified it is treated as silent-failure-prone
   and routed to the always-on body.
   Silent rules also declare `required-visibility`:
   `pre-invocation` when the rule is needed before deciding which
   procedure applies, or `pre-action` when explicit invocation can
   load the rule before the first irreversible action.
2. **A short author checklist** anchored to concrete failure modes:
   - Does violating this rule mutate filesystem, environment, git,
     or external-service state? → `silent`.
   - Does violating this rule widen permissions, install software,
     or send messages? → `silent`.
   - Does violating this rule write to shared user files
     (`AGENTS.md`, `CLAUDE.md`, settings files) outside the
     compiler's ownership region? → `silent`.
   - Is the rule needed to decide whether a skill or procedure should
     be invoked? → `silent` with `required-visibility:
     pre-invocation`.
   - Does the rule govern only a procedure that the user explicitly
     invoked before any risky action occurs? → `silent` with
     `required-visibility: pre-action`; the rule may travel with that
     procedure.
   - Does violating this rule produce only a suboptimal artifact
     (weaker prose, missing comparison, unsorted output) whose
     defect is visible to the reviewer of the output? → `visible`.
   - When in doubt → `silent`.
3. **A compiler check**: the model-invoked on-demand adapter refuses
   to emit a skill whose rules include any `failure-mode: silent`
   rule. A user-invoked procedure skill may carry
   `failure-mode: silent` rules only when the skill body is loaded
   before the first filesystem, environment, git, external-service,
   or permission mutation. `eutaxis check` surfaces misplacements
   before generation.

Two refinements that should be considered before landing:

- **Granularity.** The classification belongs at the rule level,
  not at the rule-set level. A current oikos task module typically
  mixes both classes; without per-rule classification, the gate
  must be conservative at the file level and over-routes content
  to the always-on body.
- **Activation path as a separate field.** A three-level
  `failure-mode` scale (`silent`, `mixed`, `visible`) was considered
  and rejected as not actionable. Mixed cases split at the rule
  level, while activation path and required visibility carry the
  distinction between model-invoked and user-invoked skills.

## Decision required before

Any release that emits skill artifacts from rule sources that also
contain always-on content. Every oikos task module today fits this
description, so the question blocks the first migration pass.
