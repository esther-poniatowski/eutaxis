---
tags: []
aliases:
  - Rule-template format and field vocabulary
index: "[Open architectural questions](_index.md)"
---

# Rule-template format and field vocabulary

**Severity.** High. **Phase-blocking.** Phase 1 (rule-template migration). **Origin.** Refinement of session proposal 2, recorded in [rule-sources-as-structured-templates](../adr/rule-sources-as-structured-templates.md).

## Question

[rule-sources-as-structured-templates](../adr/rule-sources-as-structured-templates.md) commits to structured, schema-validated rule sources but defers two concrete choices:

1. **Surface syntax** — which configuration format the source file uses on disk.
2. **Field vocabulary** — the exhaustive list of fields a rule may declare, with mandatory / optional status and declared types.

The first choice shapes authoring ergonomics, validation tooling, and rendering. The second shapes what a rule can express and what the renderer can rely on.

### Surface syntax

The decision requires a format that satisfies four properties:

- **Typed fields** with explicit names — the schema is the source of truth, not document conventions.
- **Mandatory / optional declarations** — a load-time validator refuses files that omit required fields.
- **Cleanly delimited multi-line blocks** — prescription text, example code, rationale prose are all multi-line; the format must preserve newlines and inner whitespace without escape noise.
- **Mature ecosystem** — parser, validator, editor support available on the platforms the project uses.

Candidate formats:

| Format | Multi-line shape | Typed fields | Schema validators | Notes |
| --- | --- | --- | --- | --- |
| **Markdown-comment-tagged hybrid** (YAML frontmatter + per-declaration fenced YAML payload + HTML-comment-tagged Markdown content blocks) | Native Markdown inside each `<!--rule:field-->...<!--rule:/field-->` block; per-block JSON metadata inside the opening tag | Yes — typed metadata in YAML; field discrimination by tag name | JSON Schema on YAML layers; custom parser on tag structure | Prior art: gnomon's [data-formats](file:///Users/eresther/Documents/work/research/geonexus/vendor/gnomon/docs/design/2-architecture/data-formats.md). Separates typed metadata from expressive prose at the syntax level |
| **YAML with literal block scalars (`\|`, `>`)** | Block scalar preserves newlines, indentation, and inner formatting | Yes | JSON Schema via `ajv`, `jsonschema`, `pydantic` | Already the Agent Skills frontmatter format; ubiquitous tooling. Prose-rich content competes with YAML's outer indentation |
| **TOML with triple-quoted multi-line strings** | Triple-quoted preserves newlines; whitespace inside is literal | Yes | JSON Schema via `taplo`, `pydantic-settings` | Already the Codex `config.toml` format; lighter ecosystem for nested schemas |
| **JSON / JSON5 / JSONC** | None native; JSON5/JSONC add comments and trailing commas but still escape newlines | Yes | JSON Schema | Hostile to prose authoring even with JSON5 extensions |
| **HCL with heredocs** | Heredoc preserves newlines | Yes | HCL-native | Niche outside infrastructure tooling |
| **Custom DSL** | Designable | Designable | Custom | Tooling cost prohibitive |

The **Markdown-comment-tagged hybrid** is the leaning resolution after a precedent in the gnomon project (`docs/design/2-architecture/data-formats.md`), which faced the same tension between typed structured fields and flexible prose-rich content and resolved it as follows: separate the *machine-typed metadata layer* (YAML frontmatter at the file level, plus a fenced YAML block at the start of each declaration carrying the typed fields) from the *expressive-prose layer* (Markdown content delimited by HTML-comment tags whose names identify the field). HTML comments are syntactically invisible in any standard Markdown renderer but uniquely addressable by a parser; per-block metadata travels as JSON inside the opening tag.

This candidate requires the accepted ADR to be read narrowly: [rule-sources-as-structured-templates](../adr/rule-sources-as-structured-templates.md) rejects an untyped frontmatter-plus-convention-body hybrid, not a typed tag-delimited hybrid whose content blocks are schema-addressable fields.

Mapped to rule templates:

