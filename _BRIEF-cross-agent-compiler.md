# Review Brief — Adversarial Assessment of the Eutaxis Cross-Agent Configuration Compiler Proposal

*This document is a self-contained brief to be handed to a separate reviewing agent. It may be used as-is. The reviewing agent is expected to have read access to the referenced files; if it does not, the inline summary below is sufficient to begin.*

---

## Role

An independent adversarial architecture reviewer, with no involvement in authoring the proposal under review and no stake in its acceptance.

## Task

Assess the architectural soundness of the Eutaxis "cross-agent configuration compiler" proposal. Identify weaknesses, hidden assumptions, portability failures, semantic gaps, security risks, and implementation traps. Do not rewrite the proposal except where a recommended correction cannot be stated otherwise. The objective is a judgement on whether the architecture is sound, not a redraft.

## Background

Eutaxis builds structured agent instructions from reusable Markdown fragments. It currently generates global and project-local instruction files from modular sources and YAML configuration.

A prior proposal introduced a runtime prompt directive (`@eutaxis rule:... role:...`), a component registry, a resolver command, and agent-specific adapters layered beneath that directive. An adversarial audit judged the runtime directive unsound: portable as a string but not as behaviour, dependent on a non-portable interpreter, using a sigil (`@`) that collides with file-reference preprocessing in both target clients, and performing runtime context injection at odds with the project's golden-file review discipline.

In response, the proposal was reframed. The new proposal — the subject of this review — repositions Eutaxis as a build-time compiler. This review must not re-litigate the prior proposal; it must assess the new one on its own terms, including whether the reframing introduced new defects.

## Materials

Primary, to be read in full:
- `/Users/eresther/Documents/work/projects/eutaxis/PROPOSAL-cross-agent-compiler.md` — the proposal under review.

Supporting:
- `/Users/eresther/Documents/work/projects/eutaxis/README.md` — the Eutaxis goal and current feature state.
- `/Users/eresther/Documents/work/techne/tutorials/ai-agents/` — technical notes on the Codex and Claude Code customization mechanisms on which the proposal relies (notably `customization-mechanisms.md`, `claude-output-styles.md`, `codex-profiles.md`, `claude-skills.md`, `codex-skills.md`, `codex-agents-loading-precedence.md`).

If the primary file cannot be read, proceed from the inline summary below and state the limitation in the report.

## Inline summary of the proposal

The proposal repositions Eutaxis from an inventor of a runtime activation protocol to a **cross-agent configuration compiler**. A single authoritative source — Markdown fragments plus a declarative manifest — is compiled into the native customization artifacts of Claude Code and Codex. There is no runtime directive and no uniform activation protocol; the agents are held to converge at the level of source content and to diverge at the level of delivery mechanism.

The architecture has **five layers**: source (fragments and manifest); resolution core (agent-agnostic selection, dependency and conflict resolution, version pinning); adapter (per-agent mapping of each component to a native mechanism, producing an artifact plan); artifact (generated files written to native locations under an ownership policy); and verification (drift detection and a fidelity report).

**Seven principles** govern it: one-way compilation; "same source, not same behaviour", with an explicit per-target fidelity grade; activation regime as the classification axis; two source kinds, namely instruction content and capability configuration; reliance on native precedence rather than a parallel resolution engine; convergence on the Agent Skills open standard; and preservation of golden-file review.

**Four activation regimes** drive mechanism selection. Always-on compiles to `CLAUDE.md` / `AGENTS.md` sections (claimed exact fidelity). On-demand compiles to `SKILL.md` skills on both agents (claimed exact). Session-preset compiles to a Claude Code output style and a Codex profile with `developer_instructions` (claimed approximate). Capability compiles to MCP and permission configuration (claimed exact for MCP server definitions, approximate for permission and command policy).

The command surface extends the existing CLI with `generate`, `check`, `plan`, and `explain`. The security model asserts that runtime injection is eliminated and that capability generation is opt-in, diffed, and reviewed before any write. Implementation is phased: always-on and on-demand first, then session-preset, then capability. Section 10 lists eight deliberately open questions (source schema, the mapping matrix, ownership policy, fidelity policy, identifiers and versioning, scope granularity, the capability-generation gate, packaging). Section 11 defers hooks, Codex rules, subagents, and plugin manifests until those surfaces stabilize.

## Required independent verification

The architecture rests on factual claims about the native customization mechanisms of Codex and Claude Code. Verify the load-bearing claims against current official documentation — `https://developers.openai.com/codex` and `https://code.claude.com/docs` — and against the supporting technical notes. Flag any claim that is stale, imprecise, or incorrect, and flag any discrepancy between the notes and the official documentation.

