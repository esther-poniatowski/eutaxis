# AI prompt - constraints and evaluation criteria

## Constraint formulation

The prompt may specify **quality standards**.

Constraints partition into two classes:

**Positive constraints** (invariants that must hold): formulate as necessary conditions on output. Use modal language: "every mathematical claim **must** be accompanied by a justification", not "try to justify claims".

**Negative constraints** (prohibited behaviors): these are often more brittle and require careful formulation.

Two common failure modes:

- **Overly broad negation**: "do not use bullet points" applied globally may suppress valid list usage. Qualify with scope: "do not use bullet points in repaired content sections; structured enumeration is permitted in audit logs."
- **Missing boundary conditions**: "do not produce content that is superficial" is unverifiable. Instead, specify the positive condition: "every claim must be grounded in a definition, lemma, or referenced result that appears within the same note or is cited explicitly."

_Example_:

```
Quality criteria:
- All claims must be justified.
- Concepts must be introduced progressively.
- Explanations must avoid unnecessary repetition.
```

**Priority ordering** among constraints must be explicit. When two constraints conflict under adversarial or edge inputs, the model may resolve the conflict through recency, salience, learned priors, or local plausibility rather than the author's intent.

*Example*: _"if constraints C1 and C2 conflict, C1 takes precedence."_

## Verification and post-conditions

Specifying _what the model must verify before committing output_ is one of the main levers for directing hidden or extended reasoning toward the right checks. For models whose reasoning is not exposed or should not be micromanaged, verification conditions are usually more robust than prescribed reasoning traces.

The instruction file should specify:

- **Output post-conditions**: what must be checked before the final answer is committed (e.g., "verify that every assumption used in the proof is listed in the assumptions section")
- **Assumption validation**: which premises or intermediate results must be confirmed before being treated as established
- **Halt conditions**: which conditions require stopping and surfacing ambiguity rather than proceeding (e.g., "if the derivation requires an assumption not declared in the contract, halt and report")
- **Completion criteria**: what counts as task completion — the verifiable conjunction that distinguishes a finished output from a partial one

**Evaluation metrics** should distinguish:

- task success
- format compliance
- citation/grounding fidelity
- tool-use correctness
- refusal/safety behavior
- latency and token cost