```markdown
---
role: rule-set
namespace: conceptual-reasoning
exports:
  - motivation-first
  - no-forward-references
---

<!--rule:decl-->
\`\`\`yaml
id: motivation-first
name: "Motivation first"
description: "Every concept is motivated before introduction."
axis: output-structure
failure-mode: visible
applies-when: "generative or expository content"
related: [no-forward-references, cognitive-load]
\`\`\`

<!--rule:prescription-->
Motivate every concept, construct or technical tool **before**
introducing it. Identify the motivating problem before proposing
a structure.
<!--rule:/prescription-->

<!--rule:prohibition-->
Never introduce formulas abruptly before explaining their purpose.
<!--rule:/prohibition-->

<!--rule:example-valid {"context":"mathematical-exposition"}-->
Before introducing $L(\theta) = \sum_i (y_i - f(x_i))^2$, state:
"We need a measure of fit that penalises large residuals more
than small ones."
<!--rule:/example-valid-->

<!--rule:example-invalid {"context":"mathematical-exposition"}-->
Section opens with: "The loss is $L(\theta) = \sum_i (y_i -
f(x_i))^2$." No motivation.
<!--rule:/example-invalid-->

<!--rule:rationale-->
Reduces cognitive load and prevents the reader from holding
undefined objects in working memory.
<!--rule:/rationale-->
<!--rule:/decl-->
```

The hybrid delivers four properties more naturally than the pure-YAML candidate:

- **Typed metadata and expressive prose are syntactically separate.** Typed fields live in YAML and are validated by JSON Schema. Prose-rich content lives in Markdown content blocks with no escaping pressure — multi-paragraph rationale, fenced code, math, and lists all author as ordinary Markdown.
- **Per-block metadata is first-class.** Example blocks declare their context, language tag, expected behaviour, or any other rendering hint inside the opening tag without forcing each example into a structured object inside YAML.
- **The source is parser-addressable and rendered-output-invisible.** HTML comments have no visual effect in a Markdown renderer, while remaining uniquely addressable in raw source. Because an agent that reads raw Markdown can still see comment tags, the source file must not be treated as a runtime artifact.
- **Failure modes are well-defined.** The gnomon prior art specifies the parser's responsibilities (reject unclosed tags, reject overlapping blocks, reject malformed JSON attributes), which is the validation surface that JSON-Schema-on-YAML alone cannot provide.

The remaining trade-offs:

- **Validation is two-layered.** JSON Schema validates the YAML portions; a custom parser validates the tag structure. Both are needed, but each remains narrow. The parser should reuse the failure modes documented by gnomon.
- **The format is non-obvious.** Anyone unfamiliar with the
  `<!--rule:...-->` convention needs documentation. A
  `docs/rule-template-syntax.md` is the deliverable here.
- **Compilation step is mandatory.** The source is never read directly by an agent at runtime; the renderer always intervenes. This aligns with [compiler-not-runtime-activation](../adr/compiler-not-runtime-activation.md) but is a stronger commitment than the YAML-only candidate carried.

A reason to fall back to YAML-with-literal-block-scalars: if the parser cost is judged not worth paying for the prose-rich expressivity gain, the pure-YAML candidate remains viable. Its defect (prose competing with YAML structure inside the file) is documented in gnomon's rejected-formats section under `t2-reject-yaml-only` and is the principal reason the hybrid is leading.

A reason to fall back to TOML: if rule-template sources ever need to be consumed directly by Codex without a compilation step, TOML is the native Codex format. Today the compilation step is assumed, so this is not load-bearing.

### Field vocabulary

The session surfaced a minimum field set covering: prescription, prohibition, valid examples, invalid examples, operational check, rationale. The exhaustive vocabulary is not yet committed.

Candidate fields, grouped by purpose:

**Identity and addressing** (all mandatory):

- `id` — stable identifier for cross-rule references and composition (subject to [identifier-and-namespace-algebra](identifier-and-namespace-algebra.md)).
- `name` — short human label for listings and pickers.
- `description` — one-line summary, used in listings and the silent-failure classification flow.

**Classification metadata** (mandatory where applicable):

- `axis` — `reasoning-target` / `output-structure` / `surface-style` / `procedure`, per [four-axis-instruction-decomposition](../adr/four-axis-instruction-decomposition.md).
- `failure-mode` — `silent` / `visible`, per [silent-failure-classification](silent-failure-classification.md). Default `silent` if omitted.
- `required-visibility` — `pre-invocation` / `pre-action` for `failure-mode: silent` rules. `pre-invocation` keeps the rule in the always-on body; `pre-action` can travel with a user-invoked procedure when the procedure loads before any irreversible action.
- `applies-when` — predicate clause for conditional rules in the always-on regime, per [silent-failure-rules-as-always-on](../adr/silent-failure-rules-as-always-on.md).
- `scope` — list of rule-sets or skills the rule belongs to.

