# Linguistic Form

Several linguistic properties have direct behavioral consequences:

**Indicative versus imperative mood.** Imperative constructions ("produce", "include", "avoid") are more reliably followed than indicative constructions ("the output should", "it is expected that"). The imperative binds the directive to the model's action space directly.

**Quantification precision.** "Often", "usually", "typically" are operationally undefined. Replace with exact conditions: "in all cases where P", "if and only if Q". Reserve hedged quantifiers for genuinely probabilistic policies, and make the distribution explicit.

**Prefer positive specification; scope negative constraints.** "Do not produce vague explanations" leaves the complement class undefined. "Every explanation must reference a specific definition, result, or operation within the current scope" is positively specified and checkable. However, negative constraints remain necessary in safety-critical and style-critical settings — the principle is not to avoid them entirely, but to ensure each negative constraint is scoped, testable, and paired with a positive alternative when possible.

**Avoiding self-referential ambiguity.** Instructions such as "be concise" or "be thorough" are self-undermining — their application changes the length of the instruction itself. Define the target property operationally: "each paragraph must introduce exactly one new conceptual unit; no paragraph may restate content from a preceding paragraph."