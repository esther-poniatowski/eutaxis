# Eutaxis — Architectural Proposal: Cross-Agent Configuration Compiler

**Status:** Draft for review
**Supersedes:** the prior proposal for prompt-level component activation
**Date:** 2026-05-21
**Scope:** the activation and delivery architecture for modular agent customization across Claude Code and Codex

---

## 1. Purpose and summary

This document proposes the architecture by which Eutaxis delivers modular, reusable customization to multiple coding agents. It replaces the earlier design, which introduced a portable prompt directive (`@eutaxis rule:... role:...`), a runtime resolver, and agent-specific adapters layered *beneath* a canonical directive syntax.

The revised position is that Eutaxis is a **cross-agent configuration compiler**. A single authoritative source — Markdown fragments together with a declarative manifest — is compiled into the *native* customization artifacts of each target agent. Eutaxis does not introduce a runtime mechanism, a directive language, or a uniform activation protocol. It unifies the *source* of customization and adapts that source to the heterogeneous, non-isomorphic surfaces each agent already provides.

The author of customization defines instructions and desired behaviours once; Eutaxis formats and configures each agent so that those behaviours take effect through mechanisms the agent natively supports. The role of Eutaxis is therefore that of an adapter and synchronizer: it relieves the author of tracking the divergent customization subsystems of each agent.

This proposal extends, rather than discards, the customization already shipped: Eutaxis already generates global and project-local instruction files from modular Markdown sources and YAML configuration. That feature is the prototype of the architecture described here, generalized from one mechanism (instruction files) to the full set of native mechanisms, and from one regime (always-active content) to four.

---

## 2. Why a uniform runtime mechanism is unattainable

The earlier proposal sought a single portable activation mechanism. Examination of the customization surfaces of both agents establishes that no such mechanism exists, and that the only coherent unification point is the source.

### 2.1 Non-isomorphic customization surfaces

The two agents expose overlapping but structurally different subsystems. Output styles in Claude Code are a first-class, system-prompt-level mechanism that *substitutes* the software-engineering role; Codex has no registry counterpart and approximates the same effect with a profile combined with *additive* `developer_instructions`. Profiles, conversely, are a Codex-only construct declared in TOML configuration, with no Claude Code equivalent. Codex rules are a Starlark command-policy layer with no behavioural analogue in Claude Code. Hook event vocabularies differ by an order of magnitude. A component cannot, therefore, be expressed once and installed identically; the target mechanism differs by agent and, for some component classes, has no faithful counterpart.

### 2.2 Absence of per-prompt activation

No agent exposes per-prompt activation. Output styles are fixed at session start and cannot be toggled for a single prompt. Skills load on invocation and persist for the remainder of the session. Profiles are selected at startup. The earlier proposal's per-prompt directive therefore had no native substrate on either target; abandoning it forfeits no capability that the platforms actually provide. The genuine requirement it expressed — on-demand loading that does not inflate always-active context — is met natively by skills, which load only when invoked.

### 2.3 The single convergence point

The agents converge at the level of *source content* and diverge at the level of *delivery mechanism*. The instruction-file layer (`AGENTS.md`, `CLAUDE.md`) already supports modular, cumulative, precedence-ordered composition. Skills, on both agents, follow the Agent Skills open standard and share the `SKILL.md` directory pattern. A uniform source compiled by per-agent adapters is consequently the only design that unifies customization without fighting the platforms.

---

## 3. Design principles

The following principles govern the architecture. Each is a constraint that the prior proposal violated or left implicit.

**P1 — One-way compilation.** The source is authoritative. Generated artifacts are owned by Eutaxis and are never hand-edited. "Synchronization" denotes regeneration together with drift detection, not bidirectional reconciliation. Bidirectional merge is explicitly out of scope, because the generated targets reside in mutable locations that users and the agents themselves modify.

**P2 — Same source, not same behaviour.** Because the mechanisms are non-isomorphic, equivalent behaviour across agents cannot be guaranteed. The compiler assigns each component, per target, an explicit fidelity level and surfaces it. The contract offered to the author is reproducible configuration from one source, not behavioural identity.

