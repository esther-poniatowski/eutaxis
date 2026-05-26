# Four-axis instruction decomposition

## Status

Accepted.

## Context

[activation-regime-as-classification-axis](activation-regime-as-classification-axis.md) partitions components by *when and how* they activate. [rule-sources-as-structured-templates](rule-sources-as-structured-templates.md) fixes the schema-level shape of a rule source. Neither decides *what kinds of constraint a rule expresses* — the source-side classification that sits below the regime and inside the schema.

The session that produced this ADR surfaced two coupled problems that the existing decisions do not resolve:

1. **Pollution between dimensions of an instruction.** Authored rules routinely conflate the content the model should verify, the shape the artifact should take, the wording it should use, and the action sequence the agent should follow. Requests that fail to separate these dimensions cause reasoning-mode pollution (a request for mathematical analysis induces academic register; a request for pedagogical style flattens rigor). The dimensions express different primary functions, but the authoring vocabulary does not keep those functions separate.
2. **Trace-based instruction of reasoning models.** The default authorial mode prescribes an action sequence ("first do X, then Y, then Z"). For native reasoning models, externalised sequence prescriptions can waste context and can harm quality when they constrain a stronger internal plan, per [reasoning-process](../prompt-writing-methods/reasoning-process.md). The dominant authoring pattern in the oikos `instructions/tasks/` set is sequence-shaped; the corrective discipline needs to be stated explicitly.

Two further vocabulary collisions worsen the situation. The directory `instructions/tasks/` uses *task* both for the rule artifact and for the runtime sense of a user-issued instance of work. *Process*, *procedure*, *workflow*, and *task* are used interchangeably in surrounding documentation.

## Decision

Authored instructions classify along **four primary-function axes**:

1. **Reasoning targets** — what the model must check, derive, decompose, or verify. Static (criterion-shaped).
2. **Output structure** — the shape of the produced artifact. Static (form-shaped).
3. **Surface style** — the phrasing of the produced artifact. Static (surface-shaped).
4. **Procedure** — an action graph with externally observable state effects. Temporal (trajectory-shaped).

The four axes are meant to separate concerns, not to prove formal orthogonality. A rule may have secondary effects across axes, but its source declaration records the primary function that governs validation, rendering, and composition.

**Within-axis discipline for non-procedure axes**: rules on the reasoning-target axis specify *reasoning targets*, not *reasoning traces*. A reasoning-target rule names the property the answer must hold and the means by which the property can be checked. It does not prescribe the order in which the model considers the property or the inner reasoning steps the model writes down. Output structure and surface style rules govern the visible artifact, not the hidden reasoning path. Five canonical reasoning-target sub-shapes — success criteria, subproblems, assumptions and edge cases, verification conditions, output contract — are documented in [instruction-axes](../prompt-writing-methods/instruction-axes.md) together with a worked example of converting a procedural methodology to reasoning-target form.

**Applicability of the procedure axis** is restricted to action graphs an external observer could record by inspecting state changes — git workflows, tool-use sequences with environment side effects, multi-agent handoffs. A rule that prescribes an internal reasoning chain is reauthored as reasoning-target rules, never as a procedure.

**Vocabulary**:

| Term | Refers to |
| --- | --- |
| **Rule** | A single authored constraint along one axis. |
| **Rule set** | A coherent group of rules addressing one aspect of behaviour. |
| **Procedure** (or **workflow**) | An action graph along the procedure axis. |
| **Task** | A runtime invocation — what the user asked the agent to do in this session. |

The directory `instructions/tasks/` is to be renamed to `instructions/rules/` (rule sets) and `instructions/procedures/` (when procedures are authored). The renaming is performed during the migration tracked by [rule-sources-as-structured-templates](rule-sources-as-structured-templates.md).

## Discarded alternatives

- **Two axes: process vs criteria.** Rejected as too coarse. Collapses surface style into either of the two; the resulting rules then fail to separate phrasing from content, which is the dominant pollution observed in the current set.
- **Three axes: reasoning targets, output structure, surface style (omitting procedure).** Rejected after session discussion. Procedural authoring is legitimately needed for external action graphs (git workflows, handoff protocols); removing the axis forces those rules into one of the other three, where they fit poorly.
- **Five axes: split reasoning targets into "what to verify" and "what to decompose".** Rejected as not orthogonal. The two sub-shapes are both reasoning targets in the formal sense; the within-axis sub-shapes (success criteria, subproblems, edge cases, verification conditions, output contract) are documented in [instruction-axes](../prompt-writing-methods/instruction-axes.md) but do not require their own top-level axes.
- **Action-graph encoding for reasoning rules.** Rejected per the model-class evidence in [reasoning-process](../prompt-writing-methods/reasoning-process.md): externalised trace prescriptions can waste context and can harm native reasoning models when they overconstrain the model's internal plan. The within-axis discipline (reasoning targets, not reasoning traces) is the corrective.
- **Preserve the `instructions/tasks/` naming.** Rejected on vocabulary-collision grounds; *task* must refer to the runtime invocation, not the rule artifact.

## Rationale

The four-axis cut delivers three properties simultaneously:

- **Concern separation.** A rule set targeting one primary function can be composed with rule sets targeting other functions while making cross-axis effects explicit. This is the structural defence against the observed style-vs-reasoning interference.
- **Compositional algebra.** Skills assemble from rule sets and procedures along axes, with mechanical addition and subtraction of rule identifiers. The classification axis matches the composition algebra.
- **Reasoning-model safety.** The within-axis discipline keeps reasoning-target rules free of trace prescriptions, which preserves the receiving model's internal reasoning budget for substantive work rather than externalised scaffolding.

The procedure axis remains in the taxonomy because authentic action-graph constraints exist; restricting its applicability to externally observable state effects prevents it from absorbing content that belongs in the reasoning-target axis.

## Consequences

- The migration from the current oikos `instructions/tasks/` set to structured templates ([rule-sources-as-structured-templates](rule-sources-as-structured-templates.md)) classifies each existing rule along one of the four axes and records the axis as a schema field ([rule-template-format-and-vocabulary](../open-questions/rule-template-format-and-vocabulary.md)).
- The directory rename (`instructions/tasks/` → `instructions/rules/` and `instructions/procedures/`) is part of the migration. Existing references to "task module" throughout user instructions and CLAUDE.md / AGENTS.md content are reauthored to use *rule set* or *procedure* as appropriate.
- Rule sources gain an `axis` field ([rule-template-format-and-vocabulary](../open-questions/rule-template-format-and-vocabulary.md)) whose values are `reasoning-target | output-structure | surface-style | procedure`. The compiler validates that the body has the declared primary axis and flags mixed-axis content that needs splitting or an explicit secondary annotation.
- Compositional skills assemble from rule sets across axes rather than from a single monolithic task module, per the composition algebra surfaced in the session. Composition inherits [intra-artifact-composition](../open-questions/intra-artifact-composition.md) and [identifier-and-namespace-algebra](../open-questions/identifier-and-namespace-algebra.md).
- The procedure axis's restricted applicability is enforced at authoring time: a rule declared as `axis: procedure` whose body prescribes internal reasoning steps is flagged by the compiler for reauthoring as reasoning targets.
- Full explanatory content, with the gnomon question-hierarchy worked example, lives in [instruction-axes](../prompt-writing-methods/instruction-axes.md). The ADR records the decision; the prompt-writing-method note records the discipline.
