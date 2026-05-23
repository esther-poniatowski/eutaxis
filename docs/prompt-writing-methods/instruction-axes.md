# Instruction axes and reasoning targets

> [!CHECK] Scope
> This note defines the four orthogonal axes along which authored
> instructions classify, fixes the vocabulary that disambiguates
> rule sets, procedures, and tasks, and resolves the
> reasoning-targets-vs-reasoning-traces question for axes that
> govern model reasoning.

## Premise

A common failure mode in authored instructions is *pollution
between axes*: a request for mathematical analysis silently induces
academic register, and a request for pedagogical style silently
flattens rigor. The pollution is structural — the authored
instruction conflates dimensions that should be specified
independently. A second failure mode is *trace-based instruction
of reasoning models*: prescribing step-by-step action sequences for
work that the receiving model executes internally. This can waste
context and can harm reasoning quality when the prescribed trace
constrains a stronger internal plan.

The decomposition below addresses both failures: four axes that
cannot be silently substituted for each other, and a within-axis
discipline that specifies *what to verify* rather than *how to
proceed*.

## The four axes

Every authored constraint on an agent's work should be classified
by its primary function along one of four axes:

| Axis | What it constrains | Object class | Temporality | Example |
| --- | --- | --- | --- | --- |
| **Reasoning targets** | What the model must check, derive, decompose, or verify | Content of the work | Static (criterion-shaped, not order-shaped) | "verify authoritative sources before stating technical claims"; "decompose the question into sub-questions whose resolution changes the status of the main question" |
| **Output structure** | Shape of the produced artifact | Form of the work | Static | "motivate every concept before introducing it"; "include a summary table for multi-case derivations" |
| **Surface style** | Phrasing of the produced artifact | Wording of the work | Static | tone, register, connectives, verbosity, pronoun discipline |
| **Procedure** | Action sequence with externally observable state effects | Trajectory of actions | Temporal (action-graph-shaped) | "stage changes → review diff → commit"; "scaffold module → write failing tests → implement → verify" |

The four-way cut is intended to be orthogonal: the same
**procedure** is compatible with any combination of reasoning
targets, output structure, and surface style. The same
**reasoning targets** apply identically across pedagogical
expositions, formal proofs, and code comments. The same
**surface style** can drape over rigorous and informal work alike.

The keyword *action graph* is reserved for the procedure axis: a
procedure constrains an action graph — an ordered set of state
mutations with declared dependencies — not an inner reasoning
trace. This distinction is load-bearing for the procedure axis's
applicability conditions, addressed below.

## Vocabulary

The current oikos `instructions/tasks/` layout names its rule
sets "tasks," which collides with the runtime sense of *task* (a
user-issued instance of work). The vocabulary is hereby fixed:

| Term | Refers to | Example |
| --- | --- | --- |
| **Rule** | A single authored constraint along one of the four axes | "Motivate every concept before introducing it." |
| **Rule set** | A coherent group of rules addressing one aspect of behaviour | The set of rules that collectively shape conceptual reasoning. |
| **Procedure** (or **workflow**) | An action graph along the procedure axis | The git-commit-splitting workflow. Named for the trajectory it constrains. |
| **Task** | A runtime invocation — what the user asked the agent to do in this session | "Refactor this module so the registry no longer holds mutable state." |

The directory currently named `instructions/tasks/` is therefore
better named `instructions/rules/` (or `instructions/rule-sets/`),
with procedures living in a parallel `instructions/procedures/`
location if and when they are authored. The current contents are
predominantly rule sets, not procedures — they specify quality
criteria the artifact must satisfy, not action sequences the
agent must traverse.

## Within-axis discipline: reasoning targets, not reasoning traces

The reasoning-targets axis carries the gravest authoring risk.
The default authorial mode — describe what the model should *do*
in what order — produces *reasoning-trace* rules. For native
reasoning models (Claude with extended thinking, OpenAI o-series),
externalised trace prescriptions are usually redundant when the
internal reasoning already explores the space, and they can be
harmful when the prescribed trace overrides better internal
organisation.
The cross-agent compiler's substrate
([reasoning-process.md](reasoning-process.md)) records the same
observation from the prompt-engineering literature.

The discipline is to specify, instead, *what the answer must
satisfy* — verification conditions, decomposition targets,
verifiable success criteria, declared assumptions, edge cases the
answer must cover, and the output contract the artifact must
meet. The model executes whatever trace its internal reasoning
selects; the rules judge the artifact, not the trace.

Five canonical sub-shapes of a reasoning-target rule:

1. **Success criteria** — properties the final answer must
   exhibit (e.g. "the answer specifies its answer-form and the
   scope under which it holds").
2. **Subproblems to decompose** — sub-questions or
   sub-claims the work must address (e.g. "the analysis
   distinguishes the conceptual, formal, and evidential
   conditions of answerability").
3. **Assumptions and edge cases to check** — situations the
   answer must explicitly handle (e.g. "the argument states
   whether each assumption is necessary, sufficient, or both").
4. **Verification conditions** — falsifiable tests the answer
   must pass (e.g. "every cited claim has an identifiable source
   on a trusted platform, or is explicitly flagged as
   unsourced").
5. **Output contract** — required artifact components and
   their structural relations (e.g. "the dependency register
   lists, for each sub-question: type, dependencies, effect on
   the main question").

A reasoning-target rule that obeys this discipline names the
property the answer must hold and the means by which the property
can be checked, and stops there. It does not name the order in
which the model should consider the property, nor the inner
reasoning steps the model should write down.

## Worked example: encoding the gnomon question-hierarchy framework

The [gnomon question-hierarchy
framework](/Users/eresther/Documents/work/research/geonexus/vendor/gnomon/docs/references-methods/question-hierarchy-framework.md)
is a methodology for decomposing a research question into
sub-questions. Its surface form is procedural: five numbered
steps, each with sub-operations, plus a revision protocol and a
failure-mode catalogue. Encoded naively, it would become a
trace-based instruction ("Step 1: do X. Step 2: do Y. ...") and
could harm reasoning-model performance.

The right encoding treats the framework as a *family of
reasoning-target rules*. The methodology is preserved; the
ordering is not prescribed.

### Naïve trace-based encoding (rejected)

```text
When given a research question:
  Step 1. Write down the answer-form and scope.
  Step 2. List the missing conditions of answerability.
  Step 3. For each missing condition, write a sub-question.
  Step 4. Classify each sub-question as analytic, abductive, or constructive.
  Step 5. Filter sub-questions by necessary / useful / decorative.
  Step 6. Rank retained sub-questions by diagnostic power, feasibility, centrality.
  Step 7. Build the dependency register table.
  Step 8. Work on the highest-priority sub-question.
  ...
```

This encoding fails along two dimensions:

- A reasoning model interleaves the operations naturally (it
  ranks while filtering, revises the register while classifying).
  Imposing the order constrains without benefit.
- The model spends context budget restating the trace rather than
  applying the methodology to the actual question.

### Reasoning-target encoding (adopted)

The framework restructured as reasoning-target rules, grouped by
sub-shape:

**Success criteria** (R1)

> A satisfactory decomposition of the target question must
> specify, for the main question: (a) its answer-form — theorem,
> formal criterion, definition, mechanism, taxonomy,
> counter-example, predictive framework, or discriminating
> comparison; (b) its scope — object class, regime, abstraction
> level, admissible evidence; (c) the conditions of answerability
> under that scope.
>
> *Operational check:* the final artifact contains an explicit
> answer-form line, an explicit scope line, and an enumeration
> of currently satisfied vs missing conditions of answerability.

**Subproblems the work must address** (R2)

> The decomposition must convert each missing condition of
> answerability into one or more candidate sub-questions, drawn
> from the condition-type taxonomy: conceptual, formal,
> evidential, identifiability, feasibility, interpretability.
> Conditions that do not surface a sub-question are stated
> explicitly as "currently satisfied" with the warrant.

**Admissibility of each sub-question** (R3)

> A sub-question is admissible only if its resolution would
> change the status of the main question — by reducing the set
> of admissible answers, forcing a reformulation, or making a
> previously indistinguishable distinction visible.
>
> *Operational check:* each sub-question carries a one-line
> "effect on main question" statement; sub-questions whose
> statement is materially empty are removed before further
> consideration.

**Functional type of each sub-question** (R4)

> Each sub-question is one of: *analytic* (removes a planning-time
> obstacle, unconditional validity), *abductive* (responds to a
> resistance encountered in inquiry, validity conditioned on a
> structural hypothesis $H_R$), or *constructive* (expands the
> conceptual vocabulary; downstream sub-questions are
> semantically undefined until this one resolves).
>
> *Verification:* abductive sub-questions carry the explicit
> conditioning hypothesis; constructive sub-questions are marked
> as vocabulary-expanding; analytic sub-questions carry no
> condition.

**Filtering criterion** (R5)

> Each candidate sub-question is assigned exactly one status:
> *necessary* (without it, the main question becomes impossible,
> invalid, or uninterpretable), *useful* (improves robustness,
> scope, or explanatory force), or *decorative* (resolution does
> not materially affect the main answer). Decorative
> sub-questions are removed.

**Prioritisation criterion** (R6)

> Retained sub-questions are ranked along three properties:
> *diagnostic power* (how sharply the resolution would constrain
> the admissible answers), *feasibility* (whether progress is
> possible now with available tools), *structural centrality*
> (whether the sub-question concerns a load-bearing assumption).
> The selected next sub-question is the one whose least
> favourable plausible answer would still eliminate a substantial
> portion of the currently live possibilities.

**Revision triggers** (R7)

> The decomposition is revised locally when any of the following
> appear: derivational impasse, empirical or formal anomaly,
> conceptual tension, interpretive ambiguity, counter-example.
> The revision records the resistance, names what is missing,
> false, or misaligned, formulates a repair sub-question
> (abductive under hypothesis $H_R$, or constructive if the
> resistance signals vocabulary insufficiency), and invalidates
> every sub-question conditioned on a hypothesis the resistance
> refutes.

**Failure-mode avoidance** (R8)

> The decomposition must not exhibit any of: thematic
> decomposition (mirroring literature instead of epistemic
> obstacles), workflow decomposition (stages instead of
> obstacles), tool-availability decomposition (what can be done
> instead of what must be known), equal-footing treatment (no
> dependency structure surfaces), premature validation (testing
> before concepts are clarified), vocabulary inertia (preserving
> a conceptual language that cannot express the needed
> distinctions), absence of falsifying leverage, or silently
> unconditional failure-induced sub-questions.

**Output contract** (R9)

> The final artifact includes a dependency register in which
> each sub-question carries: type, dependencies, effect on the
> main question, status, priority, conditioned-on (for
> abductive and constructive sub-questions). The main question
> is restated if revised; the relation between $Q$ and any $Q'$
> is stated.

### What the restructuring preserved and what it changed

The methodology's content is preserved one-to-one: every
operation in gnomon's prose corresponds to a rule above. The
condition-type taxonomy (R2), the admissibility criterion (R3),
the type classification (R4), the filtering tests (R5), the
prioritisation triad (R6), the revision protocol (R7), the
failure-mode catalogue (R8), and the dependency-register
artifact (R9) all appear without loss.

The restructuring changes three things:

1. **Order disappears.** R1 through R9 are not "steps" — they
   are properties the decomposition must hold. The model
   can satisfy them in whatever order its reasoning selects;
   nothing in the rules prescribes a trace.
2. **Each rule is testable independently.** A reviewer (human
   or model) can pick any rule and check the artifact against
   it. The "operational check" lines are falsifiers, not stages.
3. **Failure-mode avoidance becomes a constraint, not a
   warning.** R8 lifts gnomon's "methodological failure modes"
   table from descriptive prose to an explicit prohibition that
   the decomposition must not match any of the listed patterns.

The encoding is the canonical pattern for converting any
methodology — a research framework, an audit procedure, a review
protocol — into reasoning-target rules without sacrificing its
content.

## When the procedure axis actually applies

The procedure axis is not redundant. It applies when the
authored constraint governs an *action graph with externally
observable state effects* — situations where the order of
*actions* (not the order of *reasoning*) is load-bearing.

Canonical procedure-axis cases:

- **Git workflows.** "Stage changes → review the staged diff →
  commit → push" is a procedure: each step mutates external
  state (the index, the working tree, the remote), and the
  ordering constrains what subsequent steps can observe.
- **Tool-use sequences with environment side effects.**
  "Activate the project environment → install the dependency →
  run the test suite" is a procedure: the second action's
  outcome depends on the first having completed.
- **Multi-agent handoffs.** "Producer agent emits artifact →
  consumer agent reads artifact → consumer agent produces
  derived artifact" is a procedure: the trajectory of the
  artifact across agents is the constraint.

What the procedure axis is **not** for:

- An internal reasoning chain that the receiving model executes
  in its head. "First state the assumptions, then derive the
  consequence, then check the edge cases" is a reasoning-target
  rule masquerading as a procedure. It should be reauthored as
  three reasoning-target rules: an assumption-stating rule, a
  derivation rule, an edge-case rule. Each judges the artifact,
  none constrains the trace.

The test for procedure-axis applicability: *does the rule
constrain an action graph that an external observer could
record by inspecting state changes, independently of the
model's reasoning trace?* If yes, procedure. If no,
reasoning-target.

## Composition implications

The four-axis cut shapes how composable skills are assembled:

- A skill typically combines one **rule set** with possibly one
  **procedure**. The two are orthogonal artifacts.
- Surface-style rules and reasoning-target rules belong to
  different rule sets; a skill that targets pedagogical
  exposition combines a reasoning-target rule set with a
  pedagogical surface-style rule set, and the two coexist
  without pollution.
- Procedures are emitted only when the action-graph test passes;
  otherwise the same content is authored as reasoning targets.

Compositional selection ("include rule set A + rule X from set B,
minus rule Y from set A, plus procedure P") inherits the open
question on intra-artifact composition
([intra-artifact-composition](../open-questions/intra-artifact-composition.md))
and on identifier algebra
([identifier-and-namespace-algebra](../open-questions/identifier-and-namespace-algebra.md)).
The four-axis cut is the source-side classification that
composition operates over.

---

> [!LINKS] Related
> [reasoning-process](reasoning-process.md) — within-trace
> reasoning specification and the model-class taxonomy.
> [style-tone](style-tone.md) — the surface-style axis in detail.
> [output-formatting](output-formatting.md) — the
> output-structure axis in detail.
> [Four-axis instruction decomposition (ADR)](../adr/four-axis-instruction-decomposition.md)
> — the formal decision and discarded alternatives.