**P3 — Activation regime is the classification axis.** What determines the correct native target is not a component's nominal type but *when and how it must be active*. The source declares a regime; the adapter selects the mechanism. This replaces the typed-identifier taxonomy (`rule:`, `role:`, `style:`, `tool:`) of the prior proposal, which embedded a closed taxonomy into syntax.

**P4 — Two source kinds.** The source contains instruction content and capability configuration. The latter — tool, MCP, and permission declarations — is configuration, not instructions, and emitting it writes privilege grants into agent configuration. The two kinds follow separate validation, security, and review paths.

**P5 — Native precedence, not a parallel engine.** Both agents define cumulative global-then-project loading with documented precedence. Eutaxis maps source components onto native scopes and lets the platform resolve precedence. It does not introduce a competing resolution order that could disagree with the platform.

**P6 — Convergence on the Agent Skills open standard.** Where an open standard already unifies a mechanism, Eutaxis passes the artifact through with minimal adaptation rather than re-abstracting it. `SKILL.md` is treated as a near-canonical intermediate form.

**P7 — Golden-file review preserved.** Every generated artifact is a reviewable file. Compilation is deterministic; output is committed and diff-reviewed. This retains the project's established review discipline and is the reason a build-time compiler is preferred over any runtime mechanism.

---

## 4. Architecture

### 4.1 Layered overview

The architecture comprises five layers. Compilation proceeds top to bottom; verification compares the bottom layer against a re-execution of the pipeline.

| Layer | Responsibility |
| ----- | -------------- |
| Source | Markdown fragments and a declarative manifest of components. The single authoritative input. |
| Resolution core | Selection of the effective component set, dependency and conflict resolution, version pinning. Agent-agnostic. |
| Adapter | Per-agent mapping of each component's regime to a native mechanism; production of an artifact plan. |
| Artifact | Concrete generated files written to native locations, under a declared ownership policy. |
| Verification | Drift detection and a per-target fidelity report. |

### 4.2 Source layer

The source consists of reusable Markdown fragments and a manifest. The manifest is the evolution of the existing `agent-instructions.yaml` and of the component registry described in the prior proposal: it enumerates components and records, for each, the metadata required to compile and to resolve. Domain rules continue to reside in the projects that own them (for example `vitruv` and `hermeneia`); Eutaxis consumes those fragments and provides the composition and compilation workflow.

### 4.3 Component model

A component is the unit of customization. It carries, conceptually, the following information. The exact schema is an open question (Section 10).

- **Identifier** — opaque and namespaced (for example `hermeneia/prose-writing`). The nominal type is not encoded in the identifier.
- **Regime** — one of the activation regimes of Section 4.4. This is the property that drives mechanism selection.
- **Scope** — `global` or `project`, mapped to the agent's native global and project layers.
- **Payload** — for instruction components, a fragment or composed set of fragments; for capability components, a declarative configuration record.
- **Metadata** — description, version, and integrity hash. The description is load-bearing where the target mechanism uses it for implicit invocation (skills).
- **Relations** — declared dependencies and conflicts, resolved by the resolution core.
- **Targets** — the set of agents the component compiles to, with optional per-agent overrides and an expected fidelity declaration.

### 4.4 Activation regimes

Four regimes partition the component space. The regime is the canonical axis (P3).

- **Always-on** — content that must be present in context on every turn. Examples: interaction norms, file-authority rules, project conventions.
- **On-demand** — a procedure, checklist, output contract, or reference body that is relevant only to certain tasks and should not consume always-active context until needed.
- **Session-preset** — a role, mode, or communication style fixed for the duration of a session.
- **Capability** — a tool, MCP server, or permission binding. This regime is configuration, not instruction content, and is privilege-granting.

Task-conditional content that the prior proposal would have placed in always-active instruction files belongs in the on-demand regime; this is what allows the always-on instruction file to remain a compact router, consistent with the documented Codex entry-point pattern and its `project_doc_max_bytes` budget.

### 4.5 Compilation pipeline

Compilation is a deterministic function of the source. It proceeds in four stages.

