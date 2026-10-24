---
tags: []
aliases:
  - Resolution evidence and failure contract
index: "[Architecture decisions](_index.md)"
---

# Resolution evidence and failure contract

## Status

Accepted.

## Purpose

Resolver evidence must reconstruct every semantic decision without exposing a partial compilation unit. The public types therefore close the successful result, event vocabulary, source coordinates, traversal order, and failure codes before the resolver implementation begins.

## Public boundary

The public call is:

```python
resolve_compilation_unit(
    registry: DeclarationRegistry,
    manifest_id: str,
    context: Mapping[str, object],
) -> ResolutionResult
```

The call uses only the facet registry retained by `DeclarationRegistry`. It resolves the manifest before validating the context. An unknown or wrong-kind manifest raises `ResolutionError` before a trace exists. For a known composition manifest, the bound facet registry validates the complete context once. A `FacetContextError` propagates before the resolver issues an event.

Only `resolution.py` issues the following frozen values; their constructors reject direct calls:

- `ResolutionResult(unit, trace)`
- `ResolutionTrace(manifest, facet_registry, facet_source_revision, events)`
- `ResolutionEvent(...)`
- `ResolvedCompilationUnit(manifest, components, dependencies, rule_projections)`

`ResolvedRuleProjection(declaration: str, norms: tuple[str, ...], criteria: tuple[str, ...])` contains ordered local identifiers. The unit contains exactly one projection for each effective rule and no projection for a procedure. `ManifestAnchor(section: str, rank: int)`, `ResolvedComponent`, `ResolvedDependency`, and `ResolvedRuleProjection` are publicly constructible frozen leaves. Tests and consumers use them as structural values; only the aggregate certified objects require private issuance.

A successful result contains one correlated unit and trace. The trace records `registry.facet_registry.id` and `registry.facet_registry.source_revision` in its two facet fields. A `ResolutionError` may contain a failure trace but never a unit. Persisted catalog indexes cannot call the resolver.

## Exact source and anchor types

`ResolutionSource` is a publicly constructible frozen leaf with four fields:

- `path: Path`: the absolute resolved source path
- `document_path: DocumentPath`: the exact tuple of string and integer path components
- `line`: the positive one-based source line
- `column`: the positive one-based source column

The source points to the authored field that caused the event or failure. For example, a dependency discovery points to its relation target, and a manifest selection points to its declaration item.

`ManifestAnchor` contains the section identifier and the zero-based rank in the manifest's flattened authored order.

## Event record

Every event contains `ordinal`, `kind`, `declaration`, `source`, and `causes`. The ordinal is zero-based and equals the event's index in the trace. Causes are unique earlier ordinals in ascending order. The declaration identifies the semantic record affected by the event.

The remaining fields are nullable:

- `anchor: ManifestAnchor`
- `relation: Literal["requires", "refines"]`
- `dependant: str`
- `policy: str`
- `exception: str`
- `norm: str`
- `criterion: str`
- `conflict: tuple[str, str]`
- `replacement: str`
- `truth: TruthValue`
- `applicability: ApplicabilityTrace`

`ResolutionEventKind` is the following closed string enumeration. The table fixes the declaration owner, source owner, and additional fields of each kind. A field not listed for that kind must be null.

| Event kind | `declaration` | `source` | Required additional fields |
|---|---|---|---|
| `manifest-evaluated` | manifest | manifest applicability | `truth`, `applicability` |
| `manifest-selected` | selected record | manifest declaration item | `anchor` |
| `rule-set-member-expanded` | member rule | member rule root | `anchor` |
| `dependency-discovered` | dependency target | relation target | `anchor`, `relation`, `dependant` |
| `policy-result-discovered` | result record | strategy outcome field | `anchor`, `policy`, `conflict` |
| `declaration-evaluated` | evaluated record | record applicability | `anchor`, `truth`, `applicability` |
| `conflict-detected` | source of the registered incompatibility | incompatibility target | `conflict` |
| `policy-evaluated` | policy | policy root | `conflict`, `truth`, `applicability` |
| `conflict-resolved` | winning policy | strategy kind | `policy`, `conflict` |
| `declaration-excluded` | excluded record | `retain`, `replace`, or combine `kind` field | `policy`, `conflict` |
| `alias-created` | alias source | substitute `with` or combine `result` field | `policy`, `conflict`, `replacement` |
| `declaration-effective` | effective record | record root | `anchor` |
| `norm-evaluated` | enclosing rule | norm root | `norm`, `truth`, `applicability` |
| `exception-evaluated` | enclosing rule | exception `when` | `exception`, `truth`, `applicability` |
| `norm-removed` | enclosing rule | matching exception `affects` item | `norm`, `exception` |
| `norm-substituted` | enclosing rule | matching exception `substitutes` item | `norm`, `exception` |
| `norm-effective` | enclosing rule | effective norm | `norm` |
| `criterion-effective` | enclosing rule | criterion | `criterion` |
| `criterion-inactive` | enclosing rule | criterion | `criterion` |
| `unit-issued` | manifest | manifest root | none |