Claims to verify include, at minimum:
- output styles are a substitutive, system-prompt-level, session-scoped, file-based mechanism in Claude Code, and Codex has no registry equivalent;
- Codex profiles are TOML configuration presets, and `developer_instructions` is additive;
- skills on both agents follow the Agent Skills open standard and share the `SKILL.md` directory pattern, with documented differences in storage paths, frontmatter, invocation, and implicit-invocation controls;
- `AGENTS.md` and `CLAUDE.md` use cumulative global-then-project loading with documented precedence, and Codex enforces a `project_doc_max_bytes` limit;
- the locations of MCP configuration on each agent;
- Codex custom prompts are deprecated and Claude Code custom commands have been merged into skills.

A claim shown to be false invalidates the part of the architecture that depends on it. Report the dependency explicitly. If web access is unavailable, state which claims could not be verified.

## Questions to answer

1. Is the four-regime taxonomy (always-on, on-demand, session-preset, capability) complete, mutually exclusive, and the correct classification axis? Are there realistic components that span regimes or fail to fit?
2. Is the fidelity contract (exact / approximate / unsupported) operationalizable? How is fidelity to be measured or validated rather than merely declared, and by whom?
3. Within a single regime and scope, multiple components compile into one artifact — one `CLAUDE.md`, one output style, one profile. How does the proposal handle intra-artifact composition, ordering, and conflict? Is the "native precedence" principle sufficient, given it addresses only cross-scope layering?
4. Is the claim of exact fidelity for the on-demand regime justified, given the documented differences between the two skill systems in storage paths, frontmatter conventions, invocation syntax, and implicit-invocation control?
5. The session-preset regime maps a role or style to a Claude Code output style and to a Codex profile. A Codex profile bundles model, reasoning-effort, and sandbox configuration, and only one profile is active per session; an output style is activated by a settings key. Can Eutaxis configure an agent to *respect* a session-preset component, or only make it available for manual selection? Is the regime mismodeled?
6. The capability regime compiles to permission and command-policy configuration, graded approximate. Is an approximate security boundary acceptable? Should MCP server definitions be separated from permission and policy, and should policy be compiled at all?
7. The ownership policy for generated instruction files is deferred to an open question. Whole-file versus managed-region ownership determines whether Eutaxis can coexist with hand-written `CLAUDE.md` and `AGENTS.md` content. Is it sound to defer a decision the architecture structurally depends on, and is the boundary between Eutaxis-owned artifacts and agent- or user-owned content drawn correctly and completely?
8. The proposal narrows "synchronizer" to regeneration plus drift detection, invoked as a manual command. How does drift accumulate between runs, and is a manual compiler sufficient for the stated goal of keeping multiple agents consistent?
9. Source components may originate in separate rule-owning repositories. How are cross-repository source components acquired, versioned, and pinned, and is this adequately addressed?
10. Golden-file review captures the generated artifact, not the behaviour it induces. The README references behavioural testing and profile-based validation; the proposal contains no behavioural validation loop. Is artifact-level review sufficient to support a claim of correctness?
11. Does the reframing improve the net security posture? The runtime-injection vector is removed, but a write-side surface (writing to `~/.claude/`, `~/.codex/`, and configuration files) and a supply-chain surface (consuming external fragments) are introduced. Weigh these against each other.
12. The architecture is pinned to the current customization surfaces of two fast-moving agents. Section 11 defers the surfaces presumed unstable, but the mapping matrix depends on surfaces presumed stable. What is the strategy when a surface presumed stable changes? Separately, does Section 11 defer the right things — in particular, is deferring subagents defensible, given that subagents are a native role-isolation mechanism while the proposal routes roles to output styles and profiles?

## Output format

Produce the report in the following order.

1. **Objections, ordered by severity, strongest first.** For each objection state: the problematic assumption; the failure mode it produces; and the recommended correction.
2. **Verification findings.** For each load-bearing platform claim, state whether it was confirmed, found imprecise, or found incorrect, and identify the architectural component that depends on it.
3. **What the proposal gets right.**
4. **Assessment of the open questions and deferrals.** Judge whether deferring each Section 10 item is safe, whether any decision the architecture structurally depends on was wrongly deferred, and whether the Section 11 deferrals are correctly chosen.
5. **Verdict.** Exactly one of: accept as-is; accept with modifications; reject and redesign.

## Constraints

- The items in Section 10 of the proposal are deliberately open. Do not treat them as defects merely for being unspecified; assess instead whether deferring each is safe.
- Order objections strictly by severity. An objection that threatens architectural soundness outranks one that concerns implementation detail.
- Ground every objection in a specific claim, principle, or section of the proposal.
- Conclude with exactly one verdict, stated unambiguously.
