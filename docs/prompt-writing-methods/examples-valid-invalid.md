
# AI Prompt - Examples

The empirical evidence is unambiguous: **contrastive examples (valid + invalid pairs) produce substantially more reliable rule-following than declarative rules alone**, particularly for stylistic and discourse-level constraints that resist precise logical formulation. 

The mechanism is that contrastive pairs force the model to compute a **discriminant** between the two cases. This discriminant is a far more precise internal representation of the rule than a declarative statement alone can induce.

Thus, two complementary information types are necessary to specify behavior:

- **Declarative rules** establish the constraint boundary — what is in and out of the allowed set.
  Examples without rules are subject to **overfitting to surface form**: the model generalizes from the example's incidental properties rather than its underlying principle.
- **Examples** calibrate the _metric_ the model uses to measure distance from that boundary. 
  Rules without examples are subject to **boundary drift**: the model correctly represents the rule in latent space but applies an incorrect decision threshold when instantiating it.

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

When two rules can produce conflicting outputs on the same input, an example that demonstrates their joint application is high-value. Without it, the model defaults to resolving the conflict by whichever rule was most recently stated.

## Economy Principles

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

## Ordering: Invalid Before Valid

Two well-documented phenomena are relevant: **recency bias** and **contrastive priming**.

These two effects jointly favor the ordering **invalid → valid**:

1. The valid example occupies the recency-favored position. The model's generative prior at the moment of output production is shaped by the correct form, not the anti-pattern.
2. The invalid → valid sequence instantiates a **correction schema** — a pattern the model has been exposed to at massive scale through RLHF feedback, code review, and editorial revision corpora. This schema carries strong learned associations: _here is a deficient form; here is its repair_. Activating this schema aligns the model's processing with its training distribution.
3. The valid example, arriving after the anti-pattern, is computed **in contrast to** a foregrounded deficient form. This contrastive computation produces a sharper discriminant than a valid example encountered in isolation.

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
