# Behavioural validation gap

**Severity.** Medium.
**Phase-blocking.** None — the correctness contract has been
reframed.
**Origin.** Adversarial review of the cross-agent compiler proposal,
objection O7.

## Question

Golden-file review verifies **what was emitted**, not **what the agent
does with it**. The framework currently relies on
[golden-file-review-as-correctness-contract](../adr/golden-file-review-as-correctness-contract.md)
as the explicit correctness contract; the README also references
behavioural testing and profile-based validation as project
capabilities. The proposal contains no behavioural-validation loop,
no contract tests against the agents' actual responses, no oracle for
"this output style actually makes Claude write differently".

For an architecture whose advertised guarantee is "same source, not
same behaviour"
([same-source-not-same-behaviour](../adr/same-source-not-same-behaviour.md)),
the absence of behavioural validation means the fidelity grades are
**claimed**, not **measured**.

## Current state — contract reframed, gap remains

The build-time stance
([compiler-not-runtime-activation](../adr/compiler-not-runtime-activation.md))
makes deterministic emission the contract Eutaxis can credibly
deliver. The golden-file ADR documents this explicitly: the contract
is reproducible artifact generation, not behavioural equivalence.
This **closes the false-claim risk** the review raised — Eutaxis no
longer suggests behavioural correctness it cannot verify.

What remains open: whether to **add** a behavioural-validation phase
as a complement to the build-time contract. Three motivations:

- The fidelity grades in `eutaxis explain` are advisory until
  behavioural evidence backs them.
- The prompt composition framework
  ([family-profile-validation-model](../adr/family-profile-validation-model.md))
  Tier 3 — empirical evaluation — currently lives outside the build
  by design; whether Eutaxis ships a Tier-3 harness is open.
- Cross-agent drift (the same source producing divergent observable
  behaviour) is invisible without behavioural smoke prompts.

## Architectural components that depend on this

- The fidelity vocabulary in
  [same-source-not-same-behaviour](../adr/same-source-not-same-behaviour.md).
- The Tier-3 row of
  [family-profile-validation-model](../adr/family-profile-validation-model.md).
- Any release that promises "verified" behaviour rather than
  "compiled" behaviour.

## Candidate resolution

- **Behavioural validation as an optional follow-up phase.** Smoke
  prompts run against each target with the compiled configuration;
  responses compared against expected signatures. Not gated into
  `eutaxis generate`; invoked via a separate command (`eutaxis
  validate` or `eutaxis behavioural-check`).
- **Owned by the consuming project, not the framework.** vitruv,
  hermeneia, gnomon already define quality criteria; the behavioural
  loop is a project concern. Eutaxis supplies the harness shape; the
  prompts and oracles are project-defined.
- **Surface the gap in `eutaxis explain`.** When a fidelity grade is
  Approximate and no behavioural evidence is attached, the report
  marks it `unmeasured`. Structural checks produce `structural`
  evidence; smoke prompts supplied by a consuming project produce
  `smoke-tested` evidence.

The evidence label prevents a structural guarantee from being read as
a behavioural guarantee. A compiled artifact can be structurally
valid while the receiving agent still fails the intended workflow.

## Decision required before

No release is currently blocked on this. The decision is whether
behavioural validation joins the framework as a v2 feature or
remains a per-consumer responsibility.
