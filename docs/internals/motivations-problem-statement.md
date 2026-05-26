# Motivations

## Goal

> [!CHECK] Global objective
> Design a **system for governing AI-assisted production of structured content** in a modular vault.
> A vault under eutaxis is a **modular generative system** that advances a project-declared primary objective through a sequence of atomic contracted units.
> The decisive object is the **generative contract of each unit inside the vault-level structure**, rather than the polished output itself.

**Criteria**: The system must:

- provide structured procedures, workflows, and artifacts to orchestrate AI-human interaction on complex generative projects,
- combine AI autonomy, human control, and their interaction,
- implement the best design practices: modularity, separation of concerns, flexibility, extensibility, predictability, and maintainability.

One main challenge addressed by the system is to constrain AI agents in their **generative behavior**: what must be produced, from which inputs, in what order, and what counts as success.

---

## Problem statement and diagnosis

This section describes the failure modes the system aims to address, and their underlying causes. The diagnosis identifies the components needed and the rationale behind their design.

**Hierarchy of failure rates**:

- style rules are easy to follow,
- local formatting rules are easy to follow,
- abstract values like rigor and clarity are partially followable,
- global architectural constraints across many units are much harder unless externalized into explicit contracts and metadata.

**Dominant failure modes**:

- The instruction set emphasizes **syntactic and presentation rules** that are all **downstream** of the generative process (style, formatting, prose quality criteria, modularity, structure...).
- The **generative process itself remains unguided**: to advance toward a determinate output, the agent needs to be constrained at the level of _generative logic_ — semantic and structural rules. It needs an _operative_ mechanism that decides what must be produced, in what order, using what inputs, why this is the next necessary step, and what counts as success.
- The **global architecture of the vault** is under-specified.

|Problem|Symptoms|Cause|
|---|---|---|
|**Superficiality**|The agent produces content that is _plausibly_ related rather than _structurally necessary_ to address the unit's question. It defaults to associative retrieval: collects related material, provides a summary...|**Weak atomicity**: the _unit of work_ is not rigorously defined. The unit is generated from a vague or thematic intention; the "question" is too broad and not sharply delineated.<br>**Absence of pre-committed structural skeleton**: the agent is not forced to commit, _before_ writing, to an exact structural plan.<br>**Missing decision criteria**: the instructions constrain _form_ and _second-order desiderata_ (e.g. "avoid redundancy", "separate concerns") rather than _generative behavior_ (e.g. "include _only_ material required to establish the unit's output").|
|**Accumulation**|The agent:<br>- accumulates loosely related material,<br>- drifts in scope,<br>- appends remarks that are not structurally necessary,<br>- implicitly broadens the unit's purpose.|**Missing a termination criterion**: no endpoint or success criterion is formalized. This is especially severe in open-ended generative tasks because neighboring ideas are often genuinely interesting.|
|**Arbitrary and misdirected depth**|The agent optimizes visible sophistication instead of structural usefulness, such as:<br>- generality (cover a broad but low-utility property),<br>- density of detail (elaborate on aspects that do not constrain the target),<br>- abstraction (analyze an object because it is available, not because it is informative),<br>- technicality instead of architecture,<br>- formalism (accumulate definitions instead of conceptual economy).|**Missing relevance criteria**: depth is requested (e.g. "be rigorous", "provide deep insight") without specifying _what kind of clarity is sought_.<br>**Missing construction strategy**: depth is not tied to a target explanatory question.|
|**Poor motivation for introduced objects**|The agent introduces concepts because they are topically proximate, not because they are _necessary steps_ in a committed construction strategy. It adds generic and decorative prose (e.g. "it is natural to consider…", "to gain intuition…", "this helps understand…").|**Missing functional justification**: motivation is requested only rhetorically and stylistically (e.g. prompts ask for "motivate concepts", "provide intuition", "be pedagogical").|
|**Global incoherence**|The agent optimizes local completeness instead of global coherence, producing:<br>- overlaps,<br>- concepts introduced without clear downstream role,<br>- lack of vault-level novelty.|**No operative model of the vault's established content**: the dependency graph is not encoded explicitly, and the instruction set does not force the agent to map, before writing, which prior outputs are available as inputs. The agent has no strong representation of what is already _established_ versus merely mentioned, and which gap remains open.|
|**Redundancy**|Each unit is generated as if it were semi-autonomous, producing regenerations of established material.|**Missing a rule to counteract the implicit default**: language models are naturally biased toward producing self-contained, polished documents.|
|**Application failures**|Even a strong style guide does not prevent drift in rule application.|**Missing procedural workflows**: the instruction system is too _declarative_; it describes the desired output but _does not prescribe the internal workflow_. The main instructions file mixes:<br>- global style rules,<br>- generative rules,<br>- project architecture,<br>- local unit objective.|