1. **Resolve** — select the effective component set for a requested scope and target set; apply dependencies and conflicts; pin versions. Output: an agent-agnostic resolved set. This is the canonical intermediate representation.
2. **Plan** — for each agent, map every component's regime to a native mechanism and produce an artifact plan: the list of files to be written, their locations, and their intended content.
3. **Render** — produce concrete artifact contents: instruction-file sections, `SKILL.md` directories, output-style files, profile blocks, and configuration fragments.
4. **Emit** — write artifacts to native locations, or, under `check`, diff the planned artifacts against the current on-disk state and report drift.

### 4.6 Adapter layer

An adapter encapsulates everything agent-specific: native file locations, file formats, frontmatter conventions, invocation namespaces, and the regime-to-mechanism mapping. Two adapters are in scope, Claude Code and Codex. The adapter is the central mechanism of this architecture, not a layer subordinate to a canonical syntax. Adding a future agent is the addition of one adapter; the source and the resolution core are unaffected.

### 4.7 Artifact layer and ownership

Generated artifacts are written to the agents' native locations. Each artifact is Eutaxis-owned and is not to be hand-edited (P1). Two ownership models are possible — whole-file ownership, and ownership of a delimited managed region within an otherwise free file. The choice, possibly per file type, is an open question (Section 10). Generated artifacts are committed as golden files to support diff-based review (P7).

### 4.8 Verification layer

The `check` command re-executes the pipeline and compares the result against the on-disk artifacts, reporting any drift. A fidelity report enumerates, per target, the mechanism selected for each component and its fidelity grade, so that approximate compilations are visible before installation.

---

## 5. Mechanism mapping matrix

The matrix below records the proposed regime-to-mechanism mapping and the fidelity expected of each. It is a proposal subject to confirmation (Section 10).

| Regime | Claude Code mechanism | Codex mechanism | Expected fidelity |
| ------ | --------------------- | --------------- | ----------------- |
| Always-on (global) | `~/.claude/CLAUDE.md` | `~/.codex/AGENTS.md` | Exact |
| Always-on (project) | `<project>/CLAUDE.md` | `<project>/AGENTS.md` | Exact |
| On-demand | Skill at `<scope>/.claude/skills/<id>/SKILL.md` | Skill at `<scope>/.agents/skills/<id>/SKILL.md` | Exact (Agent Skills open standard; adapter handles path, frontmatter, and invocation-sigil deltas) |
| Session-preset | Output-style file under `output-styles/`, selected by the `outputStyle` settings key | `[profiles.<id>]` in `config.toml`, carrying `developer_instructions` and related keys | Approximate (Claude Code output styles are substitutive and system-prompt-level; the Codex profile path is additive) |
| Capability | `.mcp.json` and settings permission rules | `[mcp_servers.<id>]`, tool toggles, and rules in `config.toml` / `.codex/rules/` | Exact for MCP server definitions; approximate for permission and command policy |

The asymmetry in the session-preset row is the principal instance of P2: a role component cannot be guaranteed identical behaviour across agents, and the fidelity report must state this.

---

## 6. Command surface

The command surface extends the existing CLI rather than replacing it.

- **`eutaxis generate`** — compile the source and emit artifacts for the configured targets and regimes. Extends the current command from instruction files to all mechanisms.
- **`eutaxis check`** — drift detection across all generated artifacts. Extends the current command.
- **`eutaxis plan`** — a dry run reporting the artifact plan and the diff against the current on-disk state, without writing.
- **`eutaxis explain`** — the fidelity report: per target, the mechanism selected for each component and its fidelity grade.

The resolver command of the prior proposal is retained only as a build-time and diagnostic facility (subsumed by `plan` and `explain`); it is not a runtime activation mechanism.

---

## 7. Security and trust model

The reframing removes the most severe risks of the prior proposal. There is no runtime directive, so directives can no longer be injected through untrusted file content, tool output, or fetched web pages, and there is no on-demand context injection to audit.

Two concerns remain and are addressed by design.

**Capability generation is privilege-granting.** Emitting capability components writes MCP server definitions and permission rules into agent configuration. This path is opt-in per run, its output is diffed and presented for review before any write, and it is never applied silently. Golden-file review is mandatory for capability artifacts.

**Write targets are sensitive.** Artifacts are written into `~/.claude/`, `~/.codex/`, and project configuration files. The ownership policy (Section 4.7) protects any non-Eutaxis content: under whole-file ownership Eutaxis refuses to overwrite a file it does not recognise as its own; under managed-region ownership it writes only within its delimiters. Source components consumed from external rule-owning projects carry version pins and integrity hashes recorded in a lockfile.

