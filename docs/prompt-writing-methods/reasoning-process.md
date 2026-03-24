# AI Prompt - Constraining the Reasoning Process

High-quality prompts instruct the agent **how to reason**, not only **what to produce**.

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