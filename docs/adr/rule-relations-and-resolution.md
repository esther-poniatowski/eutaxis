---
tags: []
aliases:
  - Rule relations and contextual resolution
index: "[Architecture decisions](_index.md)"
---

# Rule relations and contextual resolution

## Status

Accepted.

## Purpose

The resolver must return one applicable, dependency-complete semantic set or fail with an explicit reason. It must distinguish inapplicability, exception, substitution, and conflict loss, and it must never reintroduce a declaration already excluded.

## Scope

Semantic resolution operates inside one compilation unit: the declarations selected by one composition manifest for one native scope and target artifact. Deterministic ordering inside that artifact and host-owned precedence between scope artifacts are separate layers defined by [three-layer composition and precedence](three-layer-composition-and-precedence.md).

## Relations and policies

A stable identifier names each rule-local exception. The exception either waives explicitly affected norms or substitutes named local norms. Version 1 assigns each norm to at most one exception and forbids a replacement norm from being affected by another exception. These restrictions make every substitution simultaneous and one-step. Exceptions form a closed list and do not remove the enclosing rule or alter its declaration relations.

The registry distinguishes two sets of unversioned records:

- *manifest-selectable records* are rule sets, rules, and procedures
- *effective-content records* are rules and procedures

A rule set serves only as a selection container. A manifest may select it, and the record may carry `supersedes`. The rule set cannot enter resolver state, a policy conflict, or a policy outcome. Each member rule remains separately addressable. For each member, the registry preserves the inherited predicate, source root, and containing rule-set identifier.

Every identifier in a manifest section must name a manifest-selectable record. Every identifier in the manifest's `policies` field must name a `resolution-policy`. A manifest may select a rule set and one of its members. In that case, the direct member anchor takes precedence over the container anchor. A repeated direct identifier across any two manifest positions is invalid. The referring manifest list item owns each missing, wrong-kind, or repeated-selection diagnostic.

`requires` and `refines` add dependency edges. Their combined directed graph must be acyclic. Only active content records may use these types or `incompatible-with`. `supersedes` adds a lifecycle edge from an active unversioned record to a superseded record of the same kind. Every superseded unversioned record must receive such an edge. These endpoint states prevent a supersession cycle. No record may point to itself. Each `(source, relation type, target)` triple may occur once. One source may still use both `requires` and `refines` for the same target because the two types assert different facts. A repeated triple fails at the later target.

One `incompatible-with` assertion creates one unordered conflict pair. A reverse assertion duplicates the same pair and fails at the later relation target; authors do not repeat the symmetric assertion.

One identifier names either one unversioned record, including a rule-set container or member rule, or one versioned evaluator or operation family. An identifier cannot name both. Every version in a contract family retains one kind and owner, and each `(identifier, version)` pair is unique. Evaluators and operations resolve only through typed exact references. They cannot enter a relation, policy conflict, policy outcome, or manifest section.

Every semantic link must resolve to an active target. This requirement covers:

- relation targets other than `supersedes`
- exact evaluator and operation references
- rule `decided-by` values
- manifest selections and policies
- conflict members and policy outcomes

Discovery remains lifecycle-neutral. Registries and catalogs retain proposed, active, superseded, and retired records so that callers can inspect history without making it binding.

A `resolution-policy` records the decision context and strategy for one conflict. The strategy chooses one outcome:

- retain one conflicting declaration
- replace one conflicting declaration with another declaration
- combine both declarations through a resultant declaration
- fail with an unresolved conflict

Any two effective-content records may form a conflict pair, including records of different kinds. The strategy preserves the following type rules:

- `retain` names either conflict member
- `substitute` replaces one conflict member with an effective-content record of the same kind
- `combine` requires two conflict members of the same kind and names a distinct result of that kind
- `error` names no outcome record

`combine` cannot mean “keep both.” Its result is an already-authored declaration that owns the integrated contract. For a procedure result, that contract includes the complete action graph; the registry does not synthesize a graph. The source boundary requires the retained or replaced identifier to belong to the declared conflict. A substitute differs from the declaration that it replaces, and a combine result differs from both conflict members.

Only declared incompatibilities enter conflict resolution. Each policy names the normalized unordered pair created by one incompatibility assertion. For each composition manifest, the registry considers only the policies referenced by that manifest. A duplicate `(conflict pair, order)` within this set is an error; a policy used by another manifest may reuse the same order. The resolver combines the policy declaration predicate and its `when` predicate with strong Kleene `all`. A policy matches only when this result is true. Among matching policies, the lowest non-negative integer `order` wins. The resolver does not infer semantic specificity between predicates.

