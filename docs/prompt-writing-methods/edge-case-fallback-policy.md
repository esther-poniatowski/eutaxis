---
tags: []
aliases:
  - Edge Case and Fallback Policy
index: "[Prompt writing methods](_index.md)"
---

# Edge case and fallback policy

## Edge cases

**Edge cases** are underspecified inputs that the nominal instruction set does not cover. The failure mode is that the model handles them with a locally plausible but globally incorrect strategy.

Effective edge case specification follows the pattern:

```
IF [condition characterizing the edge case]
THEN [exact behavior required]
BECAUSE [justification linking the behavior to the stated objective]
```

The `BECAUSE` clause is a useful default, not a universal empirical law. Vendor guidance and prompt-engineering practice support giving context or motivation when it clarifies the intended behavior, and some rationale-based prompting studies show gains on specific reasoning tasks. The safe claim is narrower: a concise rationale can help the model choose the intended rule application near a boundary, provided the rationale does not add ambiguity or conflict.

## Fallback policy

The **fallback policy** specifies behavior when no other rule applies. It must be explicit: "if no other rule covers the current situation, surface the ambiguity to the user and request clarification rather than producing a best-effort output." Implicit fallbacks increase the risk of confident-but-wrong outputs.
