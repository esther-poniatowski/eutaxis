---
tags: []
aliases:
  - Structured declaration system plan
index: "[Design Documentation — Methods](_index.md)"
---

# Structured declaration system plan

This plan implements the accepted structured-source decisions and assigns only work owned by Eutaxis. A consuming repository owns the cross-project assignment between its sources, Eutaxis, and other providers; that assignment is not duplicated here.

## Current state

Free-form Markdown remains the production source. The loader for schema version 1 rejects malformed source data. The loader returns complete immutable models and conjoins inherited applicability predicates.

Independent adversarial reviews approved the facet registry and static declaration registry. The declaration registry covers relation graphs, policies, manifests, exact contracts, and procedure–operation compatibility. For each defect, the registry reports the field that makes the corpus invalid. Contextual applicability and conflict resolution remain pending.

Before Eutaxis may compile downstream artifacts, it must close one normative gate. This gate requires the exact packaged records and executable evidence defined in the [shipped execution contract](../adr/yaml-declaration-schema.md#^shipped-contract-execution). The gate also requires every checker to fail its named known-failure fixture.

## Decision log and open prerequisites

- YAML is canonical; tagged Markdown is only an evidence-triggered fallback.
- Procedures are a declaration kind, separate from the three rule axes.
- Semantic resolution, deterministic artifact composition, and host scope precedence are separate layers.
- Namespace algebra and cross-repository acquisition must be decided before any external owner, including Oikos or Hermeneia, becomes a pilot source.
- Declaration identifiers remain opaque, and versioned references remain structured, until that namespace decision is recorded.
- SQLite remains conditional on measured JSON-index performance.

## Work sequence

### Normative contract

The normative contract closes through the following gates.

- [x] Implement the versioned JSON Schema for all seven declaration kinds: rule set, rule, procedure, resolution policy, composition manifest, evaluator, and operation.
- [x] Specify and test applicability semantics and explicit policy ordering.
- [x] Generate typed models from the schema or prove their conformance against the same fixture corpus.
- [x] Complete and adversarially review the [procedure contract](../adr/yaml-declaration-schema.md).
- [x] Add the canonical YAML facet registry and validate applicability values against registered facet types.
- [x] Add semantic and versioned-contract indexes, then validate the static cross-record contracts fixed by the [relation contract](../adr/rule-relations-and-resolution.md).
- [ ] Package the exact records required by the [shipped execution contract](../adr/yaml-declaration-schema.md#^shipped-contract-execution), including `eutaxis/declaration-corpus-contract` and its named norm and criteria.
- [ ] Implement the versioned YAML fixture schema and deterministic fixture index, including unique identifiers, portable resource paths, typed payload validation, and located errors.
- [ ] Implement the checker-only runner registry, keyed by exact evaluator reference and linked to one exact operation input contract; reject manual, detector, and unresolved bindings in this gate.
- [ ] Run the valid corpus and every known-failure descriptor. Check evaluator identity, `declaration-v1`, result state, exception class, and the closed evidence schema.
- [ ] Load the packaged procedure and operation through the static registry, then verify their bindings, outcome map, and empty mutation footprint. Defer operation execution to the compilation fixture.
- [ ] Plant malformed and duplicate descriptors, invalid payloads, unresolved resources, missing bindings, mismatched results, invalid evidence, action-binding defects, outcome defects, and footprint defects before independent adversarial review.

A gate closes only after its fixture corpus passes both its known-failure check and an independent adversarial review.

**Exit evidence:** packaged records load as one closed registry; every checker rejects its named known-failure fixture with schema-valid evidence; the procedure–operation pair passes; and every planted defect makes the gate fail at its owner.

### Eutaxis-owned compilation fixture

- [ ] Build a self-contained fixture corpus owned by Eutaxis before reading external repositories.
- [ ] Exercise a multi-component cumulative artifact, separate-directory artifacts, and a single-slot collision.
- [ ] Prove dependency-before-dependant order, manifest tie-breaking, byte-identical rebuilds, and failure on cycles, duplicate membership, duplicate paths, unresolved conflicts, and multiple slot values.

**Dependency:** the normative contract passes first.

**Exit evidence:** the cumulative renderer passes a genuinely multi-component fixture and preserves independent native-scope artifacts.

### Catalog, registries, and resolution

This phase turns the validated registry into resolved, queryable outputs.

- [x] Consolidate the source boundary and cross-record registry in one `declarations` package.
- [ ] Implement catalog interfaces and deterministic JSON indexing over the validated registry.
- [ ] Keep the rendered-Markdown parser behind its current public behavior until migration proves its final disposition.
- [ ] Implement the monotone candidate/excluded/required/effective algorithm and provenance-bearing explanation traces.
- [ ] Test waived dependencies, explicit substitutes, combine results, policy order ties, owner authority, attempted reintroduction of exclusions, overlap among monotone event sets, and disjointness of effective and excluded results.

**Exit evidence:** every effective declaration is dependency-complete, every omission is explained, and unresolved or unauthorized decisions fail.

### Enforcement and completion

- [ ] Derive mechanical, assisted, and deliberative classes from evaluator contracts.
- [ ] Emit three attention packets and a separate resolution trace.
- [ ] Require evidence for every effective criterion in the completion ledger.
- [ ] Permit only explicit, owned, expiring migration baselines as terminal non-blocking findings.

**Exit evidence:** clean checker output cannot complete an unmapped criterion, and unchecked, violated, or blocked criteria prevent success.

### Projections and compatibility

- [ ] Render cumulative Markdown and compact Skill entrypoints from catalog records.
- [ ] Emit normalized YAML or JSON query packets with context, trace, registry versions, hashes, and source revisions.
- [ ] Bundle rendered fallbacks for Skills whose deployment cannot guarantee catalog access.
- [ ] Extend `plan`, `check`, and `explain` with resolution and completion evidence.

**Exit evidence:** existing Markdown consumers receive reviewable golden artifacts; query consumers retrieve bounded packets without direct source access.

### Namespace, acquisition, and external pilot

- [ ] Decide the identifier namespace and cross-repository acquisition contract.
- [ ] Publish migration tooling, semantic-diff tooling, and rollback before converting an external source.
- [ ] Only then pilot one coherent Oikos rule set and one procedure.

**Exit evidence:** the external pilot cites its acquired revisions and survives validation, resolution, enforcement, rendering, and drift checking.

### Migration accountability

- [ ] Produce a ledger mapping every legacy unit to a new identifier, an explicitly named merge target, a retired rationale, or a deferred owner and prerequisite.
- [ ] Compare modality, applicability, exceptions, criteria, evaluator, and every rendered consumer before and after migration.
- [ ] Require zero unaccounted units and prove the ledger gate fails when a planted legacy unit is omitted.

**Exit evidence:** every legacy unit and consumer projection is accounted for, and rollback restores the last reviewed generated release.
