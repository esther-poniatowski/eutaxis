
# AI Prompt - Role and Domain Expertise

**Principle**: The role specifies **what type of expert the agent must emulate**.

**Rationale:** Language models condition strongly on role framing. The role establishes the prior distribution over behaviors, influencing:

- terminology, vocabulary
- conceptual depth, reasoning
- citation patterns
- proof style

**Guidelines:** Explicitly state

- Domain of expertise / discipline (e.g., "a formal methods researcher specializing in type theory")
- Epistemic posture, methodological orientation if relevant (e.g., "assumes the interlocutor has graduate-level mathematical maturity")
- Relational stance (e.g., "operates as a collaborator, not a service provider")

**Avoid**: Vague attributions ("expert assistant", "helpful AI") — these are near-zero-information priors.

_Example_:

```
Role:
Act as a research-level mathematician specializing in optimal control and Hamilton–Jacobi theory.
Provide explanations suitable for a graduate researcher with strong mathematical background.
```




