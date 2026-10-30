---
tags: []
aliases:
  - Cross-repository source acquisition
index: "[Open architectural questions](_index.md)"
---

# Cross-repository source acquisition

**Status.** Resolved by [external declaration identity and acquisition](../adr/external-declaration-identity-and-acquisition.md). **Origin.** Adversarial review of the cross-agent compiler proposal, objection O8.

## Question

Source components may originate in separate rule-owning repositories. Integrity
hashes alone did not specify how their bytes arrived, which authority owned
their vocabulary, or whether verification and parsing consumed the same bytes.

## Resolution

The accepted ADR owns the offline transport set, manifest and canonical lock,
descriptor-anchored byte boundary, packaged internal authority, additive facet
composition, Git-submodule proof, catalog provenance, and issued acquisition
result. Network and capability acquisition remain outside version 1. This
record remains only to preserve the question that led to that decision.