Every predicate-dependent event contains both `truth` and `applicability`. Other event kinds contain neither field. Only applicability traces retain observed context values.

Each discovery route emits its own event. The resolver evaluates a declaration predicate once and caches its trace. The final `declaration-effective` event cites every discovery event for that declaration, including repeated dependency discoveries and routes through later-excluded dependants.

## Failure record

`ResolutionErrorCode` is the following closed string enumeration:

- `unknown-manifest`
- `manifest-wrong-kind`
- `manifest-inapplicable`
- `manifest-applicability-indeterminate`
- `dependency-inapplicable`
- `dependency-applicability-indeterminate`
- `dependency-unsatisfied`
- `unresolved-conflict`
- `conflict-policy-indeterminate`
- `ambiguous-policy-alias`
- `policy-substitute-inapplicable`
- `policy-substitute-indeterminate`
- `policy-combine-result-inapplicable`
- `policy-combine-result-indeterminate`
- `policy-result-excluded`
- `exception-substitute-inapplicable`
- `exception-substitute-indeterminate`
- `partial-criterion-applicability`

`ResolutionError` contains `code`, `detail`, and optional `source`, `trace`, `truth`, and `applicability`. The two predicate fields occur together. They are required for every error whose code ends in `inapplicable` or `indeterminate`, including `conflict-policy-indeterminate`. They are absent for every other code.

`unknown-manifest` has no source and no trace. `manifest-wrong-kind` points to the record kind and has no trace. Every later error contains the immutable trace through the last event issued before failure. `dependency-unsatisfied` points to the original relation and contains neither predicate field. A conflict failure points to the conflict relation when no eligible policy exists, to the policy root for an indeterminate combined predicate, or to the strategy field for `error`. An alias collision points to the later policy under canonical batch order. A partial criterion points to that criterion. A blocked policy result points to its strategy outcome field.

The `error` policy strategy raises `unresolved-conflict`. If a policy result occurs in a prior exclusion or in the current batch exclusions, `policy-result-excluded` preserves the absorbing exclusion instead of restoring the record.

## Deterministic traversal

The resolver issues events in six phases:

1. Evaluate the manifest.
2. Visit manifest sections and items in authored order. Visit rule-set members in source order. Gather every initial discovery route, then evaluate distinct declarations by `(anchor rank, identifier)`.
3. For each resolution round, visit active declarations by `(anchor rank, identifier)` and their dependency relations in authored order. Record every discovery cause, but evaluate each declaration at most once.
4. Snapshot active conflict pairs and visit them in canonical lexical order. Emit `conflict-detected` before visiting policies. Evaluate each policy's normalized `all: [applicability, when]` predicate by `(order, identifier)` until the first true result. If no policy is true, the first unknown policy in that order supplies the trace and source of `conflict-policy-indeterminate`; the absence of an unknown produces `unresolved-conflict`. An `error` strategy also fails at its pair. Any selection or strategy failure stops the round before later pairs and before state changes. Policy events cite the detection event. After every pair has a valid winner, compute batch exclusions. For each policy result in pair order, emit `policy-result-discovered`, use its cached declaration trace or evaluate it once, then apply the false, unknown, exclusion, and alias checks in that order. Only a fully valid batch changes state. After applying the batch, emit `conflict-resolved`, `declaration-excluded`, and `alias-created` events. `conflict-resolved` cites the winning policy event. Newly added candidates enter the next round.
5. Visit final-effective declarations by `(anchor rank, identifier)`. For each effective rule, evaluate norms in authored order, exceptions in authored order, and criteria in authored order.
6. Issue the unit event.

For an overlapping conflict batch, a retain decision governs only its pair. Exclusion by any other pair wins. Each result is invalid when a prior exclusion or any exclusion in the current batch contains it. Two aliases from the same source may merge only when they name the same target. This comparison includes aliases retained from earlier rounds. Otherwise, resolution raises `ambiguous-policy-alias`.

Batch validation stops at the first failure in canonical conflict-pair order. Within one pair, the strategy result is checked before derived aliases, and derived aliases are checked by alias-source identifier. These rules select one error and one trace prefix when several proposals are invalid. A failed batch emits no state-change event. A successful batch emits state-change events by canonical conflict pair. Within each pair, `conflict-resolved` comes first, exclusions follow by declaration identifier, and aliases follow by alias source.

Final components and rule projections follow `(anchor rank, identifier)`. Dependency edges are rewritten through valid direct aliases, deduplicated by endpoint pair, and sorted by `(dependant, prerequisite)`.

## Consequences

The trace is deterministic evidence, not a serialized runtime context. A caller that logs or serializes applicability traces must apply its disclosure policy. The composer receives only the certified unit and validates its structure without reconstructing resolver decisions.
