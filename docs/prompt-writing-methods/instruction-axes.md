---
tags: []
aliases:
  - Instruction axes and reasoning targets
index: "[Prompt writing methods](_index.md)"
---

# Instruction axes and reasoning targets

> [!CHECK] Scope
> This note defines the three orthogonal axes along which authored
> rules classify, distinguishes procedures as a separate declaration kind, fixes the vocabulary that disambiguates
> rule sets, procedures, and tasks, and resolves the
> reasoning-targets-vs-reasoning-traces question for axes that
> govern model reasoning.

## Premise

A common failure mode in authored instructions is *pollution between axes*: a request for mathematical analysis silently induces academic register, and a request for pedagogical style silently flattens rigor. The pollution is structural — the authored instruction conflates dimensions that should be specified independently. A second failure mode is *trace-based instruction of reasoning models*: prescribing step-by-step action sequences for work that the receiving model executes internally. This can waste context and can harm reasoning quality when the prescribed trace constrains a stronger internal plan.

The decomposition below addresses both failures: three rule axes that cannot be silently substituted for each other, a separate procedure contract, and a within-axis discipline that specifies *what to verify* rather than *how to proceed*.

## The three rule axes

Every authored rule is classified by its primary function along one of three axes:

| Axis | What it constrains | Object class | Temporality | Example |
| --- | --- | --- | --- | --- |
| **Reasoning targets** | What the model must check, derive, decompose, or verify | Content of the work | Static (criterion-shaped, not order-shaped) | "verify authoritative sources before stating technical claims"; "decompose the question into sub-questions whose resolution changes the status of the main question" |
| **Output structure** | Shape of the produced artifact | Form of the work | Static | "motivate every concept before introducing it"; "include a summary table for multi-case derivations" |
| **Surface style** | Phrasing of the produced artifact | Wording of the work | Static | tone, register, connectives, verbosity, pronoun discipline |

The three-way cut is orthogonal. The same reasoning targets apply across pedagogical expositions, formal proofs, and code comments. The same surface style may govern outputs with different reasoning targets and structures.

A procedure is not a rule axis. It is a separate declaration kind with an externally observable action graph, preconditions, effects, invariants, and postconditions. This distinction prevents an action contract from being validated as though it were an artifact criterion.

## Vocabulary

The current oikos `instructions/tasks/` layout names its rule sets "tasks," which collides with the runtime sense of *task* (a user-issued instance of work). The vocabulary is hereby fixed:

| Term | Refers to | Example |
| --- | --- | --- |
| **Rule** | A single authored constraint along one of the three axes | "Motivate every concept before introducing it." |
| **Rule set** | A coherent group of rules addressing one aspect of behaviour | The set of rules that collectively shape conceptual reasoning. |
| **Procedure** (or **workflow**) | A separate declaration whose finite action graph has externally observable effects | The git-commit-splitting workflow. Named for the trajectory it constrains. |
| **Task** | A runtime invocation — what the user asked the agent to do in this session | "Refactor this module so the registry no longer holds mutable state." |

The directory currently named `instructions/tasks/` is therefore better named `instructions/rules/` (or `instructions/rule-sets/`), with procedures living in a parallel `instructions/procedures/` location if and when they are authored. The current contents are predominantly rule sets, not procedures — they specify quality criteria the artifact must satisfy, not action sequences the agent must traverse.

## Within-axis discipline: reasoning targets, not reasoning traces

The reasoning-targets axis carries the gravest authoring risk. The default authorial mode — describing what the model should *do* in what order — produces *reasoning-trace* rules. For native reasoning models (Claude with extended thinking, OpenAI o-series), externalised trace prescriptions are usually redundant when the internal reasoning already explores the space, and they can be harmful when the prescribed trace overrides better internal organisation. The cross-agent compiler's substrate ([reasoning-process.md](reasoning-process.md)) records the same observation from the prompt-engineering literature.

The discipline is to specify, instead, *what the answer must establish* — verification conditions, decomposition targets, success criteria, declared assumptions, and edge cases. The model executes whatever trace its internal reasoning selects; the rules judge the artifact, not the trace. Required components and their arrangement belong to the output-structure axis.

Four canonical sub-shapes of a reasoning-target rule:

1. **Success criteria** — properties the final answer must exhibit (e.g. "the answer specifies its answer-form and the scope under which it holds").
2. **Subproblems to decompose** — sub-questions or sub-claims the work must address (e.g. "the analysis distinguishes the conceptual, formal, and evidential conditions of answerability").
3. **Assumptions and edge cases to check** — situations the answer must explicitly handle (e.g. "the argument states whether each assumption is necessary, sufficient, or both").
4. **Verification conditions** — falsifiable tests the answer must pass (e.g. "every cited claim has an identifiable source on a trusted platform, or is explicitly flagged as unsourced").

