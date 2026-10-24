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

The cross-record registry classifies `rule-set`, `rule`, and `procedure` as content records. A rule set and each of its member rules remain separately addressable. The registry preserves each member's inherited applicability, source root, and containing rule-set identifier. Only content records may declare relations or serve as relation targets. A `composition-manifest`, `resolution-policy`, `evaluator`, or `operation` must declare an empty `relations` field.

Every declaration named in a manifest section must resolve to a content record. Every identifier in the manifest's `policies` field must resolve to a `resolution-policy`. The referring manifest list item owns a missing or wrong-kind diagnostic.

The relations `requires` and `refines` declare dependencies. Their combined directed graph must be acyclic. The lifecycle relation `supersedes` does not decide a contextual conflict and forms a separate acyclic graph. No declaration may relate to itself. Each `(source, relation type, target)` triple may occur once. The same source may still name both `requires` and `refines` for one target because these are distinct assertions. A repeated triple fails at the later target.

One `incompatible-with` assertion creates one unordered conflict pair. A reverse assertion duplicates the same pair and fails at the later relation target; authors do not repeat the symmetric assertion.

One identifier names either one unversioned record, including a member rule, or one versioned evaluator or operation family. An identifier cannot name both. Every version in a contract family retains one kind and owner, and each `(identifier, version)` pair is unique. Evaluators and operations resolve only through typed exact references. They cannot enter a relation, policy conflict, policy outcome, or manifest section.

A `resolution-policy` records the decision context and strategy for one conflict. The strategy chooses one outcome:

- retain one conflicting declaration
- replace one conflicting declaration with another declaration
- combine both declarations through a resultant declaration
- fail with an unresolved conflict

Any two content records may form a conflict pair, including records of different kinds. The strategy preserves the following type rules:

- `retain` names either conflict member
- `substitute` replaces one conflict member with a content record of the same kind
- `combine` requires two conflict members of the same kind and names a distinct result of that kind
- `error` names no outcome record

`combine` cannot mean “keep both.” Its result is an already-authored declaration that owns the integrated contract. For a procedure result, that contract includes the complete action graph; the registry does not synthesize a graph. The source boundary requires the retained or replaced identifier to belong to the declared conflict. A substitute differs from the declaration that it replaces, and a combine result differs from both conflict members.

Only declared incompatibilities enter conflict resolution. Each policy names the normalized unordered pair created by one incompatibility assertion. For each composition manifest, the registry considers only the policies referenced by that manifest. A duplicate `(conflict pair, order)` within this set is an error; a policy used by another manifest may reuse the same order. Among matching policies, the lowest non-negative integer `order` wins. The resolver does not infer semantic specificity between predicates.

Version 1 gives policy authority to the manifest owner. Every policy referenced by a manifest must have the same owner as that manifest. The manifest may still select content owned elsewhere. An authorized policy affects only that compilation unit and does not mutate a content owner's source.

## Registry diagnostics

The registry establishes one deterministic traversal before it validates cross-record contracts. It resolves every input path, removes repeated canonical paths, and sorts the canonical path strings lexically. Within each source, the registry visits the top-level record before embedded rules. Embedded rules and list fields retain source order.

Each failure belongs to the field that makes the cross-record contract invalid:

- an ordinary identifier collision or a collision between unversioned and versioned families belongs to the later `id`
- a contract family that changes owner belongs to the later `owner`
- a contract family that changes declaration kind belongs to the later `kind`
- a repeated exact contract version belongs to the later `version`
- a non-content record with relations belongs to its first relation item
- an unknown, wrong-kind, self-referential, or repeated relation belongs to the referring `target`
- a dependency or `supersedes` cycle belongs to the target edge that closes the cycle under registry traversal
- a reciprocal `incompatible-with` assertion belongs to the later relation target
- an unknown policy conflict member belongs to the corresponding `conflicts` item
- a policy conflict member that is not content belongs to the corresponding `conflicts` item
- a policy without a declared incompatibility belongs to its `conflicts` field
- an invalid `retain`, `with`, or `result` identifier belongs to that strategy field
- a cross-kind `combine` belongs to `strategy.kind`
- a repeated `(conflict pair, order)` belongs to the later policy reference in the manifest
- a policy-owner mismatch belongs to the manifest's policy reference
- a wrong manifest content or policy kind belongs to the referring manifest list item
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

