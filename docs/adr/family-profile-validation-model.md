---
tags: []
aliases:
  - Family profiles and a three-tier validation model
index: "[Architecture decisions](_index.md)"
---

# Family profiles and a three-tier validation model

## Status

Accepted.

## Context

A composed prompt ([prompt-shells-and-methodology-bundles](prompt-shells-and-methodology-bundles.md)) can be wrong in several incompatible ways. The shell can fail to render. A required section can be missing. The prose can violate documented prompt-design rules (e.g. token-economy norms). The behaviour the prompt induces in the agent can be wrong even when every structural rule passes.

A validation model that treats every check as a hard error stops the build on style violations; one that treats every check as a warning loses the constraints that actually matter. The model has to distinguish between **what must hold for the prompt to be structurally meaningful** and **what is recommended best practice**, and then between **structural review** and **empirical evaluation**.

## Decision

Each prompt family carries a **profile** (`profile.yaml`) that records both hard requirements and advisory guidance:

```yaml
name: auditor

hard_requirements:
  required_files:
    - prompt.md.j2
    - role.md
    - objective.md
    - output.md
  required_tags:
    - role
    - task

advisory_guidance:
  recommended_regions:
    - role
    - objective
    - scope
    - methodology
    - output
  token_warning_limit: 4000

family_coordination:
  notes:
    - "Scope is partitioned across members."
```

Validation runs against the **composed prompt**, not the fragments, and is organised into three tiers:

- **Tier 1 — Assembly integrity** (automatically enforced; failures block the build).
  - Shell file exists.
  - Every `{% include %}` resolves.
  - Required fragment files are present.
  - The prompt renders to one output.
  - The output length is reported.
- **Tier 2 — Authoring quality** (rule-validated; failures are reported with severity).
  - Prompt prose rules documented in `docs/prompt-writing-methods/`.
  - Section-shape checks declared in the profile.
  - Family-specific style rules.
- **Tier 3 — Behavioural effectiveness** (empirically verified; performed outside the build).
  - Golden prompt review by a human or a supervising agent.
  - Targeted prompt tests with representative inputs.
  - Iteration on the shell informed by observed agent behaviour.

A profile rule is a *hard requirement* only when violating it makes the prompt structurally meaningless. Everything else is advisory. Token-economy norms, recommended region order, and section-shape heuristics are advisory by default. They emit warnings; they do not fail the build.

Every reported fidelity or validation claim also carries an **evidence state**:

- **Structural** — derived from schema, rendering, length, and profile checks only.
- **Smoke-tested** — exercised against at least one representative prompt or task for the target family.
- **Unmeasured** — no behavioural evidence is attached.

`eutaxis explain` reports the evidence state next to each fidelity grade so that a structurally valid prompt is not mistaken for an empirically verified one.

## Discarded alternatives

- **Single tier of hard rules.** Rejected because prompt prose rules are heuristics; treating them as hard would block legitimate prompts that violate them with reason.
- **Single tier of advisory rules.** Rejected because assembly integrity *must* hold (a build that emits an unrendered template is broken); demoting it to advisory loses the build-stop on real bugs.
- **Profile rules apply to fragments**, not the composed prompt. Rejected because the composed prompt is the design artifact ([prompt-family-as-primary-unit](prompt-family-as-primary-unit.md)); validating fragments validates the wrong object.
- **Behavioural validation as part of the build.** Rejected because behavioural evaluation is empirical, possibly remote, and not deterministic; folding it into the build would either gate every rebuild on remote calls or accept silent skips. Tier 3 lives outside the build, with golden review as the discipline.

## Rationale

The three tiers correspond to three distinct failure modes: "the build is broken" (tier 1), "the prompt violates documented authoring rules" (tier 2), and "the prompt does not work in practice" (tier 3). Conflating any pair flattens the design space. Hard validation limited to true invariants is the discipline that keeps the build informative.

## Consequences

- Profiles are checked into the source tree per family.
- Tier 1 failures block `eutaxis generate`; Tier 2 violations emit warnings and a non-zero diagnostic count; Tier 3 is reported via `eutaxis validate` or equivalent, run on demand.
- The `CompositionResult` data carries `diagnostics: tuple[str, ...]` alongside `prompt_text`, `word_count`, and `token_estimate`.
- The `CompositionResult` or adjacent explanation record carries an evidence state for each validation claim. Tier 1 and Tier 2 produce structural evidence by default; Tier 3 upgrades selected claims to smoke-tested when a consuming project supplies prompts and oracles.
- Adding a new advisory rule does not break existing prompts; adding a new hard requirement does and requires a migration.
- Behavioural validation is empirical and remains the responsibility of the consuming project (vitruv, hermeneia, gnomon) — Eutaxis provides the composition layer and the diagnostics, not the agent-evaluation loop.
