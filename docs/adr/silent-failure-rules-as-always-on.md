# Silent-failure rules as always-on

## Status

Accepted.

## Context

[activation-regime-as-classification-axis](activation-regime-as-classification-axis.md)
partitions components into four regimes. The always-on and on-demand
regimes map to two structurally distinct mechanisms: always-on
compiles to the main instruction file
(`CLAUDE.md` / `AGENTS.md`), on-demand compiles to skills under
`~/.claude/skills/` and `~/.agents/skills/`.

The activation lifecycle of these two mechanisms is not symmetric.
A skill is loaded only when the model decides the task matches its
`description`. The Agent Skills standard makes this explicit via
progressive disclosure: only the metadata (~100 tokens) is in context
on every turn; the body is loaded on activation. The activation
decision is therefore *prior* to any rule the skill body contains.

This raises a question that the regime partition alone does not
answer: when a rule is **conditionally applicable** (it governs only
certain tasks, not every turn), the temptation is to model it as
on-demand. Two existing patterns embody this temptation:

- **Skill conversion.** Move the rule body into a skill, let the
  model load it when the description matches.
- **Router pointer.** Keep a stub in the always-on file that says
  "when doing X, read `instructions/tasks/X.md`", and let the model
  follow the pointer.

Both reduce to *model-judgment-gated activation*: the rule is in
scope only if the model first recognises that the current task is
the one the rule governs.

This works for some rules and silently fails for others. The
failure mode is asymmetric:

- For a rule whose violation produces a **visibly suboptimal
  artifact** (missing summary table, no contrastive comparison,
  weaker pedagogy), the cost of late activation is a flagged or
  reviewable output. The user can correct it.
- For a rule whose violation produces **silent damage** (wrong-env
  conda install, destructive git operation, scratch file written to
  the repo root, capability widening hidden in a long payload), the
  cost of late activation is irreversible state mutation. By the
  time the model recognises the task category, the violation has
  already shipped.

The router-pointer pattern is the dominant mechanism in the current
oikos `instructions/tasks/` layout and was the starting point for
the session that produced this decision. The proposal to convert
those modules wholesale into skills was reviewed against the
asymmetry above.

## Decision

The placement rule for the always-on regime is refined as follows.

1. **Model-invoked skills carry only safely-deferrable rules.** A
   rule is safely-deferrable when its violation produces a visibly
   suboptimal artifact, not silent damage. Silent-failure-prone
   rules must not be routed to a skill whose activation depends on
   the model recognising the task from metadata alone.
2. **Silent-failure-prone rules stay in `CLAUDE.md` / `AGENTS.md`
   bodies.** Conditional applicability is expressed *inside the
   rule*, as a predicate clause ("applies when installing packages",
   "applies before destructive git operations"). The rule's
   visibility is unconditional even when its triggering condition
   is conditional.
3. **The router-pointer pattern is bounded to content-volume
   reduction inside the always-on file.** A pointer of the form
   "for X, see `<path>`" is acceptable when the *triggering
   predicate and the consequence of missing the rule* are stated
   inline in the always-on file, and the externalised file holds
   only elaboration (examples, rationale, edge cases). A pointer is
   not acceptable as the sole carrier of a silent-failure rule.

The decision criterion is the **silent-failure test**: if the rule
is absent at the moment the model acts, does the resulting failure
become visible at review time, or does it pass review and surface
later as state corruption, security drift, or workflow violation?
Visible at review → safely-deferrable → model-invoked skill
candidate. Surfaces later → silent-failure-prone → always-on body
unless an explicit user invocation loads the rule before the first
irreversible action.

A user-invoked procedure skill can carry silent-failure-prone rules
for its own procedure when activation is explicit and the skill body
is loaded before filesystem, environment, git, external-service, or
permission state can change. In that case the skill body itself
satisfies the visibility requirement. If the rule is needed to decide
whether the skill should be invoked at all, the rule remains
always-on.

The operationalisation of the silent-failure test (how authors
classify a rule unambiguously, how the compiler can check
classifications) is unresolved; see
[open-questions/silent-failure-classification](../open-questions/silent-failure-classification.md).

## Discarded alternatives

- **Convert all routed modules to skills.** Rejected: routes
  silent-failure rules through model-judgment-gated activation,
  defeating the rule. Examples in the oikos set: conda-safety,
  workspace-hygiene, destructive-git-operation guards.
- **Keep the router pattern unchanged for all modules.** Rejected:
  the router itself is model-judgment-gated and exhibits the same
  failure mode as skills for silent-failure rules; it is also less
  efficient than skills for genuinely on-demand content because it
  pollutes every turn with a list of pointers the model rarely
  follows.
- **Carry conditional applicability via a session-preset.**
  Rejected: session-preset is single-active-slot
  ([session-preset-regime](../open-questions/session-preset-regime.md))
  and out-of-band; it cannot scope per-task. A silent-failure rule
  cannot depend on the user having selected the right preset for
  the current task.
- **Add a fifth regime ("conditional-always-on") between always-on
  and on-demand.** Rejected: the four-regime partition is closed by
  the activation lifecycle of the target mechanisms, not by the
  authored content. Conditional applicability is a property of the
  *rule body* (a predicate clause), not of the *regime* (the
  mechanism that carries it). Adding a regime would split the same
  mechanism (always-on file body) into two regime labels with no
  corresponding mechanism difference.

## Rationale

The placement rule preserves the regime partition while adding a
necessary discrimination *within* the always-on regime: not every
always-on rule needs to be unconditionally relevant per turn, but
every always-on rule needs to be unconditionally *visible* to the
model on every turn so that its triggering predicate can fire when
the matching task arrives. Skills cannot provide this guarantee by
design.

The decision keeps three classes of authored content cleanly
separated:

| Class | Placement | Visibility per turn | Activation |
| --- | --- | --- | --- |
| Always-on, unconditional | `CLAUDE.md` / `AGENTS.md` body | Full | Implicit (no gate) |
| Always-on, conditional / silent-failure-prone | `CLAUDE.md` / `AGENTS.md` body, with predicate clause | Full | Predicate inside the rule |
| On-demand, safely-deferrable | Skill `SKILL.md` | Description only | Model-judgment from description |
| User-invoked procedure | Skill `SKILL.md` | Full after explicit invocation | User gate before first irreversible action |

## Consequences

- The router-pointer pattern remains in scope and is endorsed as a
  content-volume reduction tactic, not as an activation mechanism.
  Authors writing routers must keep the triggering predicate
  inline.
- A migration policy is required for the current oikos
  `instructions/tasks/` set: each rule is classified by the
  silent-failure test before any conversion to skills. The
  classification records the activation path and the first
  irreversible action, because explicit user invocation and
  model-judgment activation have different visibility guarantees.
  Rules that are needed before activation stay in the always-on
  body. Rules that govern only the invoked procedure can move with
  that procedure when the skill body loads before the risky action.
- The silent-failure test is currently judgment-based.
  [silent-failure-classification](../open-questions/silent-failure-classification.md)
  tracks the work to operationalise it.
- The always-on regime on the Claude side depends on `CLAUDE.md`
  cumulative-loading behaviour to support modular authoring without
  pre-concatenation;
  [claude-md-cumulative-loading-semantics](../open-questions/claude-md-cumulative-loading-semantics.md)
  tracks the gap in vendor documentation.
- The capability regime is unaffected: capability sources continue
  to follow
  [two-source-kinds-instruction-vs-capability](two-source-kinds-instruction-vs-capability.md)
  and
  [open-questions/capability-regime-split](../open-questions/capability-regime-split.md).