Version 1 gives policy authority to the manifest owner. Every policy referenced by a manifest must have the same owner as that manifest. The manifest may still select records owned elsewhere. An authorized policy affects only that compilation unit and does not mutate the source of another owner.

The exact immutable composite remains in the live `DeclarationRegistry`. That composite checks the registry sources. Packaged callers obtain the composite through `acquire_packaged_composite_facet_registry(lock)`. The public resolver accepts the bound registry, a manifest identifier, and a context. The resolver rejects a separate facet registry. Therefore, runtime predicates use the same facet schemas as the source checks. A persisted catalog index lacks complete records. The persisted catalog index also lacks an issued composite. Therefore, the resolver rejects the persisted catalog index.

## Registry diagnostics

The registry establishes one deterministic traversal before it validates cross-record contracts. It resolves every input path, removes repeated canonical paths, and sorts the canonical path strings lexically. Within each source, the registry visits the top-level record before embedded rules. Embedded rules and list fields retain source order.

Each failure belongs to the field that makes the cross-record contract invalid:

- an ordinary identifier collision or a collision between unversioned and versioned families belongs to the later `id`
- a contract family that changes owner belongs to the later `owner`
- a contract family that changes declaration kind belongs to the later `kind`
- a repeated exact contract version belongs to the later `version`
- an evaluator or operation with a relation belongs to its first relation item
- when a non-content record uses a type other than `supersedes`, the diagnostic belongs to the relation type
- when a target is unknown, inactive, of the wrong kind, identical to its source, or repeated, the diagnostic belongs to the referring `target`
- a dependency cycle belongs to the target edge that closes the cycle under registry traversal
- when a superseding source is inactive, the diagnostic belongs to its status
- when a supersession target has another status or kind, the diagnostic belongs to the relation target
- when a superseded record has no active successor, the diagnostic belongs to its status
- a reciprocal `incompatible-with` assertion belongs to the later relation target
- an unknown policy conflict member belongs to the corresponding `conflicts` item
- a policy conflict member that is not effective content belongs to the corresponding `conflicts` item
- a policy without a declared incompatibility belongs to its `conflicts` field
- an invalid `retain`, `with`, or `result` identifier belongs to that strategy field
- a cross-kind `combine` belongs to `strategy.kind`
- a repeated `(conflict pair, order)` belongs to the later policy reference in the manifest
- a policy-owner mismatch belongs to the manifest's policy reference
- a manifest selection that is not selectable, or a policy reference of the wrong kind, belongs to the referring manifest list item
- a repeated direct selection belongs to its later manifest list item
- an unknown exact family or a family of the wrong kind belongs to the reference `id`
- a known exact family with an absent version belongs to the reference `version`
- a missing required operation input belongs to the action's `with` mapping, or to the action when `with` is absent
- an unknown operation input belongs to its binding key
- an invalid literal belongs to the deepest failing path below `literal`
- an unknown procedure parameter belongs to `parameter`
- a parameter whose schema differs from the input schema belongs to `parameter`
- a missing operation failure outcome belongs to the action's `on-failure` mapping
- an additional operation failure outcome belongs to that outcome key
- an operation effect outside the procedure footprint belongs to the action's `operation` reference
- an invariant observed state changed by an operation belongs to the conflicting `observes` item

## Monotone resolution algorithm

For a typed context, the resolver maintains three monotone event sets, `candidate`, `required`, and `excluded`, plus the derived set `effective`. These sets contain effective content only. Candidate and required identifiers may later also occur in excluded; exclusion wins. Only `effective` must remain disjoint from `excluded`.

The resolver requires an active manifest before it begins. A selected active rule set contributes only its active members. For each inactive member, the trace emits `rule-set-member-inactive`, uses the selected rule set as the anchor, and cites the member status as the source. The final component set contains only active rules and procedures.

