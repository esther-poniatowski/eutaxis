---
tags: []
aliases:
  - YAML declaration schema
index: "[Architecture decisions](_index.md)"
---

# YAML declaration schema

## Status

Accepted. The [bound declaration contract](../../src/eutaxis/data/schemas/declaration-v1.schema.json) and [bound context-facet contract](../../src/eutaxis/data/schemas/context-facets-v1.schema.json) govern author-editable YAML. Their base schemas define the reusable structures without binding a source document. Eutaxis 0.0.0 has not released schema 1. Therefore, this correction retains version 1 and migrates the closed repository corpus atomically.

## Purpose

The schema must let authors state rules and procedures once, validate their semantics before rendering, and retrieve only the declarations required for a task. The source form must preserve rich prose, type every operative relation, and remain readable without a custom editor.

## Canonical form and authority

Pure YAML is the canonical authoring format. Markdown remains available inside YAML block scalars. A tagged-Markdown hybrid is the fallback only if a representative YAML pilot demonstrates a material authoring or round-trip defect.

Versioned JSON Schemas are the normative field, type, cardinality, conditional-requirement, and default contracts. Each authoring format has an unbound base schema and a bound source-document schema. The bound schema requires its logical identifier in the first `_schema` key. `_schema` selects the Eutaxis contract; JSON Schema `$id` identifies a schema resource and does not replace the source binding. Python models must pass the same valid and invalid fixture corpus and may not introduce independent defaults. This ADR fixes the architecture and required semantics, but it is not an exhaustive substitute for the schemas.

Kleisis owns the schema-resource declaration in `specs/schema-resources.yml` and materializes `specs/schema-registry.yml`. That registry exports the declaration and context-facet contracts under stable logical identifiers. The Python loader resolves the same packaged resources offline.

Every author-editable field with a matching Ekphrasis control carries a shape-compatible `x-kind` annotation. The annotation supplies a renderer hint from the admitted Eutaxis vocabulary; it does not alter validation. A free identifier sequence uses `list`, whereas `choices` is reserved for enumerated items. Record controls apply only to mapping items, and `alternatives` applies only to object alternatives. Arbitrary JSON values, embedded JSON Schemas, and unconstrained dynamic maps omit `x-kind`, because Ekphrasis has no typed control that can edit their complete value space. Their source remains valid YAML and their surrounding declared structure remains form-editable. Ekphrasis compiles the exported schemas with its Ajv configuration and ignores the annotations during validation as intended.

## Declaration kinds

The discriminated union contains eight kinds:

- `rule-set` groups coherent rules and supplies one discovery purpose; it is a selection container, not effective content
- `rule` declares one addressable operative constraint
- `procedure` declares a finite externally observable action graph
- `resolution-policy` resolves a named class of semantic conflicts inside one compilation unit
- `composition-manifest` selects and orders content under one declared artifact mechanism
- `evaluator` declares how a criterion is assessed and what its evidence means
- `operation` declares an action node available to procedures
- `decision` records a governance choice, the alternatives considered, and its consequences

Each decision supplies five elements:

- non-empty Markdown `context`
- one or more decision `drivers`, each with a unique local identifier and a Markdown statement
- one or more options, each with a unique local identifier, a Markdown description, and an assessment for every driver
- one `outcome` that names an option
- non-empty Markdown `consequences`

Each assessment names one declared driver and supplies a non-empty Markdown `judgment`. Within one option, a driver may be assessed only once. Each option must assess every declared driver, so validation establishes the complete option-by-driver matrix. These elements record what was chosen and why. They do not duplicate the governed rules.

Only rules carry an `axis`: `reasoning-target`, `output-structure`, or `surface-style`. Procedures are a declaration kind, not a fourth axis. A file may contain one declaration or a declared collection; member objects retain their own `kind` and stable identifier.

For a composition manifest, the selectable kinds are:

- `rule-set`
- `rule`
- `procedure`

The `mechanism` field accepts exactly three values:

- `cumulative`
- `separate-directory`
- `single-slot`

Authors must provide the field explicitly. The opaque `target` remains independent of the selected mechanism.

Rules and procedures are the only effective-content kinds. Each kind admits the following links:

