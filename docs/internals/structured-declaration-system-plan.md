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

The procedure-contract gate passed its adversarial review. Three registry gates remain in the normative contract. The downstream compilation stages remain pending behind them.

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
- [ ] Add the canonical YAML facet registry and validate applicability values against registered facet types.
- [ ] Add semantic and versioned-contract indexes, then validate every cross-record contract.
- [ ] Register representative evaluator and operation contracts. Execute each checker against its named fixtures.

A gate closes only after its fixture corpus passes both its known-failure check and an independent adversarial review.

**Exit evidence:** all valid fixtures round-trip without semantic loss; every invalid fixture fails at its located cause; a deliberately invalid fixture proves the gate can fail.

### Eutaxis-owned compilation fixture

- [ ] Build a self-contained fixture corpus owned by Eutaxis before reading external repositories.
- [ ] Exercise a multi-component cumulative artifact, separate-directory artifacts, and a single-slot collision.
- [ ] Prove dependency-before-dependant order, manifest tie-breaking, byte-identical rebuilds, and failure on cycles, duplicate membership, duplicate paths, unresolved conflicts, and multiple slot values.

**Dependency:** the normative contract passes first.

**Exit evidence:** the cumulative renderer passes a genuinely multi-component fixture and preserves independent native-scope artifacts.

### Catalog, registries, and resolution

- [ ] Implement one `declarations` package for loading, models, registries, catalog interfaces, and deterministic JSON indexing.
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
