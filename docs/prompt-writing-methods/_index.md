# Prompt writing methods

Designing agent instructions (prompts) is a discipline with well-characterized failure modes and evidence-informed practices. Empirical support varies by model family, task, and deployment surface. Stable design principles span structural architecture, linguistic form, and behavioral specification.

> [!WARNING] Design-time artifact
> This note is a **design-time reference** used when authoring the `governance/` files (rules, specs, contracts, audits, workflow). Agents do not load it during note production. The deployed system's agent instructions are the `governance/` files themselves; this note informs their design but is not part of the runtime instruction surface.

> [!CHECK] Scope
> This note addresses the **main instruction file** (system prompt) that orchestrates or launches a task — the text that defines the agent's role, constraints, reasoning schema, and output requirements. The treatment assumes a **single-turn, single-agent** system prompt as the baseline. Multi-agent considerations (controller/subagent consistency, handoff protocols, state serialization across turns) appear where they affect instruction-file design, but the architecture of multi-agent orchestration is not covered in full. Similarly, for agentic systems the instruction file is only one component of a broader control surface that also includes external artifacts (tool descriptions, structured output schemas, governance files); these appear where they interact with the instruction file, but their internal design is not covered.

## Foundational principles

The central challenge is the **specification-behavior gap**: the model infers operational intent from natural language, introducing ambiguity at every underspecified node. Effective instructions reduce this gap through precision, completeness, and internal consistency.

Three meta-principles govern all decisions:

- **Reducing interpretive degrees of freedom.** Each instruction should minimize the number of valid parses. Ambiguous clauses produce stochastic behavior — the model samples from a distribution over interpretations. The target is to reduce this distribution's entropy as far as possible, not to eliminate it entirely (natural language cannot guarantee a single parse).
- **Separating concerns.** Role, task, constraints, output format, and edge-case handling are orthogonal dimensions. Conflating them produces coupling: changing one accidentally alters the other. Instructions should decompose cleanly along these axes.
- **Falsifiable compliance.** An instruction the model cannot check against its own output is harder to enforce and easier to satisfy only superficially. Every behavioral directive should be testable against the model's own output at inference time when the directive concerns the output artifact.

> [!WARNING]
> Prompt design depends on the **model-family**. A prompt that works well for a reasoning model may be suboptimal for a lower-latency execution model.

- [Structure of prompts](structure-prompts.md)
- [Section demarcation](section-demarcation.md)
- [Linguistic form](linguistic-form.md)
- [Examples valid/invalid](examples-valid-invalid.md)
- [Token budget](token-budget.md)
- [Iterative refinement](iterative-refinement.md)
- [Multi-agent and multi-turn extensions](multi-agent-multi-turn.md)
- [Instruction axes and reasoning targets](instruction-axes.md)

