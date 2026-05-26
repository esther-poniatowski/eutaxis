
# AI prompt - examples

Few-shot and in-context-learning evidence supports a qualified claim: **well-chosen examples often improve rule-following beyond declarative rules alone**, particularly for format, style, and discourse-level constraints that resist precise logical formulation. The effect is model-dependent and sensitive to example quality, ordering, surface features, and task distribution.

Contrastive pairs are useful because they expose a boundary between allowed and disallowed outputs. The prompt should not assume this induces a faithful internal representation of the rule; the pair only needs to give the model a local pattern for distinguishing compliant from non-compliant outputs.

Two complementary information types are often needed to specify behavior:

- **Declarative rules** establish the constraint boundary — what is in and out of the allowed set.
  Examples without rules are subject to **overfitting to surface form**: the model generalizes from the example's incidental properties rather than its underlying principle.
- **Examples** calibrate the local pattern the model should instantiate near that boundary.
  Rules without examples are subject to **boundary drift**: the model may interpret the rule in a plausible but unintended way when producing a concrete output.

## Conditions for relevance

|Rule type|Format|Examples needed?|
|---|---|---|
|Binary, surface-detectable (contractions, pronouns)|`<statement>` + substitution table|Minimal — substitution table suffices|
|Continuous/subjective (register, density)|`<statement>` + contrastive pair + `<note>`|Yes — pair is load-bearing|
|Compositional (rule interacts with others)|`<statement>` + joint-application example|Yes — demonstrates resolution policy|
|Hierarchically structured|Parent `<statement>` + child `<rule>` blocks|At parent level only|

Examples are particularly high-value in the following conditions:

**Condition 1: The rule involves a continuous or subjective dimension**

Rules operating on continuous dimensions (formality, concision, argumentative density) admit an infinite number of partially compliant outputs. An example pair collapses this ambiguity.

*Example*: Rule "*Subjective informal pronouns are forbidden*". The example is non-redundant: it reveals that the required transformation is not just pronoun deletion but *syntactic restructuring* to preserve the propositional content.

```
Rule: Subjective informal pronouns are forbidden.

✗  "You can see that the result follows from Schur's lemma."
✓  "The result follows directly from Schur's lemma."
```

**Condition 2: The rule's failure mode is a specific and recurring surface pattern**

If the rule targets a clearly identifiable anti-pattern, a single invalid example is sufficient and a valid example is often unnecessary (the valid case is the entire complement).

*Example*: Here the valid/invalid pair doubles as a substitution table — maximally efficient.

```
Rule: Contractions are forbidden.

✗  "don't", "can't", "that's"   →   ✓  "do not", "cannot", "that is"
```

**Condition 3: The rule interacts non-trivially with other rules**

When two rules can produce conflicting outputs on the same input, an example that demonstrates their joint application is high-value. Without it, the model may resolve the conflict by whichever rule is most salient, recent, or locally plausible.

## Economy principles

Two economy principles prevent example sets from becoming a maintenance liability:

**Minimum discriminating set.** The set of examples for a rule should be the smallest set such that any output either:

- matches a valid example's pattern
- matches an invalid example's anti-pattern.

> [!WARNING]
> Redundant examples dilute attention and increase prompt length without adding information.

**Generative examples, not enumerative ones.** The examples should illustrate the _principle_ of the rule, not enumerate its _instances_.

An example that instantiates the rule at a point where multiple anti-patterns co-occur is more efficient than two separate examples each targeting one anti-pattern in isolation.

*Example*: This single pair simultaneously demonstrates: pronoun removal, contraction removal, hedging elimination, and concision — four rules in one discriminative act.

```
✗  "I think you can see that we're dealing with a non-trivial case here."
✓  "The case is non-trivial."
```

> [!Warning]
> The _composition_ of that set must also be representative of the task distribution and balanced across failure modes.

ICL literature finds that:

- even randomly assigned labels in few-shot examples can influence output through format priming rather than semantic content,
- the distribution of examples across classes affects the output distribution,
- superficial surface features of examples (length, punctuation) can dominate over their intended semantic signal.

## Ordering: invalid before valid

Two well-documented phenomena are relevant: **recency bias** and **contrastive priming**.

These two effects usually favor the ordering **invalid -> valid**:

1. The valid example occupies the recency-favored position. The model is more likely to continue from the compliant form than from the anti-pattern.
2. The invalid -> valid sequence instantiates a **correction schema**: a deficient form followed by its repair. This pattern is common in editing, code review, and feedback data.
3. The valid example, arriving after the anti-pattern, contrasts with a foregrounded deficient form. This contrast can make the intended boundary easier to apply than a valid example encountered in isolation.

## Field name semantics

> [!NOTE] The following is a plausible design heuristic, not an established empirical law.

Field names function as **semantic primes** that may activate distinct interpretive frames before the model reads the example content. Different frames engage different learned associations, which may propagate into how the examples modulate behavior.

A practical guideline is to select the field name based on the **nature of the constraint**:

|Constraint type|Field names|Effects|Rationale|
|---|---|---|---|
|Hard syntactic rule (contractions, pronouns)|`valid` / `invalid`|Activates a **formal constraint satisfaction** frame.|Value-neutral, the model interprets the task as checking membership in a well-defined set.  <br>Consistent with formal specification language (schema validation, type checking), a domain where the model has learned precise compliance behavior.|
|Soft stylistic preference (register, density)|`preferred` / `avoid`|Activates a **directional instruction** frame — closer to a behavioral directive than an evaluation.|Useful when the constraint is genuinely a preference (not a hard rule) and when the boundary is intentionally soft.|
|Logical/semantic correctness|`correct` / `incorrect`|Activates an **epistemic correctness** frame — closer to truth/falsity than to rule compliance.|Appropriate when the constraint has an underlying ground truth (e.g., grammatical correctness) but introduces an unintended implication: it suggests there is a single correct answer derivable by reasoning, which may cause the model to attempt to justify outputs rather than simply comply.|
|Formal specification (schema, type)|`example` / `counterexample`|Activates a **mathematical** frame — standard in formal proof and type theory pedagogy.|Appropriate when the instruction set is addressed to a mathematically sophisticated model persona and when the rule has the structure of a formal predicate. It is the most precise framing but the least aligned with natural language instruction-following distributions.|

> [!Fail]
> Do not mix frames within a single instruction set. If most rules use `valid`/`invalid`, a frame shift signals a difference in constraint type that may not be intended, and the model will likely treat the other frame rule as softer than the others.
