---
tags:
  - index
aliases:
  - Architecture decisions
index: "[Eutaxis](../index.md)"
---

# Architecture decisions

Accepted architecture decisions for Eutaxis, organised by scope:

- **Framework.** Cross-cutting decisions about what Eutaxis is and
  how it composes its capabilities.
- **Prompt composition.** Decisions specific to the prompt-composition
  framework (prompt families, methodology bundles, validation tiers).
- **Cross-agent commands.** Decisions specific to the commands
  subsystem (Agent Skill artifacts compiled from one source for
  Claude Code and Codex).
- **Superseded.** Earlier decisions retained for historical context.

Open architectural questions — items the ADR set does not resolve —
live under [`docs/open-questions/`](../open-questions/_index.md).

## Framework

- [Eutaxis as a build-time compiler, not a runtime activation mechanism](compiler-not-runtime-activation.md)
- [Same source, not same behaviour: declared per-target fidelity](same-source-not-same-behaviour.md)
- [Activation regime as the classification axis](activation-regime-as-classification-axis.md)
- [Silent-failure rules as always-on](silent-failure-rules-as-always-on.md)
- [Failure-mode classification as a source field](failure-mode-as-source-field.md)
- [Rule sources as structured templates](rule-sources-as-structured-templates.md)
- [Four-axis instruction decomposition](four-axis-instruction-decomposition.md)
- [Two source kinds: instruction content and capability configuration](two-source-kinds-instruction-vs-capability.md)
- [Native precedence, not a parallel resolution engine](native-precedence-over-parallel-engine.md)
- [Convergence on the Agent Skills open standard](convergence-on-agent-skills-standard.md)
- [Golden-file review as the correctness contract](golden-file-review-as-correctness-contract.md)

## Prompt composition

- [Prompt family as the primary organising unit](prompt-family-as-primary-unit.md)
- [Prompt shells and parameterised methodology bundles](prompt-shells-and-methodology-bundles.md)
- [Family profiles and a three-tier validation model](family-profile-validation-model.md)
- [Generalisation requires demonstrated maintenance pressure](generalization-by-demonstrated-pressure.md)

## Cross-agent commands

- [Agent Skills as the command target surface](agent-skills-as-target-surface.md)
- [Multi-file rendered artifact model](multi-file-artifact-model.md)
- [Adapter-passthrough frontmatter and files in the source schema](adapter-passthrough-source-schema.md)
- [Dual ownership marker: sidecar plus frontmatter key](dual-ownership-marker.md)
- [Instruction-file ownership boundaries (navigation only)](instruction-file-ownership-boundaries.md)
- [Regime translation and permission mapping per adapter](regime-and-permission-mapping.md)
- [Install registry: atomicity and locking](registry-atomicity-and-locking.md)

## Superseded

- [Prompt-level component activation](prompt-level-component-activation.md)
