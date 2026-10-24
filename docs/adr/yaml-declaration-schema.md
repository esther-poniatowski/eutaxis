---
tags: []
aliases:
  - YAML declaration schema
index: "[Architecture decisions](_index.md)"
---

# YAML declaration schema

## Status

Accepted. The source boundary implements declaration schema version 1. The [normative field contract](../../src/eutaxis/data/schemas/declaration-v1.schema.json) governs its models and fixtures. The next slice adds the checks that require registries.

## Purpose

The schema must let authors state rules and procedures once, validate their semantics before rendering, and retrieve only the declarations required for a task. The source form must preserve rich prose, type every operative relation, and remain readable without a custom editor.

## Canonical form and authority

Pure YAML is the canonical authoring format. Markdown remains available inside YAML block scalars. A tagged-Markdown hybrid is the fallback only if a representative YAML pilot demonstrates a material authoring or round-trip defect.

One versioned JSON Schema is the normative field, type, cardinality, conditional-requirement, and default contract. Python models are generated from that schema where the toolchain preserves its semantics; otherwise, the models must pass the same valid and invalid fixture corpus and may not introduce independent defaults. This ADR fixes the architecture and required semantics, but it is not an exhaustive substitute for that schema.

## Declaration kinds

The discriminated union contains seven kinds:

- `rule-set` groups coherent rules and supplies one discovery purpose
- `rule` declares one addressable artifact or decision constraint
- `procedure` declares a finite externally observable action graph
- `resolution-policy` resolves a named class of semantic conflicts inside one compilation unit
- `composition-manifest` selects declarations and orders the sections of one native-scope artifact
- `evaluator` declares how a criterion is assessed and what its evidence means
- `operation` declares an action node available to procedures

Only rules carry an `axis`: `reasoning-target`, `output-structure`, or `surface-style`. Procedures are a declaration kind, not a fourth axis. A file may contain one declaration or a declared collection; member objects retain their own `kind` and stable identifier.

## Common envelope

Every declaration has `schema-version`, stable `id`, `kind`, `owner`, lifecycle status, source revision, applicability, and relations. Classification, failure mode, visibility, rationale, title, and purpose appear only where the normative schema admits them. A required per-rule `description` is excluded because it normally paraphrases the norm. A rule set or procedure may carry one `purpose` for discovery.

At this boundary, each identifier contains one or more non-whitespace characters. The schema leaves separators uninterpreted because the namespace across repositories remains undecided. A versioned evaluator or operation reference uses separate `id` and positive-integer `version` fields. Therefore, future namespace syntax cannot change how a reference is parsed.

Applicability is conjunctive across nesting. The normalized version 1 language contains `all`, `any`, and `not` nodes plus typed atomic tests with operators `equals`, `in`, and `exists`. Atomic tests name registered context facets. A missing facet makes `equals` and `in` return `unknown`; `exists` always returns true or false.

The boolean nodes use strong Kleene truth tables. `all` returns false if any child is false, true if every child is true, and unknown otherwise. `any` returns true if any child is true, false if every child is false, and unknown otherwise. `not` preserves unknown and reverses true or false. A final unknown is a resolution error. Therefore, `all: [exists(f), equals(f, x)]` returns false when `f` is missing, while an unguarded `equals(f, x)` fails instead of silently omitting the declaration.

A child does not replace its inherited predicate. The loader constructs `all: [<parent>, <child-local>]`, and a norm narrows a rule through the same structural conjunction. This construction proves narrowing without a general implication solver. The resolver reports the expanded normalized predicate and each atomic result. Resolution policies use explicit order rather than an inferred predicate-specificity relation.

## Rules and criteria

