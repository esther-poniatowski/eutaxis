---
tags: []
aliases:
  - YAML declaration schema
index: "[Architecture decisions](_index.md)"
---

# YAML declaration schema

## Status

Accepted. The [normative field contract](../../src/eutaxis/data/schemas/declaration-v1.schema.json) governs the models and fixtures for declaration schema version 1. The source boundary implements this contract. Eutaxis adds each registry check through a bounded gate. Eutaxis will construct catalogs after those gates pass.

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

## Context-facet registry

One explicitly supplied YAML registry defines the context vocabulary for a typed load. The registry remains separate from the seven-kind declaration union. The registry owns all facet entries and records their owner and source revision:

```yaml
schema-version: 1
id: eutaxis/context-facets
owner: eutaxis
source-revision: v1
facets:
  - id: task.kind
    value-schema:
      type: string
      enum: [writing, programming]
```

Each facet entry contains only an `id` and a `value-schema`. The registry supplies the owner and source revision once.

A facet value schema follows the [shared embedded-schema contract](#^embedded-schema-contract).

The typed declaration route checks every applicability predicate while the YAML source map remains available. The route covers:

- common predicates and predicates on member rules
- predicates that narrow norms or activate exceptions
- procedure and operation predicates
- policy predicates

An unknown facet fails even inside an untested branch. By contrast, the local loader checks only the source schema and intrinsic semantics. The local loader does not claim that the registry accepts the declaration.

The registry checks every supplied runtime context key and value before it evaluates a predicate. Unknown keys and values outside the registered schema fail rather than returning false. Missing keys remain valid input to the strong Kleene logic.

Each operator acts uniformly across the JSON domain:

- `exists` tests whether the key is present, including when its value is null
- `equals` compares the context value with one registered value
- `in` compares the context value with one or more alternatives; for an array-valued facet, each alternative is an array

The following work remains outside schema version 1:

- merging facet registries
- defining aliases or defaults
- coercing values
- deriving facets

A later layer may combine registries only after it specifies how registries cross owner boundaries. The same layer must specify how namespaces compose.

## Embedded-schema contract ^embedded-schema-contract

Self-contained Draft 2020-12 schemas govern five fields:

- facet values
- procedure parameters
- evaluator evidence
- operation inputs
- operation outputs

The static scan examines the root schema and every subschema. This coverage includes schemas under inactive `$defs` and conditional branches. The scan admits local JSON Pointers but rejects:

- a separate `$id`
- a dialect other than Draft 2020-12
- external `$ref` values
- `$dynamicRef` and `$recursiveRef`
- local `$ref` values that do not resolve within the root schema

Cycle analysis follows Draft 2020-12 evaluation paths and is narrower than the static scan:

- rejects every reachable reference cycle
- enters a schema under `$defs` only when an evaluation path refers to that schema
- treats `then` and `else` as unreachable without a sibling `if`

The cycle checker admits a cycle that no evaluation path reaches. Separately, the validator records the `format` keyword without asserting a constraint.

Together, these rules let every schema run offline against its complete root resource.

Exact JSON values compare under four rules:

- objects compare independently of key order
- arrays compare item by item in order
- a boolean and a number do not compare equal
- finite integers and finite floating-point numbers compare numerically

The applicability operators and declaration registry both use these rules. Separately, the registry compares schema forms exactly. The registry does not determine whether two schemas accept the same values. The registry does not classify one schema as a subtype of another.

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

An `evaluator` names who assesses a criterion. The evaluator declares when it runs. The contract specifies accepted inputs and produced evidence. The contract also specifies failures. A checker names its known-failure fixtures. Version 1 admits three exact enforcement contracts:

- `checker` covers every admitted input and decides the result authoritatively
- `detector` covers only some admitted inputs and proposes candidate results
- `manual` asks a human reviewer to decide

Each checker names at least one known-failure fixture. During the final registry slice, Eutaxis will register version 1 of `eutaxis/manual-judgment`. Its evidence identifies the reviewer and criterion, then records the observation and conclusion. Therefore, `manual` is not an unregistered escape value.

An `operation` declares a versioned action contract. The contract defines:

- typed inputs and outputs
- preconditions
- the closed set of state identifiers that may change on any outcome
- named failure outcomes and a recovery contract

Procedures select these contracts by identifier. Declarations exclude arbitrary executable shell commands.

## Procedure contracts

A procedure formalizes `{P} A {Q}` without treating every predicate as decidable. Its contract defines:

- typed parameters and predicates
- a finite acyclic action graph
- an authorized mutation footprint
- postcondition and failure terminals

Each action node names a registered operation. The `on-success` field names its successor. The `on-failure` map names one successor for each failure outcome. A registered guard operation supplies the outcomes used for conditional branches.

To ensure termination, schema version 1 admits no unbounded loop. Every path must reach a declared terminal.

Schema version 1 restricts operation inputs and procedure parameters to closed object schemas. Each schema declares its `properties`. The schema rejects additional properties and requires only declared properties. Property names and action input keys use the identifier syntax of the declaration schema. Each binding selects a parameter or literal variant. The immutable domain model represents these variants with separate types.

The declaration registry requires each binding to satisfy four conditions:

- every required input is bound
- no unknown input is bound
- every literal satisfies its input schema
- every parameter schema has the same normalized form as its input schema

Each invariant declares its observed state identifiers. The registry rejects an action when its operation may mutate one of these states. The registry also requires the operation footprint to fit within the procedure's authorized footprint. These conservative checks cover every declared outcome.

Procedure predicates reuse the bounded, side-effect-free boolean grammar after typed `before`, `after`, `request`, and `observations` facets are registered. A judgment predicate references the manual evaluator rather than encoding a false mechanical test.

## Validation

The source boundary rejects a source when:

- YAML repeats a key, contains a cyclic alias, or produces a non-JSON value
- a field violates the normative schema or embeds an invalid JSON Schema
- local identifiers repeat or a local reference does not resolve
- two exceptions contradict each other, or a policy strategy contradicts its declaration
- a procedure graph omits a transition, contains a cycle, or leaves an action unreachable
- a closed object schema requires an undeclared property, or an action binds an undeclared procedure parameter

The facet-registry boundary rejects duplicate identifiers and values outside the JSON domain. The same boundary rejects malformed value schemas and schemas that resolve content externally. The typed route rejects unregistered facet names and invalid comparison constants. Before evaluating a predicate, the runtime rejects unknown context keys and invalid present values.

Diagnostics name the document path and closest YAML source position. The loader conjoins each child applicability predicate with its inherited parent predicate. The immutable domain model preserves every normative field.

Two registry slices remain in the normative contract. The declaration registry will enforce contracts that span declarations. Finally, shipped registry records will connect evaluator fixtures to executable results. The catalog and resolver will decide final `unknown` applicability results and cross-declaration conflicts after those gates pass.

## Runtime boundary

Canonical YAML is build input and is never itself injected into an agent session. A catalog query produces a generated, provenance-bearing packet containing only the material needed by its caller. The packet may serialize as YAML or JSON. A diagnostic command may generate the packet during a task, but the packet remains adapter output.

Current hosts still require rendered Markdown for cumulative `AGENTS.md` and `CLAUDE.md` files and compact `SKILL.md` entrypoints. When a deployed Skill cannot access the catalog, the Skill must bundle its rendered fallback. Therefore, adapters render Markdown only as a compatibility projection.

## Consequences

The source boundary now publishes the complete local procedure contract and a typed facet-registry boundary. One remaining slice checks contracts across records. The final slice runs evaluator fixtures and compares the results with their declarations. Eutaxis will build the catalog only after both slices pass. External sources cannot adopt the schema until the full normative-contract gate passes.
