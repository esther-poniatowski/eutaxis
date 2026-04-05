# AI Prompt - Structure

Designing instructions for an AI agent requires structuring the prompt as a **specification of behavior** rather than a simple request.

## Sections ordering

The most robust prompts resemble **technical protocols**: they define the role, scope, procedure, and expected outputs.

For a _single-agent system prompt_, a strong default template is:

1. [Role and Domain expertise](role-domain-expertise.md)
2. [Target audience and background](target-audience-background.md)
3. [Objective, scope, outcome](objective-scope-outcome.md)
4. [Context and grounding policy](context-grounding-policy.md) (source types, trust boundaries, citation, conflict resolution)
5. [Constraints and evaluation criteria](constraints-evaluation-criteria.md)
6. [Structural instructions](structural-instructions.md)
7. [Reasoning process](reasoning-process.md)
8. [Style and tone](style-tone.md)
9. [Output formatting](output-formatting.md)
10. [Edge cases and fallback policy](edge-case-fallback-policy.md)
11. [Iterative interation rules](iterative-interation-rules.md)


> [!IMPORTANT]
> Each section should be:
> - _exhaustive over its domain_,
> - _non-redundant with adjacent sections_.

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

## Hierarchy within sections

Hierarchical structure is justified only when:

- the rules themselves have genuine logical hierarchy — when child rules are properly _instances_ or _refinements_ (special cases) of a parent rule,
- it provides the decision procedure for novel cases in the rule's domain — when a parent rule encodes the _generative principle_ that governs how to handle cases not covered by any child rule (even when children are interpretable without it).

In all other cases, the dominant format remains flat tagged blocks with contrastive examples and a `<note>` field encoding non-obvious implications.

Valid hierarchy: the parent rule is a general principle; the children partition its application space.

```
Constraint: Prose must not substitute enumeration for argumentation.
  ├─ Lists are forbidden inside "repaired content" sections.
  ├─ Logical relationships must be expressed via connectors
  │   (consequently, it follows that, by contrast, more precisely).
  └─ A sequence of three or more short sentences on the same topic
      must be fused into a single argumentative paragraph.
```

Invalid hierarchy: siblings rules are orthogonal. The indentation implies a derivation that does not exist and wastes the model's attention on a spurious structural signal. A flat list, or better, a properly tagged section, is more honest.

```
Writing constraints:
  ├─ Use formal tone.
  ├─ Avoid contractions.
  └─ Do not use bullet points.
```

**Practical criterion**: If removing the parent rule leaves the children fully interpretable and complete, the hierarchy is "cosmetic".

> [!Warning] This condition is _sufficient_ for eliminating hierarchy, but not _necessary_.

## Multi-agent extension

For a **controller prompt** in a hierarchical agent architecture, two additional sections are required that have no analog in single-agent design:

- **Subagent taxonomy**: enumerates each subordinate agent, its scope, and its authority boundary — what each subagent may decide autonomously and what requires escalation.
- **Trust model specification**: declares that subagent outputs constitute structured data inputs, not trusted instructions. This is a specific instantiation of the context and grounding policy (section 4 above) applied to agent-generated content rather than external documents.