# Architecture decisions

Accepted architecture decisions for Eutaxis, organised by scope:

- **Framework.** Cross-cutting decisions about what Eutaxis is and how it composes its capabilities.
- **Prompt composition.** Decisions specific to the prompt-composition framework (prompt families, methodology bundles, validation tiers).
- **Cross-agent commands.** Decisions specific to the commands subsystem (Agent Skill artifacts compiled from one source for Claude Code and Codex).
- **Superseded.** Earlier decisions retained for historical context.

Open architectural questions — items the ADR set does not resolve — live under [open-questions](../open-questions/_index.md).

```{toctree}
:maxdepth: 1
:caption: Framework

compiler-not-runtime-activation
same-source-not-same-behaviour
activation-regime-as-classification-axis
silent-failure-rules-as-always-on
rule-sources-as-structured-templates
four-axis-instruction-decomposition
two-source-kinds-instruction-vs-capability
native-precedence-over-parallel-engine
convergence-on-agent-skills-standard
golden-file-review-as-correctness-contract
```

```{toctree}
:maxdepth: 1
:caption: Prompt composition

prompt-family-as-primary-unit
prompt-shells-and-methodology-bundles
family-profile-validation-model
generalization-by-demonstrated-pressure
```

```{toctree}
:maxdepth: 1
:caption: Cross-agent commands

agent-skills-as-target-surface
multi-file-artifact-model
adapter-passthrough-source-schema
dual-ownership-marker
regime-and-permission-mapping
registry-atomicity-and-locking
```

```{toctree}
:maxdepth: 1
:caption: Superseded

prompt-level-component-activation
```
