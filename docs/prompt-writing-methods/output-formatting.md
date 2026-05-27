---
tags: []
aliases:
  - AI Prompt - Output Formatting
index: "[Prompt writing methods](_index.md)"
---

# AI prompt - output formatting

**Principles**:

- Output format specification should be **generative**, not descriptive.
- Provide examples of expected output. Demonstrations improve alignment.
- If possible, provide a **template** the output must instantiate rather than listing properties the output should have. _Every constraint that can be expressed as a template or schema property should be expressed in a template rather than in the prompt_.

Prompts and template hold complementary roles in the instruction system:

- The prompt indicates the agent _why_ each field matters; the template ensures the agent _cannot_ produce a malformed artifact.
- Prose instructions cover only what schemas cannot enforce — semantic intent, edge-case rationale, and cross-field consistency that exceeds schema expressiveness.

**Rationale**: Precise formatting rules help produce **structured and reusable outputs**. Templates eliminate a class of interpretation errors and compliance failure that prose instructions can only discourage.

| **Type of output**                  | Template content                                                                           |
| ----------------------------------- | ------------------------------------------------------------------------------------------ |
| **Prose outputs**                   | - Document structure (sections, ordering)<br>- Tables<br>- Numbered lists<br>- Code blocks |
| **Structured outputs (JSON, YAML)** | Formal schemas (e.g. enum-constrained fields, required/optional annotations, typed values) |

*Example*:

```
Formatting:
- Use numbered sections
- Present formulas in LaTeX
- Provide examples in clearly labeled blocks

Example output structure:

Concept: Value Function

Motivation
...

Formal definition
...

Theorem (Dynamic Programming Principle)
...
```

