# Proposal — Eutaxis Prompt Composition Framework

## Executive Summary

Eutaxis is a domain-agnostic prompt composition framework. It provides the
tooling and method for authoring, composing, validating, and revising
structured AI agent prompts. It does not own domain-specific quality criteria;
those live in the projects whose domains they govern:

- **vitruv** owns software architecture standards and audit prompts.
- **hermeneia** owns writing quality standards and prose audit prompts.
- **gnomon** owns mathematical research note workflow and governance.

Eutaxis provides the composition infrastructure that these projects consume:
prompt shells, parameterized methodology bundles, family profiles, and an
author-compose-review-test workflow.

The immediate problem this proposal addresses:

- Prompt authoring has no structured workflow: there is no
  author → compose → review → test loop, no composed-prompt design surface,
  no validation, and no golden-file review.
- The prompt-writing methodology exists as prose (`docs/prompt-writing-methods.md`)
  but is not embodied in the authoring workflow — the strongest prompt-design
  rules remain advisory.
- `generate.py` is a naive concatenator with no structural awareness.
- The current XML templates are phantom abstractions with no consumer.

This proposal introduces:

1. **Prompt family as the primary organizing concept.**
   The first-class unit is a prompt family (e.g., vitruv's `architecture/auditor`
   or hermeneia's `documentation/auditor`), not an abstract task taxonomy.
2. **The composed prompt as the primary design artifact.**
   Each prompt owns an explicit top-level shell that determines final ordering,
   local bridging text, and prompt-level coherence.
3. **Reuse at semantically stable units.**
   Shared text starts as coarse parameterized methodology bundles, not a
   registry of micro-blocks.
4. **Hard validation limited to real invariants.**
   Family profiles enforce only what must hold for a prompt to be structurally
   meaningful. Richer structural guidance is advisory.
5. **Generality deferred until demonstrated.**
   Broader abstractions become justified only when actual cross-family
   maintenance pressure appears.

---

## Part I — Problem Statement

### What is broken now

| Problem | Evidence | Consequence |
| --- | --- | --- |
| Prompt iteration lacks a workflow | No author → compose → review → test loop; the composed prompt is not a first-class design surface | Prompt quality depends entirely on monolithic editing without validation or golden-file review |
| Methodology not operationalized | `docs/prompt-writing-methods.md` defines sectioning, token economy, and reasoning-regime concerns, but tooling does not embody them | The strongest prompt design rules remain advisory prose |
| No prompt-aware composer | `generate.py` concatenates sources without prompt structure, section awareness, or validation | The build cannot distinguish a coherent prompt from an arbitrary Markdown join |
| Phantom templates | `role.md`, `rules.md`, and `task.md` exist as abstractions with no runtime consumer | The data layer contains named concepts that do not govern system behavior |

### Scope

This proposal solves the prompt-composition problem for eutaxis as a
framework provider. Domain-specific prompt families are authored and
maintained in their respective projects (vitruv, hermeneia) using eutaxis
tooling.

---

## Part II — Design Principles

1. **Prompt family first.** Begin from prompt families that actually exist,
   not from a forecast taxonomy of agent postures.
2. **Composed prompt first.** The final prompt is the primary object of design
   review, empirical testing, and quality judgment.
3. **Reuse at the largest stable semantic unit.** When text changes together,
   it should live together.
4. **Hard validation only for true invariants.** If violating a rule makes
   the prompt structurally meaningless, validate as an error. Otherwise, emit
   a warning.
5. **Behavioral evidence outranks structural elegance.** If testing shows that
   a family works better with a different structure, the architecture must
   adapt.
6. **Generalization requires demonstrated pressure.** A second prompt family,
   repeated cross-family reuse, or duplicated prompt-check rules are evidence.
   Abstract symmetry is not.

---

## Part III — Architecture

### A. Core Domain Model

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PromptFamily:
    domain: str                 # "architecture", "documentation"
    name: str                   # "auditor"
    profile_path: str           # path to profile.yaml
    bundle_dir: str             # shared family bundles


@dataclass(frozen=True)
class PromptDefinition:
    family: str                 # "auditor"
    name: str                   # "component"
    shell_path: str             # prompt.md.j2
    methodology_path: str | None = None
    regime: str = "standard"
    output_path: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptProfile:
    name: str
    required_files: tuple[str, ...]
    required_tags: tuple[str, ...]
    recommended_regions: tuple[str, ...] = ()
    warning_token_limit: int | None = None
    coordination_notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompositionResult:
    prompt_text: str
    diagnostics: tuple[str, ...]
    word_count: int
    token_estimate: int
```

### B. Prompt Shells

Every prompt owns a top-level shell — the authoritative assembly document.

```markdown
# SYSTEM PROMPT - ADVERSARIAL COMPONENT AUDITOR

{% include "role.md" %}

---

## Methodology

{% include "_bundles/quality-methodology.md.j2" %}
{% include variant("method", regime) %}

---

## Output Format

{% include "_bundles/report-contract.md.j2" %}
{% include "output.md" %}
```

The shell owns final ordering, local transitions, and prompt-level coherence.
Shared text exists to support the shell, not to replace it as the design
surface.

### C. Prompt Profiles

Each family has a `profile.yaml` with hard requirements and advisory guidance:

```yaml
name: auditor

hard_requirements:
  required_files:
    - prompt.md.j2
    - role.md
    - objective.md
    - output.md
  required_tags:
    - role
    - task

advisory_guidance:
  recommended_regions:
    - role
    - objective
    - scope
    - methodology
    - output
  token_warning_limit: 4000

family_coordination:
  notes:
    - "Scope is partitioned across members: component examines nodes,
      interaction examines edges, model examines concepts."
```

### D. Parameterized Methodology Bundles

Bundles are Jinja2 templates that accept per-prompt content through template
variables. They capture shared structural patterns while allowing
domain-specific specialization.

Starting bundles:

1. `quality-methodology.md.j2` — shared audit methodology structure (finding
   budget, systemic claim standard, severity model, evidence standard). Each
   prompt provides domain-specific content through template variables.
2. `report-contract.md.j2` — shared report structure (verdict, executive
   findings, detailed findings). Each prompt provides its verdict
   classifications and finding template fields.

### E. Composition Flow

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

### F. Quality Model

**Tier 1 — Assembly integrity** (automatically enforced): shell exists,
includes resolve, required files present, prompt renders into one output,
length reported.

**Tier 2 — Authoring quality** (rule-validated): prompt prose rules,
section-shape checks, family-specific style rules.

**Tier 3 — Behavioral effectiveness** (empirically verified): golden prompt
review, targeted prompt tests, iteration on the shell.

---

## Part IV — Staged Delivery

### Phase 1 — Framework and first consumer

Deliver:

- Prompt composition commands (`eutaxis generate`, `eutaxis validate`)
- Family profile infrastructure (hard requirements + advisory guidance)
- Parameterized bundle rendering (Jinja2)
- Golden-file output and review workflow
- Length reporting and assembly validation

Phase 1 does **not** include: task-type taxonomy, universal section taxonomy,
domain manifests, cross-domain enforcement, block registries.

### Phase 1 monitoring signals

Within Phase 1, consider promoting a concept early if:

1. A standard change requires coordinated updates across more than two prompts
   and the `sources:` list proves insufficient.
2. A bundle's parameterized slots diverge enough that the template no longer
   captures a coherent shared structure.
3. A new family member creates scope-coordination pressure that the current
   profile model cannot express.

### Phase 2 — Cross-family generalization

Phase 2 begins when at least two maintained prompt families exist across
domain-specific projects. Then evaluate whether the following are justified:

- Cross-family shared bundles
- Family registries
- Richer source-mapping metadata
- Generalized prompt-family style-check infrastructure

---

## Part V — Authoring Workflow

1. **Edit the shell first** when the problem is ordering, emphasis, or section
   interaction.
2. **Edit local fragments** when the problem is prompt-specific content.
3. **Edit a family bundle** only when the same change genuinely belongs across
   the whole family.
4. **Compose the prompt** and inspect the full output.
5. **Review the golden diff** as a prompt, not as file fragments.
6. **Test behavior** with representative inputs.
7. **Update the family profile** if the family has learned a better default.

### Rule for moving text

- One prompt needs it → keep it local.
- All prompts in a family need it and it changes together → family bundle.
- Multiple families need it with stable meaning → cross-family abstraction
  (Phase 2).

---

## Part VI — Deliberate Non-Decisions

These are intentionally postponed:

- Whether task posture deserves a global type
- Whether standards need first-class reference tracking
- Whether domains need manifests
- Whether prompt sections need a universal taxonomy
- Whether prompt prose checks should be fully decomposed now

Postponing these is alignment with the core principle: abstractions should
follow demonstrated maintenance pressure, not forecast it.