A reasoning-target rule that obeys this discipline names the property the answer must hold and the means by which the property can be checked, and stops there. It does not name the order in which the model should consider the property, nor the inner reasoning steps the model should write down.

## Worked example: encoding the gnomon question-hierarchy framework

The Gnomon question-hierarchy framework from the external Gnomon project is a methodology for decomposing a research question into sub-questions. Its surface form is procedural: five numbered steps, each with sub-operations, plus a revision protocol and a failure-mode catalogue. Encoded naively, it would become a trace-based instruction ("Step 1: do X. Step 2: do Y. ...") and could harm reasoning-model performance.

The right encoding treats the framework as a family of reasoning-target rules plus one output-structure rule. The methodology is preserved; the ordering is not prescribed.

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

- A reasoning model interleaves the operations naturally (it ranks while filtering, revises the register while classifying). Imposing the order constrains without benefit.
- The model spends context budget restating the trace rather than applying the methodology to the actual question.

### Reasoning-target encoding (adopted)

The framework restructured as reasoning-target rules, grouped by sub-shape:

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

**Output structure** (S1)

> The final artifact includes a dependency register in which
> each sub-question carries: type, dependencies, effect on the
> main question, status, priority, conditioned-on (for
> abductive and constructive sub-questions). The main question
> is restated if revised; the relation between $Q$ and any $Q'$
> is stated.

### What the restructuring preserved and what it changed

The methodology's content is preserved one-to-one: every operation in Gnomon's prose corresponds to a rule above. The condition-type taxonomy (R2), admissibility criterion (R3), type classification (R4), filtering tests (R5), prioritisation triad (R6), revision protocol (R7), failure-mode catalogue (R8), and dependency-register structure (S1) all appear without loss.

The restructuring changes three things:

1. **Order disappears.** R1 through R8 and S1 are not steps. The model can satisfy them in whatever order its reasoning selects; nothing in the declarations prescribes a trace.
2. **Each rule is testable independently.** A reviewer (human or model) can pick any rule and check the artifact against it. The "operational check" lines are falsifiers, not stages.
3. **Failure-mode avoidance becomes a constraint, not a warning.** R8 lifts gnomon's "methodological failure modes" table from descriptive prose to an explicit prohibition that the decomposition must not match any of the listed patterns.

The encoding is the canonical pattern for converting a methodology into the rule axes that its acceptance conditions require, without turning its internal reasoning into a procedure.

## When the procedure kind applies

A procedure applies when the authored contract governs an *action graph with externally observable state effects* — situations where the order of *actions* rather than the order of internal reasoning is load-bearing.

Canonical procedure cases:

- **Git workflows.** "Stage changes → review the staged diff → commit → push" is a procedure: each step mutates external state (the index, the working tree, the remote), and the ordering constrains what subsequent steps can observe.
- **Tool-use sequences with environment side effects.** "Activate the project environment → install the dependency → run the test suite" is a procedure: the second action's outcome depends on the first having completed.
- **Multi-agent handoffs.** "Producer agent emits artifact → consumer agent reads artifact → consumer agent produces derived artifact" is a procedure: the trajectory of the artifact across agents is the constraint.

What the procedure kind is **not** for:

- An internal reasoning chain that the receiving model executes in its head. "First state the assumptions, then derive the consequence, then check the edge cases" is a reasoning-target rule masquerading as a procedure. It should be reauthored as three reasoning-target rules: an assumption-stating rule, a derivation rule, an edge-case rule. Each judges the artifact, none constrains the trace.

The classification test is: *does the declaration constrain an action graph that an external observer could record by inspecting state changes independently of the model's reasoning trace?* If yes, it is a procedure. If no, it may be a reasoning-target rule.

## Composition implications

The three rule axes and separate procedure kind shape how composable skills are assembled:

- A skill typically combines one **rule set** with possibly one **procedure**. The two are orthogonal artifacts.
- Surface-style rules and reasoning-target rules belong to different rule sets; a skill that targets pedagogical exposition combines a reasoning-target rule set with a pedagogical surface-style rule set, and the two coexist without pollution.
- Procedures are emitted only when the action-graph test passes. Other content is classified by the property it governs: reasoning target, output structure, or surface style.

Compositional selection ("include rule set A + rule X from set B, minus rule Y from set A, plus procedure P") follows [three-layer composition and precedence](../adr/three-layer-composition-and-precedence.md) and still depends on the open identifier algebra. The three-axis classification applies only to rules; procedure is selected by declaration kind.

---

> [!LINKS] Related
> [reasoning-process](reasoning-process.md) — within-trace
> reasoning specification and the model-class taxonomy.
> [style-tone](style-tone.md) — the surface-style axis in detail.
> [output-formatting](output-formatting.md) — the
> output-structure axis in detail.
> [Three rule axes and the procedure kind](../adr/three-rule-axes-and-procedure-kind.md)
> — the formal decision and discarded alternatives.