---

## 8. Relationship to the current implementation and to the prior proposal

The current `eutaxis generate` and `eutaxis check`, operating on instruction files, are precisely the always-on regime of this architecture for both agents. The proposal generalizes that implementation; it does not invalidate it.

The disposition of the prior proposal's elements is as follows.

| Prior element | Disposition |
| ------------- | ----------- |
| Typed component identifiers (`rule:`, `role:`, ...) | Replaced by opaque namespaced identifiers plus a regime field. |
| Portable prompt directive `@eutaxis ...` | Removed. No runtime directive. |
| Optional structured YAML form | Retained and promoted: it becomes the manifest, the authoritative source, not a prompt directive. |
| Component registry | Retained and extended into the manifest and component model. |
| Resolver command | Retained as a build-time and diagnostic command, not a runtime activation. |
| Agent-specific adapters | Retained and made central: the adapter is the output stage of the compiler. |
| "Slash commands as adapters" | Subsumed: a compiled on-demand component is a skill, and its invocation surface is whatever the agent natively provides. |

---

## 9. Phased implementation

The phasing front-loads the exact-fidelity, highest-value regimes and defers the privilege-granting and unstable surfaces.

**Phase 1 — Always-on and on-demand, both agents.** Compile to instruction-file sections and to `SKILL.md` skills. Both regimes are exact-fidelity. The instruction-file half already exists; the skills half is new and rests on the open standard. Includes `check`, `plan`, and golden-file output. This phase exercises the full pipeline and both adapters on the safest mechanisms.

**Phase 2 — Session-preset.** Compile to output styles and profiles. Introduces the fidelity report, since this regime is approximate.

**Phase 3 — Capability.** Compile to MCP and permission configuration. Introduces the diff-and-review gate of Section 7.

Plugin packaging, hooks, subagents, and Codex rules are deferred (Section 11).

---

## 10. Open questions

The following decisions are deliberately left open and are to be resolved after review of this proposal.

1. **Source schema.** The exact manifest format, the fragment-reference syntax, and the migration path from the existing `agent-instructions.yaml`.
2. **Regime-to-mechanism mapping.** Confirmation of the matrix in Section 5; in particular, whether task-conditional content compiles exclusively to skills or may also compile to router-referenced instruction modules, and how the always-on router text that points to skills is generated.
3. **Ownership policy.** Whole-file ownership versus managed-region ownership for generated instruction files, and whether the choice should differ by file type.
4. **Fidelity policy.** Whether an `unsupported` or `approximate` compilation should fail the build, emit a warning, or be configurable per component.
5. **Identifier and versioning scheme.** Namespacing rules, version-pinning syntax, and the lockfile format.
6. **Scope granularity.** Whether to support directory-level (sub-project) scope, exploiting the Codex root-to-leaf precedence walk and the Claude Code parent-directory skill discovery.
7. **Capability-generation gate.** The exact review and approval workflow preceding any write of privilege-granting configuration.
8. **Packaging.** Whether Eutaxis should additionally emit Claude Code plugin packages, or remain at the loose-file level.

---

## 11. Decisions deferred until agent surfaces stabilize

The following surfaces are either documented as experimental, diverge sharply between agents, or are subject to active evolution. Adapter support for them is deferred until they stabilize; commitment is made only to the stable substrates, namely the instruction-file layer and the Agent Skills open standard.

- Hooks — the event vocabularies of the two agents differ by an order of magnitude and continue to change.
- Codex rules — documented as experimental.
- Subagents — distinct declaration models on each agent.
- Plugin manifests and the Codex optional-metadata file (`agents/openai.yaml`).

---

## 12. Verdict

Eutaxis is repositioned as a cross-agent configuration compiler: a uniform source, per-agent adapters, one-way deterministic generation, declared per-target fidelity, activation-regime-driven mechanism selection, and a separated capability-generation path subject to review. This architecture is incremental with respect to the shipped implementation, eliminates the portability and security failures of the prior proposal, and respects the native customization model of each agent rather than competing with it.
