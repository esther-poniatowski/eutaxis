# Token-budget and Context-window

Prompt quality is constrained by **token budget**: instructions, retrieved context, tool schemas, examples, and prior outputs all compete for space.

## Empirical phenomena

Long-context transformer behavior often exhibits a U-shaped positional reliability profile: models tend to use information near the beginning and near the generation point more reliably than information in the middle. The strength of this pattern depends on the model, task, and prompt layout.

- _Primacy effect_: very early tokens are more influential.
- _Recency effect_: later context, especially text immediately before generation, can exert disproportionate influence relative to earlier context.
- _Contrastive priming_: a nearby example can shape the pattern the model continues. If the last example seen is an anti-pattern, the prompt may make that anti-pattern locally salient.

The mechanism is not a simple inverse scaling law over tokens. Empirical work on lost-in-the-middle behavior and positional attention bias supports the practical conclusion that longer prompts make instruction placement and retrieval layout more important, but the exact mechanism varies across architectures and training regimes.

## Practical implications

**Length of prompts.** The token budget for instructions should be minimized to the extent possible without sacrificing critical information. Longer prompts increase the surface area for conflicts, salience shifts, and retrieval failures, so every sentence must justify its presence through a unique contribution to behavior.

**Placement of critical instructions.** Critical global instructions usually belong in stable high-level prompt regions so they remain consistently available.

**Placement of soft constraints.** As prompt length increases, soft constraints (stylistic, register-level) are often more fragile than hard syntactic constraints, because the latter can be matched against explicit surface patterns. Long prompts should place important soft constraints in prominent regions and reinforce them through examples or output contracts when they matter.
