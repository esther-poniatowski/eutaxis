# AI Prompt - Constraining the Reasoning Process

## General principles

For agents performing multi-step tasks, the **reasoning schema** must define the checks, decompositions, and external artifacts that should exist before committed output. Depending on the model class, high-quality prompts either guide the reasoning trace directly or specify the targets that the model's hidden reasoning must satisfy.

**Rationale**: This prevents superficial explanations and encourages systematic reasoning.

Possible reasoning constraints include:

- derive results step by step
- justify each non-trivial statement
- highlight assumptions
- distinguish intuition from formal proof

*Example*:

```
Reasoning requirements:
- Every theorem must include a clear list of assumptions.
- Proofs must be constructive whenever possible.
- Intuition must precede formalism.
```

Encourage explicit reasoning transparency when the model and task benefit from visible derivations. For native reasoning models, prefer concise reasoning summaries or verification artifacts unless the task requires an inspectable derivation.

*Example*:

```
Each derivation must clearly indicate:
- the starting equation
- each transformation step
- the mathematical property used
```

## Dependence on model architecture

> [!WARNING] Distinct reasoning schema designs are required for different classes of models.

**Model-class taxonomy:**

| Model                                     | Context                                        | Characteristic                                                                               | Consequences for prompt design                                                                                                                              |
| ----------------------------------------- | ---------------------------------------------- | -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Standard instruction-following models** | Non-reasoning or low-latency execution models | No separate hidden reasoning-token budget is exposed. Visible intermediate reasoning can be prompted when useful. | Specify both _what_ the model should reason about and, when needed, _how_ it should externalize that reasoning. |
| **Native reasoning models**               | OpenAI o-series, Claude with extended thinking | The model has a separate hidden or extended reasoning path; raw reasoning is not a normal prompt-controlled output artifact. | The design task shifts from _inducing_ reasoning structure to _directing_ reasoning targets: specify success criteria, verification conditions, decomposition targets, and output contracts. |

## Explicit chain-of-thought scaffolding

**Standard instruction-following models.** The primary technique is **chain-of-thought scaffolding**: require the model to _externalize intermediate reasoning_ in a designated _scratchpad section_ before producing committed output. Two benefits:

1. The model's generative process is constrained to pass through interpretable intermediate states.
2. Errors localize to specific reasoning steps, enabling targeted correction.

Warning

Visible reasoning traces are not guaranteed to be _causally faithful_. The written steps may rationalize rather than generate the output, so error localization via scratchpad is heuristically useful but epistemically unreliable.

The boundary between the scratchpad and the output must be explicit and structural: "content within `<reasoning>` tags constitutes internal scaffolding and must not appear in the final response; content within `<output>` tags constitutes the committed response." Failure to enforce this boundary causes the model to either suppress useful reasoning (if it treats all output as committed) or pollute the response with scratchpad content.

**Native reasoning models**. External chain-of-thought scaffolds are not the default control mechanism for native reasoning models. The model already allocates hidden reasoning, so a visible scratchpad often duplicates work and consumes context. A prescribed action sequence can also degrade performance when it forces the model through a weaker human-written plan.

For these configurations, prompt design should usually specify **reasoning targets** rather than **reasoning traces**. Reasoning targets include:

- the success criteria the answer must satisfy
- the subproblems the model must decompose
- the assumptions, edge cases, and failure modes the model must check
- the verification conditions the final answer must pass
- the required output contract

This guidance is not an absolute ban on stepwise structure. External steps remain appropriate when the task needs inspectable intermediate artifacts, reproducible process boundaries, tool choreography, compliance evidence, or a teaching-oriented derivation. In those cases, the steps should describe the required external work product, not attempt to micromanage the model's hidden reasoning process.