**Rule content** (mandatory unless noted):

- `prescription` — the ✓ block; multi-line Markdown content block.
- `prohibition` — the ✗ block; multi-line Markdown content block. Optional only if the rule is purely prescriptive.
- `rationale` — the **Why** block; optional but recommended.
- `operational-check` — a falsifiable test the renderer or reviewer can apply to detect a violation; optional.
- `example-valid` — repeated content block illustrating compliant behaviour. Each instance carries its own JSON metadata (`context`, `language`, `expected-behavior`) inside the opening tag.
- `example-invalid` — repeated content block illustrating violations, same metadata shape as `example-valid`.

For the reasoning-target axis specifically, the canonical sub-shapes documented in [instruction-axes](../prompt-writing-methods/instruction-axes.md) (success criteria, subproblems, assumptions and edge cases, verification conditions, output contract) map onto the `prescription` / `operational-check` pairing. The schema does not add per-sub-shape fields; the within-rule discipline lives in the prose, not in the metadata.

**Cross-references** (optional):

- `related` — list of `id`s pointing to other rules that interact with this one.
- `superseded-by` — list of `id`s for rules that replace this one during deprecation.

One sub-question to settle before landing:

- **Adapter-specific overrides.** Whether a rule can declare `adapters.<name>.{prescription, examples, ...}` overrides analogous to the commands schema in [adapter-passthrough-source-schema](../adr/adapter-passthrough-source-schema.md), so a rule can be phrased differently for Claude and Codex when the rendered form must diverge. The leaning is no overrides in the first iteration; phrasing divergence is the renderer's responsibility, kept in per-adapter rendering code. The override slot can be added later if the renderer hits a case it cannot handle.

The earlier "example structure" sub-question is resolved by the hybrid format: examples are content blocks whose metadata travels in the opening tag's JSON payload. Bare-string vs structured-object is no longer the trade-off — both shapes coexist naturally.

## Current state

- No schema file exists in the eutaxis tree today; rule sources are free-form Markdown.
- JSON Schema is already used implicitly by the Agent Skills standard for `SKILL.md` frontmatter; reusing that infrastructure is the lowest-cost path.
- The legacy oikos `generate` pipeline does not parse rule internals — it concatenates files verbatim into the always-on artifact.

## Architectural components that depend on this

- The Phase 1 always-on regime adapter for both target agents.
- The on-demand skill adapter when it consumes rule sources (rather than command sources).
- The migration plan from the current oikos `instructions/tasks/` files to structured templates.
- The compositional-skill work tracked under proposal 3 — its selection algebra references rule `id`s declared by this schema.

## Candidate resolution

The composite leaning resolution:

- **Surface syntax: Markdown-comment-tagged hybrid** (YAML frontmatter + per-declaration fenced YAML payload + HTML-comment-tagged Markdown content blocks), validated by JSON Schema on the YAML layers plus a custom parser on the tag structure. Prior art: gnomon `docs/design/2-architecture/data-formats.md`.
- **Vocabulary: the field set above**, with `prescription`, `id`, `name`, `description`, `axis`, `failure-mode` mandatory, `required-visibility` mandatory for `failure-mode: silent`, and the rest optional.
- **Examples as content blocks** with JSON metadata in the opening tag (`context`, `language`, `expected-behavior` optional), preserving richer downstream rendering without forcing structured-object authoring inside YAML.
- **No adapter-specific source overrides** in the first iteration; phrasing divergence is the renderer's job, kept in per-adapter rendering code. The override slot can be added later if the renderer hits a case it cannot handle.

The candidate is leaning, not decided. The format choice in particular should be checked against the first non-trivial migration: a rule with many examples, a rule with cross-references, a rule with conditional applicability, and a rule whose prescription is a multi-paragraph reasoning-target specification all need to round-trip cleanly before the format is committed. The round trip must also confirm that the hybrid satisfies the accepted ADR's schema-validation requirement rather than recreating convention-shaped Markdown under a new delimiter syntax. The parser implementation cost (the primary objection to the hybrid over pure YAML) should also be empirically checked against the gnomon implementation as a reference.

## Decision required before

The first migration pass from the current oikos `instructions/tasks/` files to structured templates. The schema and the format both become load-bearing at that point; later changes require migrating every authored rule.