Rules express modality as data. The values follow [BCP 14](https://www.rfc-editor.org/info/bcp14): `must`, `must-not`, `should`, `should-not`, and `may`. Each norm has a local stable `id`, `modality`, `subject`, an action with `verb`, `object`, and optional `timing`, and optional narrowing applicability, Markdown guidance, and rationale.

`should` and `should-not` require a decision criterion that evaluates the norm or inclusion in the `affects` set of a closed exception. An exception names the local norms affected, its applicability predicate, and either a waiver or replacement norms. Version 1 admits at most one exception for each affected norm and only one-step substitutions: a replacement norm cannot itself be affected by an exception. This direction excludes waivers of the enclosing rule and unrelated declarations. `may` is admitted only for a genuinely discretionary choice. Prohibitions are `must-not` norms, not a parallel prose field. Each success criterion names the norm identifiers that it evaluates and one registered evaluator.

The following rule set demonstrates the common envelope, inherited applicability, modal norms, and a structured evaluator reference:

```yaml
schema-version: 1
id: prose/reasoning-over-mechanics
kind: rule-set
owner: oikos
status: active
source-revision: example-1
applicability:
  facet: artifact.is-created-or-revised
  operator: equals
  value: true
relations: []
purpose: >-
  Directs agent attention to judgments that mechanical tools cannot make
rules:
  - id: allocate-deliberation
    schema-version: 1
    kind: rule
    owner: oikos
    status: active
    source-revision: example-1
    axis: reasoning-target
    failure-mode: visible
    relations: []
    applicability:
      facet: task.kind
      operator: equals
      value: writing
    norms:
      - id: reason-beyond-tools
        modality: must
        subject: agent
        action:
          verb: allocate-attention
          object: deliberative criteria not decided by registered checkers
      - id: no-checker-substitution
        modality: must-not
        subject: agent
        action:
          verb: treat
          object: a clean checker result as proof of semantic adequacy
    criteria:
      - id: purpose-read
        norms: [reason-beyond-tools, no-checker-substitution]
        evaluator: {id: eutaxis/manual-judgment, version: 1}
        statement: >-
          The artifact has been read against its reader-facing purpose
```

## Evaluator and operation registries

An `evaluator` records its identity, assessment authority, timing, accepted inputs, evidence contract, failure behavior, and known-failure fixtures. Version 1 admits three exact enforcement contracts: `checker` with total coverage and authoritative adjudication, `detector` with partial coverage and candidate adjudication, and `manual` with no mechanical coverage and manual adjudication. Each checker names at least one known-failure fixture. The next slice registers version 1 of the evaluator `eutaxis/manual-judgment`. Its evidence names the reviewer, criterion, observation, and conclusion. The value `manual` is therefore not an unregistered escape value.

An `operation` records `id`, `owner`, semantic version, typed inputs and outputs, preconditions, allowed and forbidden effects, failure outcomes, and recovery contract. Procedures reference operations by identifier. The registry supplies their effect summaries for static comparison with procedure invariants; declarations do not embed arbitrary executable shell commands.

## Procedure contracts

A procedure formalizes `{P} A {Q}` without pretending that every predicate is decidable. Its contract contains typed parameters, typed predicates, a finite acyclic action graph, declared effects, and terminal states. Every node references a registered operation. Each outcome names exactly one successor. Conditional branching uses a registered guard operation whose success and failure outcomes name the two branches. Version 1 admits no unbounded loop. Every path must reach a declared postcondition or failure state, so termination is structurally decidable.

Procedure predicates reuse the bounded, side-effect-free boolean grammar after typed `before`, `after`, `request`, and `observations` facets are registered. A judgment predicate references the manual evaluator rather than encoding a false mechanical test.

## Validation

The source boundary rejects a source when:

- YAML repeats a key, contains a cyclic alias, or produces a non-JSON value
- a field violates the normative schema or embeds an invalid JSON Schema
- local identifiers repeat or a local reference does not resolve
- exception interactions, policy strategies, or effects contradict their surrounding declaration
- a procedure graph omits a transition, contains a cycle, or leaves an action unreachable

Diagnostics name the document path and closest YAML source position. The loader conjoins each child applicability predicate with its inherited parent predicate. The immutable domain model preserves every normative field.

The registry slice will reject unregistered context facets, evaluators, and operations. The same slice will compare operation effects with procedure invariants, resolve external references, and reject policy-order ties. Next, the catalog and resolver will decide final `unknown` applicability results and cross-declaration conflicts. These later checks are not attributed to the source boundary before their registries exist.

## Runtime boundary

Canonical YAML is build input and is never itself injected into an agent session. A catalog query produces a generated, provenance-bearing packet containing only the material needed by its caller. The packet may serialize as YAML or JSON. A diagnostic command may generate the packet during a task, but the packet remains adapter output.

Current hosts still require rendered Markdown for cumulative `AGENTS.md` and `CLAUDE.md` files and compact `SKILL.md` entrypoints. When a deployed Skill cannot access the catalog, the Skill must bundle its rendered fallback. Therefore, adapters render Markdown only as a compatibility projection.

## Consequences

The first implementation publishes the complete source boundary and its fixture corpus. The next work registers evaluators and operations and completes their fixtures before catalog construction. External sources cannot adopt the schema until the full normative-contract gate passes.