1. Resolve the manifest and validate the complete context once through the facet registry bound to the declaration registry. Evaluate the manifest predicate. Expand each selected rule set into its member rules. Evaluate each discovered rule or procedure at most once, then add only true records to `candidate`. The rule-set predicate already appears in each member's inherited predicate, so the resolver does not evaluate the container as a separate gate.
2. Expand the combined `requires` and `refines` closure of non-excluded candidates. Evaluate each dependency target at most once. Add a true, non-excluded target to `required`. If a true target is already excluded, leave the dependency unsatisfied until the final alias check; exclusion remains irreversible. A false target fails with `dependency-inapplicable`. An unknown target fails with `dependency-applicability-indeterminate`.
3. Snapshot the active conflict pairs among `candidate ∪ required` minus `excluded`. Sort the canonical pairs lexically. For each pair, evaluate authorized policies by `(order, identifier)` and choose the first true policy. Compute every winning strategy against the snapshot. An unresolved pair, an indeterminate policy set, or an `error` strategy stops processing at that pair. No part of the round changes state.
4. After every pair has a valid winning strategy, compute the union of batch exclusions. Then, validate strategy outcomes in canonical pair order. For each substitute or combine result, emit its discovery event and use its cached declaration trace or evaluate it once. False and unknown results fail immediately with the strategy-specific code. Next, validate the result against `excluded ∪ batch_exclusions`; a result in that union fails with `policy-result-excluded`. Finally, compare proposed aliases with both the retained alias map and earlier proposals in this batch. The same source may map repeatedly to the same target, and every cause is retained. A different target for the same source fails with `ambiguous-policy-alias`. Only a fully valid batch simultaneously applies its exclusions, aliases, and candidate additions. A retain decision applies only to its own pair. Results added to `candidate` participate in the next round.
5. Repeat dependency expansion and conflict resolution until no set changes. Every iteration only adds identifiers to `candidate`, `required`, or `excluded`; it never removes from `excluded`. A later introduction cannot restore an excluded identifier. Finite declarations and acyclic dependencies therefore guarantee termination.
6. Set `effective = (candidate ∪ required) − excluded`. Recheck every dependency of every effective declaration. A dependency is complete when its target is effective. A direct alias may instead point from an applicable target excluded by a policy to an effective target. A true target without either route fails with `dependency-unsatisfied`. Also fail on any unresolved conflict.
7. Project norms and criteria only for final-effective rules. Then, assign final components and dependency edges.

The policy strategies update resolver state as follows:

- `error` raises the declared unresolved-conflict error
- `retain` excludes the non-retained member and creates no alias
- `substitute` excludes `replace`, adds `with` as a candidate, and creates the direct alias `replace → with`
- `combine` excludes both members, adds `result` as a candidate, and creates one direct alias from each member to `result`

An alias satisfies a dependency only when the original target was applicable and its immediate alias target is final-effective. Version 1 does not compose aliases transitively. The resolver never uses `supersedes` to satisfy a dependency.

The `required` set remains conservative. A prerequisite discovered through a dependant remains retained when a later conflict excludes every dependant that discovered it. Its anchor comes from the earliest discovery cause, including an excluded dependant. This over-approximation preserves monotonicity and the termination proof. The certified unit does not describe every retained prerequisite as currently necessary. It emits a dependency edge only when both endpoints are effective, after rewriting an aliased prerequisite to its final-effective target.

## Norm and criterion projection

Each effective rule produces one `ResolvedRuleProjection` containing the rule, its effective norms, and its effective criteria. Norm and criterion identifiers retain their authored order.

The resolver first evaluates the fully inherited predicate of every norm. A true norm enters the initial set. A false or unknown norm remains inactive. The trace distinguishes those two outcomes. Next, the resolver evaluates every exception predicate against the same initial set and context. Only a true exception matches. All matching exceptions act simultaneously. The resolver removes the union of their `affects` sets, then adds the union of their `substitutes` sets.

Every substitute norm must have true applicability, including a substitute already present in the initial set. A false substitute raises `exception-substitute-inapplicable`; an unknown substitute raises `exception-substitute-indeterminate`. The final norm tuple follows authored order.

A criterion is effective when all of its named norms are effective. It is inactive when none are effective. If a criterion names more than one norm and only a proper nonempty subset is effective, resolution raises `partial-criterion-applicability`. The resolver-backed composer boundary validates only that projections are one-to-one and contain valid local identifiers in authored subsequence order. It never repeats these semantic decisions.

## Three-valued decisions

Only `true` activates an object. A policy matches only when both its declaration predicate and its `when` predicate are true. The following table fixes every consequence of `false` and `unknown`.

