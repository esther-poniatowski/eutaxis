# AI prompt - objective and scope

The prompt must clarify **what successful completion means**.

**Rationale:** Clarifying success transforms the prompt into a **goal-directed instruction**, guiding the agent to prioritize relevant material.

**Guidelines:** Define the **end state of knowledge or capability**.

- **Objective specification** should be expressed as a **transformation function**: given input of type X, produce output of type Y satisfying property P. The function-theoretic framing forces the author to identify what constitutes a correct output, not just a plausible one.
- **Scope of application**, to avoid irrelevant material.

*Example*:

```
Objective:
Develop full conceptual and mathematical mastery of deterministic optimal control
sufficient to derive and solve Hamilton–Jacobi–Bellman equations and apply them
to mean-field game models.

Scope restriction:
Focus only on deterministic optimal control.
Do not introduce stochastic control or reinforcement learning
unless explicitly requested.
```

**Avoid**: Vague requests such as "_explain optimal control_", which leads to generic outputs.

Example of weak objective: _"Help the user with their Obsidian notes."_

Example of strong objective: _"Given a Markdown note, audit all mathematical claims for logical completeness, flag any claim presented as a theorem that lacks a preceding proof or citation, and produce a revised version where prose flows as continuous scholarly argument using logical discourse connectors rather than rigid theorem-environment formatting."_