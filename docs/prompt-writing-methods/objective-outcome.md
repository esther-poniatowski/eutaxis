# AI Prompt - Objective and Outcome

The prompt must clarify **what successful completion means**.

A vague request such as "_explain optimal control_" leads to generic outputs. Instead, define the **end state of knowledge or capability**.

**Rationale:** This transforms the prompt into a **goal-directed instruction**, guiding the agent to prioritize relevant material.

**Guidelines:** Define:

- the learning objective  
- the final competence  
- the scope of application  

*Example*:

```
Objective:
Develop full conceptual and mathematical mastery of deterministic optimal control
sufficient to derive and solve Hamilton–Jacobi–Bellman equations and apply them
to mean-field game models.
```



---

**Objective specification** should be expressed as a **transformation function**: given input of type X, produce output of type Y satisfying property P. The function-theoretic framing forces the author to identify what constitutes a correct output, not just a plausible one.

Example of weak objective: _"Help the user with their Obsidian notes."_

Example of strong objective: _"Given a Markdown note, audit all mathematical claims for logical completeness, flag any claim presented as a theorem that lacks a preceding proof or citation, and produce a revised version where prose flows as continuous scholarly argument using logical discourse connectors rather than rigid theorem-environment formatting."_