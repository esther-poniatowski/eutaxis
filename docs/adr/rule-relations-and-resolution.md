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

A stable identifier names each rule-local exception. The exception either waives explicitly affected norms or substitutes named local norms. Version 1 assigns each norm to at most one exception and forbids a replacement norm from being affected by another exception. These restrictions make every substitution simultaneous and one-step. Exceptions form a closed list and do not remove the enclosing rule or alter its declaration relations. The relations `requires` and `refines` declare dependencies. The symmetric relation `incompatible-with` declares a conflict. The lifecycle relation `supersedes` never decides a contextual conflict. Directional dependencies must be acyclic.

A `resolution-policy` records the decision context and strategy for one conflict. The strategy chooses one outcome:

- retain one conflicting declaration
- replace one conflicting declaration with another declaration
- combine both declarations through a resultant declaration
- fail with an unresolved conflict

`combine` cannot mean “keep both”; its resultant declaration owns the composed norms and criteria. The source boundary requires the retained or replaced identifier to belong to the declared conflict. A substitute differs from the declaration that it replaces, and a combine result differs from both conflict members.

Only declared incompatibilities enter conflict resolution. Among matching policies, the lowest non-negative integer `order` wins; a duplicate order for the same conflict is an error. The resolver does not infer semantic specificity between predicates. A cross-owner policy belongs to the consuming composition manifest and does not mutate either owner's source. The manifest owner must have authority over that compilation unit.

## Monotone resolution algorithm

For a typed context, the resolver maintains three monotone event sets, `candidate`, `required`, and `excluded`, plus the derived set `effective`. Candidate and required identifiers may later also occur in excluded; exclusion wins. Only `effective` must remain disjoint from `excluded`.

1. Build `candidate` from selected declarations whose full inherited applicability conjunction matches.
2. Evaluate all rule-local exceptions against the same initial norm set. Their statically disjoint `affects` sets make the matching transformations simultaneous. Remove the union of all matching `affects` sets, then add the union of the matching `substitutes` sets. Add a substitute only when its full inherited applicability is true; otherwise, fail resolution. An exception never adds a declaration to `excluded`.
3. Expand the dependency closure of non-excluded candidates into `required`. If a dependency is missing, inapplicable, or excluded, then resolution fails unless an active policy names a compatible substitute.
4. Detect declared conflicts among `candidate ∪ required` minus `excluded`. Select exactly one authorized matching policy for each conflict. Add every loser or replaced declaration to `excluded`; add each named substitute or combine result to `candidate`.
5. Repeat dependency expansion and conflict resolution until no set changes. Every iteration only adds identifiers to `candidate`, `required`, or `excluded`; it never removes from `excluded`. Finite declarations and acyclic dependencies therefore guarantee termination.
6. Set `effective = (candidate ∪ required) − excluded`. Recheck that every dependency of every effective declaration is effective or satisfied by its declared substitute. Fail on any unresolved conflict or incomplete dependency.

The resolver returns the effective set and a trace containing every applicability decision, waiver, substitution, dependency, policy match, exclusion, and inclusion. A caller can therefore ask why a declaration is present or absent without treating absence as completion evidence.

## Validation

Static validation covers reference existence, inherited applicability narrowing, overlapping exceptions, chained substitutions, directional cycles, symmetric incompatibilities, policy order ties, invalid substitutions and combine results, and owner authority. Scenario fixtures exercise matching and non-matching rule-local exceptions, inapplicable replacement norms, conflicts introduced by dependency closure, policy-based substitutes, and attempted reintroduction of an excluded declaration.

## Consequences

Rules carry neither generic conflict notes nor global priority numbers. Composition manifests and resolution policies are first-class sources. The resolver is a build-time and diagnostic catalog operation, not a runtime instruction injector.
