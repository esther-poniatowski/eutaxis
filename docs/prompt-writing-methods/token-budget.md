# Token-budget and Context-window

Prompt quality is constrained by **token budget**: instructions, retrieved context, tool schemas, examples, and prior outputs all compete for space.

## Empirical phenomena

Transformer attention exhibits a U-shaped positional reliability profile: highest at the beginning and immediately before generation, lowest in the middle.

- _Primacy effect_: very early tokens are more influential.
- _Recency effect_: later context (immediately prior to the generation point) exerts more influence on generation relative to earlier context. This effect is strongest at short distances — but it is consistently observed across model scales.
- _Contrastive priming_: the model's tends to use the immediately preceding example as a generative prior when producing output. If the last example seen is an anti-pattern, that anti-pattern occupies a privileged position in the activation space at generation time.

The mechanism is attention dilution: in a fixed context window with full self-attention, each token's influence on the generated output scales inversely with the total number of tokens competing for the model's attention at the relevant positions.

## Practical implications

**Length of prompts.** The token budget for instructions should be minimized to the extent possible without sacrificing critical information. Each additional token reduces the influence of all other tokens, so every sentence must justify its presence through a unique contribution to behavior.

**Placement of critical instructions.** Critical global instructions usually belong in stable high-level prompt regions so they remain consistently available.

**Placement of soft constraints.** As prompt length increases, soft constraints (stylistic, register-level) degrade faster than hard syntactic constraints, because the latter are more easily pattern-matched. Long prompts must front-load and structurally repeat soft constraints, not merely enumerate them once.