For a typed context, the resolver maintains three monotone event sets, `candidate`, `required`, and `excluded`, plus the derived set `effective`. Candidate and required identifiers may later also occur in excluded; exclusion wins. Only `effective` must remain disjoint from `excluded`.

1. Build `candidate` from selected declarations whose full inherited applicability conjunction matches.
2. Evaluate all rule-local exceptions against the same initial norm set. Their statically disjoint `affects` sets make the matching transformations simultaneous. Remove the union of all matching `affects` sets, then add the union of the matching `substitutes` sets. Add a substitute only when its full inherited applicability is true; otherwise, fail resolution. An exception never adds a declaration to `excluded`.
3. Expand the dependency closure of non-excluded candidates into `required`. If a dependency is missing, inapplicable, or excluded, then resolution fails unless an active policy names a compatible substitute.
4. Detect declared conflicts among `candidate ∪ required` minus `excluded`. Select exactly one authorized matching policy for each conflict. Add every loser or replaced declaration to `excluded`; add each named substitute or combine result to `candidate`.
5. Repeat dependency expansion and conflict resolution until no set changes. Every iteration only adds identifiers to `candidate`, `required`, or `excluded`; it never removes from `excluded`. Finite declarations and acyclic dependencies therefore guarantee termination.
6. Set `effective = (candidate ∪ required) − excluded`. Recheck that every dependency of every effective declaration is effective or satisfied by its declared substitute. Fail on any unresolved conflict or incomplete dependency.

The resolver returns two objects. First, a resolved compilation unit provides the complete input for the composer. The unit contains:

- every retained semantic record needed by the renderer
- every prerequisite edge retained after the resolver waives local norms and applies conflict policies
- one manifest section and rank anchor for each retained record

When a manifest names a rule set, the resolver expands its retained member rules. Those members enter the unit instead of the rule-set container. A target renderer may depart from this default only when its contract requires the container itself.

The resolver assigns anchors by four rules:

- A record named directly by the manifest keeps its authored `(section, rank)` pair.
- A prerequisite added by closure takes the earliest anchor among its retained dependants.
- For a policy result, the resolver chooses the earliest anchor of every replaced or satisfied record.
- A rule-set member takes its containing rule set's anchor unless the manifest names the member directly.

More than one rule may give candidate anchors to the same record. When the manifest names that record directly, the authored anchor wins. Otherwise, the candidate with the lowest manifest rank wins. The rank identifies one exact `(section, rank)` pair, so no separate section tie-break exists.

For example, a record named directly at rank 3 keeps rank 3 when a policy also introduces the record from rank 0. By contrast, a prerequisite inherited from dependants at ranks 0 and 2 takes rank 0. A direct anchor can conflict with the required order of `sections`. In that case, the resolver preserves the authored anchor, and the composer rejects the backward edge.

Second, the trace states why each predicate matched. The same trace states why each record remained or disappeared. Only the resolver can issue the certified unit. The composer accepts that unit and never infers absent edges or records from raw sources.

## Validation

Static validation covers reference existence, inherited applicability narrowing, overlapping exceptions, chained substitutions, directional cycles, symmetric incompatibilities, policy order ties, invalid substitutions and combine results, and owner authority. Registry tests use a closed fixture corpus whose references all resolve. The individually valid source-boundary fixtures do not form this corpus because their illustrative references are intentionally incomplete.

Scenario fixtures exercise matching and non-matching rule-local exceptions, inapplicable replacement norms, conflicts introduced by dependency closure, policy-based substitutes, and attempted reintroduction of an excluded declaration.

## Consequences

Rules carry neither generic conflict notes nor global priority numbers. Composition manifests and resolution policies are first-class sources. The resolver is a build-time and diagnostic catalog operation, not a runtime instruction injector.
