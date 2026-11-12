---
tags: []
aliases:
  - Cumulative Markdown projection
index: "[Architecture decisions](_index.md)"
---

# Cumulative Markdown projection

## Status

Accepted.

## Purpose

A host that accepts only one cumulative Markdown instruction file must receive every effective instruction needed to apply the resolved rules and procedures, without direct access to canonical YAML or to the live catalog.

## Decision

The cumulative Markdown adapter reads one authenticated composition plan from the live catalog. Components follow the planned order. The resolver determines which content the adapter emits. Its trace retains applicability predicates, exceptions, conflict policies and excluded content. The adapter leaves those records unchanged.

Two profiles serve different readers. The default `auditable` profile uses the full canonical identifier as the rule label. Each norm keeps its identifier. Each effective criterion keeps the exact evaluator identifier and version.

The `agent-instructions` profile serves a bounded resident instruction file. Its consumer label takes the text after the final slash in the canonical identifier. Before rendering, the adapter validates the label against the host grammar and claims it for one canonical identifier. An invalid label or a collision stops rendering.

Every effective norm in the compact profile retains the fields needed by the agent:

- `subject`;
- `action`;
- `timing`;
- `guidance`;
- `rationale`;
- `decision-criterion`.

The compact profile omits norm identifiers and evaluator criteria. The canonical catalog, attention requirements and query interfaces retain those records. When selected rules belong to one rule set, the adapter emits the set's purpose and rationale once before its first effective member.

Both profiles render the five requirement levels as follows:

| Modality | Marker | Keyword |
|---|---|---|
| `must` | ✓ | `MUST` |
| `must-not` | ✗ | `MUST NOT` |
| `should` | ✓ | `SHOULD` |
| `should-not` | ✗ | `SHOULD NOT` |
| `may` | ✓ | `MAY` |

The keyword makes the norm binding. The marker makes the output valid labelled Markdown. Attention packets retain enforcement classes and evaluator instructions because the evaluator contract defines them.

Each procedure block retains its purpose, rationale, parameter schema, entry node, predicates, action graph, effects and declared failures. Predicates retain their class, expression, evaluator reference and observed values. Actions render as graph nodes rather than numbered steps; each node retains its operation reference, bindings and complete outcome transitions. The adapter also renders every exact operation contract referenced by the procedure, including its input and output schemas, preconditions, effects, failure outcomes and recovery. Therefore, a catalog-less consumer can reconstruct the declared operational contract.

Structured values use compact canonical JSON in fenced code blocks. The adapter chooses a backtick fence longer than every backtick run in the payload, so admitted strings cannot terminate the fence. Authored Markdown fields remain Markdown and are not escaped or rewritten.

The public operation accepts one authenticated external composition plan. Catalog construction, resolution correlation and rendering remain inside that transaction. The operation re-authenticates both the plan and the exact catalog state before issuing artifact bytes.

## Consequences

The two profiles keep one canonical source while serving different review and loading constraints.

- The cumulative artifact derives from the canonical source instead of becoming a second authoring source.
- Canonical identifiers and evaluator metadata remain queryable even when the resident file omits them.
- A consumer must select the compact profile explicitly; the auditable profile remains the default.
- Golden tests review the complete rendered bytes for each admitted rule modality and for branching procedures.
- Compact Skill entrypoints remain a separate projection because they have a different activation purpose and token budget.
- A change to this format changes reviewed consumer artifacts and requires a golden diff.
