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

The cumulative Markdown adapter renders one authenticated composition plan from the live declaration catalog. The adapter emits components in planned order and emits only the norms and criteria retained by contextual resolution. Applicability predicates, exceptions, conflict policies and excluded content remain in the resolution trace; the adapter does not restate or reinterpret them.

Each rule block uses the full declaration identifier as its label. Every effective norm retains its local identifier, subject, action, timing, authored guidance, rationale and decision criterion. BCP 14 modalities render as follows:

| Modality | Marker | Keyword |
|---|---|---|
| `must` | ✓ | `MUST` |
| `must-not` | ✗ | `MUST NOT` |
| `should` | ✓ | `SHOULD` |
| `should-not` | ✗ | `SHOULD NOT` |
| `may` | ✓ | `MAY` |

The keyword carries the normative meaning; the marker preserves compatibility with the existing labelled-Markdown grammar. Each effective criterion retains its local identifier, statement and exact evaluator reference. Enforcement class and evaluator execution instructions remain in attention packets because the evaluator contract, rather than the rule, defines them.

Each procedure block retains its purpose, rationale, parameter schema, entry node, predicates, action graph, effects and declared failures. Predicates retain their class, expression, evaluator reference and observed values. Actions render as graph nodes rather than numbered steps; each node retains its operation reference, bindings and complete outcome transitions. The adapter also renders every exact operation contract referenced by the procedure, including its input and output schemas, preconditions, effects, failure outcomes and recovery. Therefore, a catalog-less consumer can reconstruct the declared operational contract.

Structured values use compact canonical JSON in fenced code blocks. The adapter chooses a backtick fence longer than every backtick run in the payload, so admitted strings cannot terminate the fence. Authored Markdown fields remain Markdown and are not escaped or rewritten.

The public operation accepts one authenticated external composition plan. Catalog construction, resolution correlation and rendering remain inside that transaction. The operation re-authenticates both the plan and the exact catalog state before issuing artifact bytes.

## Consequences

- The cumulative artifact is a compatibility projection, not a second authoring source.
- Golden tests review the complete rendered bytes for each admitted rule modality and for branching procedures.
- Compact Skill entrypoints remain a separate projection because they have a different activation purpose and token budget.
- A change to this format changes reviewed consumer artifacts and requires a golden diff.