- rules and procedures may use `requires`, `refines`, `incompatible-with`, and `supersedes`
- rule sets, resolution policies, composition manifests, and decisions may use only `supersedes`
- evaluators and operations admit no relations because their positive integer `version` supplies their replacement lineage

During resolution, a rule set expands to its active member rules. The rule set never enters a candidate, required, excluded, effective, or certified set.

## Common envelope

Every authored declaration begins with `_schema: eutaxis:declaration@1`, followed by its stable `id`, `kind`, `owner`, lifecycle status, source revision, applicability, and relations. Classification, failure mode, visibility, rationale, title, and purpose appear only where the normative schema admits them. A required per-rule `description` is excluded because it normally paraphrases the norm. A rule set or procedure may carry one `purpose` for discovery.

The lifecycle vocabulary has four states:

- `proposed` is not binding
- `active` is binding and is the only state admitted for a semantic target or effective resolver content
- `superseded` marks an unversioned record replaced by an active record of the same kind; the active record must point to it through `supersedes`
- `retired` marks a record withdrawn without replacement

Exact evaluator and operation contracts cannot use `superseded`. Their versioned keys express replacement without an unversioned relation. Catalog discovery retains every lifecycle state. The resolver rejects an inactive manifest, records and excludes each inactive rule-set member, and never emits inactive content.

The source loader enforces first-key placement because JSON Schema validates mappings without assigning significance to key order. Nested rule-set members are independently bound and begin with the same `_schema` key. Normalized Python models retain the internal integer `schema_version`; generated catalogs, acquisition records, evaluator-fixture descriptors, evidence records, and migration baselines retain their distinct `schema-version` fields. Those internal formats do not claim to be author-editable declaration documents.

At this intrinsic source boundary, each identifier contains one or more non-whitespace characters. The schema leaves separators uninterpreted so internal sources remain independent of acquisition. The downstream [external-source boundary](external-declaration-identity-and-acquisition.md) applies the exact namespace grammar, owner constraint, and complete reference traversal before it constructs a combined registry. A versioned evaluator or operation reference uses separate `id` and positive-integer `version` fields.

Applicability is conjunctive across nesting. The normalized version 1 language contains `all`, `any`, and `not` nodes plus typed atomic tests with operators `equals`, `in`, and `exists`. Atomic tests name registered context facets. A missing facet makes `equals` and `in` return `unknown`; `exists` always returns true or false.

