# AI Prompt - Constraining the Reasoning Process

## General principles

For agents performing multi-step tasks, the **reasoning schema** must define the computational graph the model should traverse before emitting output. High-quality prompts instruct the agent **how to reason**, not only **what to produce**.

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

Encourage explicit reasoning transparency. When analytical tasks are involved, instruct the agent to make reasoning explicit.

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
| **Standard instruction-following models** | Dominant in production agentic deployments     | Reasoning occurs entirely within the context window and is fully controllable via prompting. | Specify both _what_ the model should reason about and _how_ it should externalize that reasoning.                                                           |
| **Native reasoning models**               | OpenAI o-series, Claude with extended thinking | Internal chain-of-thought executes outside the accessible context window.                    | The design task shifts from _inducing_ reasoning structure to _directing_ reasoning targets — specifying what the model should verify, decompose, or check. |

## Explicit chain-of-thought scaffolding

**Standard instruction-following models.** The primary technique is **chain-of-thought scaffolding**: require the model to _externalize intermediate reasoning_ in a designated _scratchpad section_ before producing committed output. Two benefits:

1. The model's generative process is constrained to pass through interpretable intermediate states.
2. Errors localize to specific reasoning steps, enabling targeted correction.

Warning

Visible reasoning traces are not guaranteed to be _causally faithful_. The written steps may rationalize rather than generate the output, so error localization via scratchpad is heuristically useful but epistemically unreliable.

The boundary between the scratchpad and the output must be explicit and structural: "content within `<reasoning>` tags constitutes internal scaffolding and must not appear in the final response; content within `<output>` tags constitutes the committed response." Failure to enforce this boundary causes the model to either suppress useful reasoning (if it treats all output as committed) or pollute the response with scratchpad content.

**Native reasoning models**. Imposing an explicit scratchpad section is either redundant (the model already maintains internal reasoning) or actively harmful (it consumes context budget for a process the model handles more effectively without structural constraint). For these configurations, the design effort should be directed toward specifying **verification conditions** and **decomposition targets** rather than output boundaries — state what the model should check, not how it should think.