---
tags: []
aliases:
  - Prompt shells and parameterised methodology bundles
index: "[Architecture decisions](_index.md)"
---

# Prompt shells and parameterised methodology bundles

## Status

Accepted.

## Context

Once the prompt family is the organising unit ([prompt-family-as-primary-unit](prompt-family-as-primary-unit.md)) and the composed prompt is the design artifact, the question becomes: how is the composed prompt assembled? The legacy implementation used `generate.py` as a naive Markdown concatenator with no structural awareness; it could not distinguish a coherent prompt from an arbitrary join. Phantom XML templates (`role.md`, `rules.md`, `task.md`) existed as named abstractions but had no runtime consumer.

The assembly mechanism has to satisfy several constraints simultaneously: ordering must be explicit and reviewable; family-level methodology must be reusable across members without forcing every member into one template; local content (this prompt's specific objective, output format) must remain authored per prompt; bridging text between sections must be authorable in the assembly file itself, not invented at runtime.

## Decision

Every prompt owns a top-level **shell** — a Jinja2 template that is the authoritative assembly document for that prompt. The shell determines final ordering, local bridging text between sections, and prompt-level coherence. Shared text is introduced through `{% include %}` directives that reference family-level **methodology bundles**.

Methodology bundles are themselves Jinja2 templates that accept per-prompt content through template variables. A bundle captures a shared structural pattern (e.g. the audit methodology: finding budget, severity model, evidence standard) while letting each prompt supply domain-specific content (the concrete finding categories, the verdict classifications).

The starting set of bundles is small and concrete:

- `quality-methodology.md.j2` — shared audit methodology structure. Per-prompt variables supply domain-specific finding kinds.
- `report-contract.md.j2` — shared report structure (verdict, executive findings, detailed findings). Per-prompt variables supply verdict classifications and finding template fields.

The composition flow is deterministic:

```text
Load PromptDefinition
→ Load per-prompt methodology variables (methodology.yaml)
→ Resolve shell and family bundles
→ Select local variants by regime
→ Render composed prompt (bundles receive methodology variables)
→ Validate hard profile requirements
→ Emit advisory warnings and length report
→ Write golden output
```

The output is one composed prompt file per prompt definition, committed as a golden file. Review is the diff over the composed output, not over the fragments.

## Discarded alternatives

- **Naive Markdown concatenation** (the legacy `generate.py`). Rejected because ordering, transitions, and section interaction cannot be expressed; the build cannot distinguish a coherent prompt from an arbitrary Markdown join.
- **Inheritance-style templating** (one base template per family; members override blocks). Rejected because the shell's job is *per-prompt* ordering and transitions; expressing those as block overrides on a base template inverts the design surface (the prompt becomes a diff against an invisible parent).
- **Micro-block registry** (small reusable fragments stored centrally, referenced by ID from shells). Rejected: text-that-changes-together should live together; a micro-registry inflates coordination cost without matching observed maintenance patterns. See [generalization-by-demonstrated-pressure](generalization-by-demonstrated-pressure.md).
- **A non-Jinja templating engine** (custom DSL, Markdown-with-extensions). Rejected because Jinja2 is mature, well-known, supports `{% include %}` and per-template variables natively, and integrates with Python's tooling. A custom DSL would be the wrong place to invest.
- **Inline methodology in every prompt** (no bundles; each prompt carries its own copy of the audit methodology). Rejected because the family-level methodology change pattern is the strongest observed reuse signal; copies would diverge.

## Rationale

The shell is what the author actually designs: the ordering and the transitions are properties of the assembly, not of the fragments. Methodology bundles capture the coarsest reuse layer that the observed maintenance pattern justifies; smaller reuse units stay inline until evidence promotes them. Jinja2 is the right tool because the requirements are exactly templating with includes and variables — no novel mechanism needed.

## Consequences

- A new prompt family is one shell template plus a `profile.yaml` plus zero or more family-level bundle templates.
- Adding a new prompt to an existing family is one shell template plus per-prompt methodology variables.
- The composition stage is a small, dependency-light Python module built on Jinja2.
- The composed prompt file is the unit of diff review and the unit of empirical testing.
- Hard validation of the composed prompt is the third tier of the quality model ([family-profile-validation-model](family-profile-validation-model.md)); the shell is not validated against the agent's behavioural response.
