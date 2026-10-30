---
tags: []
aliases:
  - Identifier and namespace algebra
index: "[Open architectural questions](_index.md)"
---

# Identifier and namespace algebra

**Status.** Resolved by [external declaration identity and acquisition](../adr/external-declaration-identity-and-acquisition.md). **Origin.** Adversarial review of the cross-agent compiler proposal, objection O10 (and §10 Q5).

## Question

The cross-agent compiler required one stable address for declarations supplied
by different repositories, together with an independent account of content and
acquisition state. It also required a collision rule that could not be confused
with host scope precedence.

## Resolution

The accepted ADR owns the identifier grammar, owner constraint, collision
semantics, structured versioned references, and the separation between stable
semantic identity, content revision, and acquisition revision. This record
remains only to preserve the question that led to that decision.
