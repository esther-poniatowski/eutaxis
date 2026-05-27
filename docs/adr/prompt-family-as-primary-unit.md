---
tags: []
aliases:
  - Prompt family as the primary organising unit
index: "[Architecture decisions](_index.md)"
---

# Prompt family as the primary organising unit

## Status

Accepted.

## Context

Eutaxis provides two related but distinct capabilities. One is the cross-agent configuration compiler that emits instruction files, skills, and other native artifacts on multiple agents (see [compiler-not-runtime-activation](compiler-not-runtime-activation.md)). The other is a **prompt composition framework**: tooling and method for authoring, composing, validating, and revising structured agent prompts — primarily the system-prompt-level artifacts that downstream projects (vitruv, hermeneia, gnomon) consume.

The composition capability needs its own organising unit. A taxonomy of "task postures" or "agent roles" abstracted ahead of evidence risks pre-committing to a structure no actual prompt fits. The existing concrete examples — vitruv's `architecture/auditor`, hermeneia's `documentation/auditor` — are coherent families: members that share methodology and report shape, scoped to a domain, with one member per scope partition (component / interaction / model in vitruv; sentence / paragraph / section in hermeneia).

Two design choices follow from this observation. First, what is the unit of reuse: a single prompt, a family of prompts, or a typology of families? Second, what is the unit of design review: the assembled output that the agent sees, or the file fragments the author edits?

## Decision

The **prompt family** is the first-class organising unit. A family is a coherent group of prompts (`auditor`, `composer`, `reviewer`) that share methodology and report contract, distinguished by domain (`architecture`, `documentation`) and by an internal scope partition (`component`, `interaction`, `model`).

The **composed prompt** is the primary design artifact. The fully assembled prompt — methodology bundles expanded, local fragments included, length reported — is the surface on which design review, golden-file diff, and empirical testing operate. File fragments are authoring inputs; the composed prompt is the design output.

These two choices interlock. The family supplies the reuse boundary (shared methodology bundle, family profile); the composed prompt supplies the review boundary (one rendered file per prompt, diffable, testable, length-bounded).

Reuse happens at the largest stable semantic unit. Methodology bundles are coarse: an audit methodology shared by every auditor in the family. Micro-block registries are not introduced; small repeated fragments stay inline until repetition makes them load-bearing (see [generalization-by-demonstrated-pressure](generalization-by-demonstrated-pressure.md)).

## Discarded alternatives

- **Abstract task taxonomy as primary unit.** Rejected: a typology of postures (`reviewer`, `auditor`, `analyst`) abstracted in advance forces every concrete prompt into a category that may not fit its actual structure. The family unit is concrete and grounded in existing artifacts.
- **Single prompt as primary unit.** Rejected because family coordination is load-bearing: members of a family partition a domain (one auditor per scope) and that partitioning is a designable property, not an emergent one.
- **File fragment as design artifact.** Rejected: reviewing fragments is reviewing inputs to a process whose output is the thing the agent actually reads. Length, ordering, and section transitions are properties of the composed prompt; they are invisible at fragment level.
- **Micro-block registry as the reuse unit** (each paragraph or bullet point reusable). Rejected because text that changes together should live together; a registry of micro-blocks introduces a coordination layer that the actual maintenance patterns do not warrant.

## Rationale

The prompt family matches the existing concrete artifacts and the existing maintenance patterns. The composed prompt is what the agent reads; reviewing anything else is reviewing the wrong object. Reuse at coarse units (family methodology bundles) defers the registry complexity until it is genuinely needed.

## Consequences

- The source model carries `PromptFamily`, `PromptDefinition`, `PromptProfile`, and `CompositionResult` as first-class types.
- The composition mechanism (Jinja2 shells, methodology bundles) is a separate decision; see [prompt-shells-and-methodology-bundles](prompt-shells-and-methodology-bundles.md).
- Hard versus advisory validation of family profiles is a separate decision; see [family-profile-validation-model](family-profile-validation-model.md).
- Promotion of a fragment to a higher reuse tier follows the demonstrated-pressure rule; see [generalization-by-demonstrated-pressure](generalization-by-demonstrated-pressure.md).
- The composition capability and the cross-agent compiler capability are **distinct features** of the eutaxis package. Both ship; both have their own ADR set.
