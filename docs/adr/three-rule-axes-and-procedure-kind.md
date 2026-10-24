---
tags: []
aliases:
  - Three rule axes and the procedure kind
index: "[Architecture decisions](_index.md)"
---

# Three rule axes and the procedure kind

## Status

Accepted. Supersedes the former four-axis formulation.

## Context

Instruction sources constrain either an artifact or an externally observable course of action. Treating both as rules obscures their different contracts. A rule is evaluated against an artifact or decision. A procedure has preconditions, an action graph, effects, invariants, and postconditions. The earlier four-axis model made `procedure` both a rule axis and a declaration kind, so the same source could not be classified unambiguously.

## Decision

Rules use one of three primary-function axes:

- `reasoning-target` states what must be established, checked, derived, or verified
- `output-structure` states the visible organization of an artifact
- `surface-style` states how visible content is phrased

Procedures are a separate declaration kind. A procedure represents an externally observable action graph, such as a git workflow, deployment sequence, tool operation with state effects, or multi-agent handoff. A procedure does not carry a rule `axis` field.

Rules on the reasoning-target axis specify the property that the answer must satisfy and the evidence that can establish it. They do not prescribe an internal reasoning trace. Output-structure and surface-style rules govern the artifact, not hidden reasoning.

An instruction unit that contains both artifact constraints and an action graph splits into a rule set and a procedure. The two declarations may reference each other, but each keeps its own evaluator and lifecycle.

## Vocabulary

| Term | Meaning |
| --- | --- |
| Rule | One constraint evaluated against an artifact or decision |
| Rule set | A coherent group of rules with member identifiers |
| Procedure or workflow | A finite externally observable action graph |
| Task | The runtime request being handled |

## Discarded alternatives

- **Procedure as a fourth rule axis.** Rejected because a procedure requires a different body and validation contract.
- **No procedure kind.** Rejected because externally observable action graphs are legitimate instruction artifacts and do not fit the three rule axes.
- **Procedure for internal reasoning.** Rejected because an imposed reasoning trace can constrain a model without adding an observable acceptance condition.
- **Domain axes such as epistemology or argumentation.** Rejected because domain, failure mode, activation, and ownership are orthogonal metadata rather than primary rule functions.

## Consequences

- The rule-axis enum is closed to `reasoning-target | output-structure | surface-style`.
- The structured-source migration converts `prose-authoring-workflow` and `batch-commit-splitting` into procedure declarations, not rules with `axis: procedure`.
- The directory migration separates `instructions/rules/` from `instructions/procedures/` after the structured-source pilot passes.
- Mixed legacy modules are split by declaration kind during migration; line count alone never triggers a split.
- Composition manifests may select both rule sets and procedures, while evaluators and renderers handle their different contracts.
- The detailed discipline for reasoning targets remains in [instruction axes](../prompt-writing-methods/instruction-axes.md).