The boolean nodes use strong Kleene truth tables. `all` returns false if any child is false, true if every child is true, and unknown otherwise. `any` returns true if any child is true, false if every child is false, and unknown otherwise. `not` preserves unknown and reverses true or false. Only a final true activates an object. The semantic consequence of false or unknown depends on the predicate site and is fixed by the [three-valued decision table](rule-relations-and-resolution.md#three-valued-decisions). Therefore, `all: [exists(f), equals(f, x)]` returns false when `f` is missing, while an unguarded `equals(f, x)` remains unknown.

A child does not replace its inherited predicate. The loader constructs `all: [<parent>, <child-local>]`, and a norm narrows a rule through the same structural conjunction. This construction proves narrowing without a general implication solver. The resolver reports the expanded normalized predicate and each atomic result. Resolution policies use explicit order rather than an inferred predicate-specificity relation.

## Context-facet registry

One explicitly supplied YAML registry defines the context vocabulary for a typed load. The registry remains separate from the eight-kind declaration union and binds to its own logical contract. The registry owns all facet entries and records their owner and source revision:

```yaml
_schema: eutaxis:context-facets@1
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

The traced evaluator returns the normalized predicate tree. Every node records its computed truth value. For each atomic node, the trace records the facet name and its presence. The trace retains the observed value when the facet is present. For `equals` and `in`, the trace also retains the authored comparison operand. The Boolean `observed_present` field distinguishes a missing facet from a facet whose value is JSON `null`. Both observed values and authored operands may be sensitive. Therefore, callers must apply a disclosure policy before logging or serializing a trace.

Both evaluator interfaces run three checks before applying missing-facet semantics:

- accept only a supported operator
- require a sequence operand for `in`
- require JSON comparison operands

The canonical source loader additionally performs three checks:

- require or forbid each field according to the operator
- reject every undeclared field
- require at least one distinct alternative for `in`

The former scalar evaluator returned `unknown` for some rejected input when the facet was absent. Schema-valid normalized predicates keep the same strong-Kleene results.

Each operator acts uniformly across the JSON domain:

- `exists` tests whether the key is present, including when its value is null
- `equals` compares the context value with one registered value
- `in` compares the context value with one or more alternatives; for an array-valued facet, each alternative is an array

The following work remains outside the intrinsic declaration schema version 1:

- merging facet registries
- defining aliases or defaults
- coercing values
- deriving facets

The accepted [external-source boundary](external-declaration-identity-and-acquisition.md) supplies that later layer. It issues a composite registry from the mandatory packaged base and owner-authorized additive extensions, then applies external namespace rules before combined declaration registry construction. Aliases, defaults, coercions, and derived facets remain unsupported.

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

A rule may cite its governance basis through `decided-by`. Each list item must name an active, unversioned `decision` record. Only the rule carries this directed link.

`should` and `should-not` require a decision criterion that evaluates the norm or inclusion in the `affects` set of a closed exception. An exception names the local norms affected, its applicability predicate, and either a waiver or replacement norms. Version 1 admits at most one exception for each affected norm and only one-step substitutions: a replacement norm cannot itself be affected by an exception. This direction excludes waivers of the enclosing rule and unrelated declarations. `may` is admitted only for a genuinely discretionary choice. Prohibitions are `must-not` norms, not a parallel prose field. Each success criterion names the norm identifiers that it evaluates and one registered evaluator.

The resolver evaluates each norm under its fully inherited applicability and applies matching exceptions simultaneously. It then projects each effective rule into its effective norms and criteria. A criterion is effective only when all its norms are effective; a proper nonempty subset is an error. The [resolution contract](rule-relations-and-resolution.md#norm-and-criterion-projection) owns the complete projection semantics.

The following rule set demonstrates the common envelope, inherited applicability, modal norms, and a structured evaluator reference:

```yaml
_schema: eutaxis:declaration@1
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
    _schema: eutaxis:declaration@1
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

An `evaluator` names who assesses an obligation. The evaluator declares when it runs. The contract specifies accepted inputs and produced evidence. The contract also specifies failures. A checker names its known-failure fixtures. Version 1 admits three exact enforcement contracts:

- `checker` covers every admitted input and decides the result authoritatively
- `detector` covers only some admitted inputs, proposes candidate results, and states the residual judgment question
- `manual` asks a human reviewer to decide

Each checker names at least one known-failure fixture. Each detector states a non-empty `residual-question` and uses `failure-behavior: block`; checker and manual contracts omit the residual question. The candidate and record failure behaviors remain outside version 1 detector execution because their exception, evidence, and completion semantics are not defined. Eutaxis registers version 1 of `eutaxis/manual-judgment`. Its evidence identifies the reviewer and obligation, then records the observation and conclusion. Therefore, `manual` is not an unregistered escape value.

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

Each action node selects one registered operation and defines all transitions:

- `on-success` names the successor after success
- `on-failure` has one key for each declared failure outcome and contains no other key

A registered guard operation supplies the outcomes used for conditional branches.

To ensure termination, schema version 1 admits no unbounded loop. Every path must reach a declared terminal.

Schema version 1 restricts operation inputs and procedure parameters to closed object schemas. Each schema declares its `properties`. The schema rejects additional properties and requires only declared properties. Property names and action input keys use the identifier syntax of the declaration schema. Each binding selects a parameter or literal variant. The immutable domain model represents these variants with separate types.

An operation may declare a Markdown `method`. The method states an algorithm or command sequence for a consumer that executes the operation from instructions. Preconditions, effects, failure outcomes and recovery remain structured fields; the method does not replace them. Cumulative Markdown renders a present method as part of the exact operation contract, and attention snapshots retain it with each expanded operation occurrence. The field does not declare an execution route or prove that a callable exists. Before deployment, a separate gate must verify an available runner or require a method for every selected agent-executed operation.

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
- a rule set declares a relation
- local identifiers repeat or a local reference does not resolve
- two exceptions contradict each other, or a policy strategy contradicts its declaration
- a procedure graph omits a transition, contains a cycle, or leaves an action unreachable
- a closed object schema requires an undeclared property, or an action binds an undeclared procedure parameter

The facet-registry boundary rejects duplicate identifiers and values outside the JSON domain. The same boundary rejects malformed value schemas and schemas that resolve content externally. The typed route rejects unregistered facet names and invalid comparison constants. Before evaluating a predicate, the runtime rejects unknown context keys and invalid present values.

Diagnostics name the document path and closest YAML source position. The loader conjoins each child applicability predicate with its inherited parent predicate. The immutable domain model preserves every normative field.

The static declaration registry indexes manifest-selectable records, effective-content records, and exact contract families, then validates the cross-record contracts fixed by [rule relations and contextual resolution](rule-relations-and-resolution.md). These checks include relation graphs, policy endpoints, unique manifest selections, and procedure–operation compatibility. Contextual applicability and conflict resolution remain downstream catalog responsibilities.

## Shipped contract execution ^shipped-contract-execution

Packaged version 1 records live under `src/eutaxis/data/declarations/v1/`. The minimum corpus contains:

- `eutaxis/manual-judgment` version 1, which has no executable runner
- `eutaxis/declaration-registry` version 1, a total authoritative checker for the static declaration registry
- `eutaxis/load-declaration-registry` version 1, a side-effect-free operation with one `invalid-registry` failure outcome
- `eutaxis/validate-declaration-registry`, a procedure that binds schema-identical parameters to that operation and maps every outcome
- `eutaxis/declaration-corpus-contract`, a rule containing the norm `establish-valid-corpus`

The norm `establish-valid-corpus` requires Eutaxis to establish one mechanically valid and semantically faithful version 1 declaration corpus before catalog work. Criterion `static-contracts-valid` states that the corpus satisfies the version 1 source boundary and every static cross-record contract; it references `eutaxis/declaration-registry` version 1. Criterion `semantic-contracts-faithful` states that the corpus preserves the intended meanings of its rules, procedures, evaluators, and operations; it references `eutaxis/manual-judgment` version 1. Both criteria evaluate `establish-valid-corpus`.

`eutaxis/load-declaration-registry` accepts two inputs. `sources` is an array whose items have JSON type `string`. `facet-registry` also has JSON type `string`. The returned object requires `registry.valid: true`. The same object reports non-negative integers for `record-count`, `family-count`, and `conflict-count`. The callable has no effects.

The procedure uses the same schemas for its parameters. Each parameter binds to the corresponding callable input. On success, control moves to `valid-registry`. The `valid-registry` node reads `registry.valid`. On `invalid-registry`, the procedure returns the failure of the same name. The procedure declares no effects. The packaged facet registry defines `registry.valid` as a boolean. The normative gate checks only this static contract.

During the first compilation slice, reviewed Python callables receive exact versioned keys. Before a callable runs, Eutaxis freezes and validates its input. After the callable returns, Eutaxis admits schema-valid immutable outputs or a declared failure. The callable for `eutaxis/load-declaration-registry` loads the sources and returns the four declared fields. Source-boundary defects produce `invalid-registry`. The remaining compilation work will run procedure graphs and compose artifacts.

Reviewed Python, rather than YAML, names executable callables. During the normative gate, each exact checker key maps to one callable and one input contract. When Eutaxis compiles, each exact callable key maps to its implementation. Detector runners belong to the enforcement phase. Manual evaluators cannot enter the checker registry. Therefore, authored YAML cannot introduce a command or module path. Authored YAML also cannot supply executable code.

Packaged known-failure descriptors live under `src/eutaxis/data/evaluator-fixtures/v1/` as YAML and conform to the closed `evaluator-fixture-v1` schema. A descriptor contains `schema-version: 1`, a stable `id`, an exact `evaluator` reference, `input-revision: declaration-v1`, an `input` object, and `expected-state: violated`. The input object contains non-empty `sources` and one `facet-registry`. These resource paths use POSIX separators, are relative to the descriptor directory, contain no `..` segment, and must resolve within the packaged fixture root.

The version 1 checker declares five known failures:

- `eutaxis/declaration-registry/unresolved-exact-reference` tests exact semantic references
- `eutaxis/declaration-registry/wrong-schema-binding` tests the bound source contract
- `eutaxis/declaration-registry/unresolved-decided-by` tests the governance link
- `eutaxis/declaration-registry/old-status` tests the current lifecycle vocabulary
- `eutaxis/declaration-registry/orphaned-superseded` tests the required active successor

The `known-failure-fixtures` field contains all five identifiers. Each descriptor names `eutaxis/declaration-registry` version 1.

The fixture loader resolves descriptor paths canonically and visits their string forms in lexical order. Fixture identifiers are unique across that traversal; a duplicate fails at the later `id`. A malformed descriptor fails at its invalid field. An unresolved source or facet-registry resource fails at the corresponding path value. After the exact evaluator and its registered input operation resolve, the fixture input must satisfy that operation's input schema; a mismatch belongs to `input` at the deepest failing instance path. Every identifier in `known-failure-fixtures` must resolve to one descriptor, and a missing fixture belongs to the referring list item. The descriptor must point back to the same evaluator, or the descriptor's `evaluator` field fails. The loader issues the immutable index with a process-local private stamp; direct construction, copying, serialization, and reconstruction fail, and execution rejects an unstamped index before invoking a runner. The loaded index retains one immutable digest record for the descriptor and for each resolved resource field. Each record preserves its canonical path, lowercase SHA-256 value, fixture identifier, resource role, and descriptor document path. Known-failure execution checks these records before and after each invocation and once more before assurance issuance. This contract assumes no hostile concurrent change-and-restoration cycle while a path-based runner executes.

A checker runner returns its exact evaluator reference, input revision, one state from `satisfied`, `violated`, and `blocked`, and evidence. A valid registry returns `satisfied`. A declaration or facet source error returns `violated`. Any exception outside the declared source-error boundaries returns `blocked`, as required by `failure-behavior: block`; the runner does not misreport that exception as a source defect.

The `eutaxis/declaration-registry` evidence schema is closed and has three variants. Satisfied evidence contains `outcome: valid` and the three registry counts. Violated evidence contains `outcome: invalid`; `error-class`, restricted to `declaration-schema`, `declaration-semantic`, `declaration-registry`, `facet-registry-schema`, or `facet-registry-semantic`; `source`; `location`; `message`; and optional positive `line` and `column` integers. Blocked evidence contains `outcome: blocked`, `internal-exception-class`, and `message`. The runner maps the corresponding five public source-error classes to the violated error-class values. Every other exception maps to blocked evidence.

The execution gate requires the returned evaluator identity and input revision to match the invocation. It also requires the state to match the fixture expectation and the evidence to satisfy this schema. A missing runner belongs to the evaluator reference under execution. A returned identity, revision, state, or evidence defect belongs to that result field.

The shipped checker wraps facet-registry loading and `load_declaration_registry`. It accepts the same `sources` and `facet-registry` input as its registered operation contract. Its valid packaged corpus must return `satisfied`. Each of the five known-failure corpora must return `violated` with a located diagnostic. Separately, the packaged procedure and operation must pass the static procedure–operation checks. Planted tests cover malformed and duplicate fixture descriptors, invalid payloads, unresolved resources, missing runner and fixture bindings, result identity and revision mismatches, wrong states, invalid evidence, action bindings, outcome maps, and mutation footprints.

## Runtime boundary

Canonical YAML is build input and is never itself injected into an agent session. A catalog query produces a generated, provenance-bearing packet containing only the material needed by its caller. The packet may serialize as YAML or JSON. A diagnostic command may generate the packet during a task, but the packet remains adapter output.

Current hosts still require rendered Markdown for cumulative `AGENTS.md` and `CLAUDE.md` files and compact `SKILL.md` entrypoints. When a deployed Skill cannot access the catalog, the Skill must bundle its rendered fallback. Therefore, adapters render Markdown only as a compatibility projection.

## Consequences

The authored contract now passes four boundaries:

- sources conform to the schema and intrinsic semantics
- context facets conform to their typed registry
- records satisfy every contract between records
- checkers satisfy their declared result schemas

The first compilation prerequisite can also call one exact reviewed callable and validate its returned value. The artifact fixture composes its outputs deterministically. Catalog construction and external-source acquisition consume the same validated declaration models; neither defines a competing source schema.
