
Designing instructions for an AI agent requires structuring the prompt as a **specification of behavior** rather than a simple request. Effective instructions reduce ambiguity, define objectives precisely, and constrain the reasoning process of the agent. The most robust prompts resemble **technical protocols**: they define the role, scope, procedure, and expected outputs.

A strong prompt typically resembles a **technical specification**:

1. [Role and Domain expertise](role-domain-expertise.md)
2. [Objective and outcome](objective-outcome.md)
3. [Target audience and context](target-audience.md)
4. [Structural instructions](structural-instructions.md)
5. [Reasoning process](reasoning-process.md)
6. [Style and tone](style-tone.md)
7. [Output formatting](output-formatting.md)
8. [Scope](scope.md)
9. [Evaluation criteria](evaluation-criteria.md)
10. [Iterative interation rules](iterative-interation-rules.md)

*Example*:

```
Role
Act as a research-level mathematician specializing in optimal control theory.

Objective
Develop a rigorous understanding of deterministic optimal control,
including Hamilton–Jacobi–Bellman equations and the Pontryagin
Maximum Principle.

Audience
Graduate-level reader familiar with analysis and linear algebra.

Structure
For each concept provide:
1. Motivation
2. Informal intuition
3. Formal definition
4. Main theorem(s)
5. Proof sketch
6. Complete proof
7. Worked examples
8. Common pitfalls

Reasoning rules
- Every theorem must include assumptions.
- Proofs must be detailed and constructive.

Style
- Formal academic tone
- No personal pronouns
- Introduce formulas with verbal explanations

Scope
Focus exclusively on deterministic optimal control.

Goal
Enable the reader to derive and solve Hamilton–Jacobi–Bellman equations independently.
```