| Predicate site | `false` | `unknown` |
|---|---|---|
| Manifest applicability | fail with `manifest-inapplicable` | fail with `manifest-applicability-indeterminate` |
| Direct or expanded rule or procedure | omit the candidate and record an inapplicable event | omit the candidate and record an indeterminate event |
| Initial norm applicability | leave the norm inactive | leave the norm inactive and record indeterminacy |
| Exception `when` | record a non-matching exception | record an indeterminate non-matching exception |
| Required dependency target | fail with `dependency-inapplicable` | fail with `dependency-applicability-indeterminate` |
| Conjoined policy predicate | treat the policy as non-matching | treat the policy as indeterminate and non-matching |
| Policy substitute `with` record | fail with `policy-substitute-inapplicable` | fail with `policy-substitute-indeterminate` |
| Policy combine `result` record | fail with `policy-combine-result-inapplicable` | fail with `policy-combine-result-indeterminate` |
| Exception substitute norm | fail with `exception-substitute-inapplicable` | fail with `exception-substitute-indeterminate` |

An eligible policy is referenced by the manifest, owned by the manifest owner, and names the active conflict pair. If no eligible policy matches, an unknown policy predicate makes the conflict fail with `conflict-policy-indeterminate`. Otherwise, the conflict fails with `unresolved-conflict`. Every predicate-dependent event and error carries its truth value and exact applicability trace. This requirement includes `conflict-policy-indeterminate`. Therefore, false and unknown never collapse into the same explanation.

The public operation is `resolve_compilation_unit(registry, manifest_id, context) -> ResolutionResult`. Only the resolver may issue four immutable values:

- `ResolutionResult`
- `ResolutionTrace`
- `ResolutionEvent`
- `ResolvedCompilationUnit`

Their constructors are not public. Success returns one correlated unit and trace. Failure raises `ResolutionError`. The error may carry an immutable failure trace, but it never carries a partial unit.

A resolved compilation unit provides the complete input for the composer. The unit contains:

- every retained semantic record
- every prerequisite edge retained after the resolver applies conflict policies
- the projected norms and criteria of every retained rule
- one manifest section and rank anchor for each retained record

When a manifest names a rule set, the resolver expands its retained member rules. Those members enter the unit instead of the rule-set container. Version 1 does not project package-level edges because a rule set cannot declare them.

The resolver assigns anchors by four rules:

- A record named directly by the manifest keeps its authored `(section, rank)` pair.
- A prerequisite added by closure takes the earliest anchor among all dependants that discovered it, including dependants later excluded.
- For a policy result, the resolver chooses the earliest anchor of every replaced or satisfied record.
- A rule-set member takes its containing rule set's anchor unless the manifest names the member directly.

More than one rule may give candidate anchors to the same record. When the manifest names that record directly, the authored anchor wins. Otherwise, the candidate with the lowest manifest rank wins. The rank identifies one exact `(section, rank)` pair, so no separate section tie-break exists.

For example, a record named directly at rank 3 keeps rank 3 when a policy also introduces the record from rank 0. By contrast, a prerequisite inherited from dependants at ranks 0 and 2 takes rank 0. A direct anchor can conflict with the required order of `sections`. In that case, the resolver preserves the authored anchor, and the composer rejects the backward edge.

The [resolution evidence and failure contract](resolution-evidence-and-failures.md) defines the public models, event kinds, admitted field combinations, error codes, source references, and deterministic traversal. That contract is the sole authority for externally visible resolver evidence.

The applicability evaluator returns a normalized predicate tree in which every node carries its computed truth value. While inheriting parent predicates, the loader may place both predicates below a new `all` node. Consequently, node paths address the normalized tree rather than the source text. The resolver attaches source coordinates to each record and explains every retention or removal. The composer accepts the certified unit and never infers absent edges or records from raw sources.

## Validation

Static validation covers reference existence, inherited applicability narrowing, overlapping exceptions, chained substitutions, directional cycles, symmetric incompatibilities, policy order ties, invalid substitutions and combine results, and owner authority. Registry tests use a closed fixture corpus whose references all resolve. The individually valid source-boundary fixtures do not form this corpus because their illustrative references are intentionally incomplete.

Scenario fixtures exercise matching and non-matching rule-local exceptions, inapplicable replacement norms, conflicts introduced by dependency closure, policy-based substitutes, overlapping conflict batches, alias collisions, conservative prerequisite retention, and attempted reintroduction of an excluded declaration.

## Consequences

Rules carry neither generic conflict notes nor global priority numbers. Composition manifests and resolution policies are first-class sources. The resolver is a build-time and diagnostic catalog operation, not a runtime instruction injector.
