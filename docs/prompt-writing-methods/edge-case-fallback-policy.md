# Edge Case and Fallback Policy

## Edge Cases

**Edge cases** are underspecified inputs that the nominal instruction set does not cover. The failure mode is that the model handles them with a locally plausible but globally incorrect strategy.

Effective edge case specification follows the pattern:

```
IF [condition characterizing the edge case]
THEN [exact behavior required]
BECAUSE [justification linking the behavior to the stated objective]
```

The `BECAUSE` clause is empirically validated: models that receive a rationale for a rule exhibit more robust generalization to novel cases near the rule's boundary. This is consistent with the understanding that instruction-following operates through learned associations between task descriptions and behaviors — rationale enriches the associative context.

## Fallback Policy

The **fallback policy** specifies behavior when no other rule applies. It must be explicit: "if no other rule covers the current situation, surface the ambiguity to the user and request clarification rather than producing a best-effort output." Implicit fallbacks produce confident-but-wrong outputs.