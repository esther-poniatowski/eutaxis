# Convergence on the Agent Skills open standard

## Status

Accepted.

## Context

The on-demand activation regime ([activation-regime-as-classification-axis](activation-regime-as-classification-axis.md)) must compile to a native mechanism on each target agent. Both Claude Code and Codex independently adopt the **Agent Skills** open standard: a directory containing `SKILL.md` (YAML frontmatter plus Markdown body), optional supporting files, and a progressive-disclosure load model. The standard is asserted by each vendor's documentation rather than by a neutral standards body, but the convergence is sufficient that the two agents already accept the same minimal artifact.

A cross-agent compiler facing this convergence has a choice: pass the artifact through with minimal adaptation, or re-abstract it into a Eutaxis intermediate form and re-render per agent. Re-abstraction would let Eutaxis express agent-specific elaborations in a uniform language; passthrough binds Eutaxis to the standard's surface.

## Decision

Eutaxis **converges on the Agent Skills open standard** as the canonical intermediate form for on-demand artifacts. The source layer expresses an on-demand component as a near-canonical `SKILL.md` fragment plus declarative metadata; the adapter writes a directory that is itself a valid Agent Skill.

Each adapter is permitted to elaborate the artifact with its agent-specific surface where the standard is silent:

- The Claude adapter writes `disable-model-invocation`, `allowed-tools`, `argument-hint`, and other documented Claude frontmatter fields directly into `SKILL.md`.
- The Codex adapter writes a sibling `agents/openai.yaml` carrying UI metadata, `policy.allow_implicit_invocation`, and `dependencies.tools[]`.

The convergence applies to the **on-demand regime**. Other regimes (always-on, session-preset, capability) have their own per-agent artifact shapes and are not promised through the same path.

The commands subsystem of Eutaxis is the first concrete consumer of this principle; see [agent-skills-as-target-surface](agent-skills-as-target-surface.md) for the commands-specific specialisation and [multi-file-artifact-model](multi-file-artifact-model.md) for the multi-file representation that flows from this decision.

## Discarded alternatives

- **Re-abstract on-demand into a Eutaxis intermediate form** distinct from `SKILL.md`. Rejected because both agents already accept the standard form; a Eutaxis-specific intermediate would mean two translations (source → Eutaxis → native) where one (source → native) is sufficient.
- **Emit the legacy per-agent surfaces** (Claude `.claude/commands/`, Codex `~/.codex/prompts/`) instead of skills. Rejected: Codex declares the legacy custom-prompt path deprecated; Claude treats the legacy command form as superseded. See [agent-skills-as-target-surface](agent-skills-as-target-surface.md) for the commands-specific disposition.
- **Compile only to one agent's flavour of the standard.** Rejected because the agents' elaborations diverge in load-bearing places (`allowed-tools` semantics, `agents/openai.yaml` siblings); a single flavour would forgo legitimate native features on the other.

## Rationale

The standard absorbs the convergence work the vendors already did. Passthrough keeps Eutaxis aligned with each vendor's recommended path without re-inventing the load model, the progressive disclosure contract, or the directory layout.

## Consequences

- The on-demand artifact is a **directory**, not a single file. This drives the multi-file model ([multi-file-artifact-model](multi-file-artifact-model.md)).
- Adapter elaborations are scoped to the agent-specific portion of the artifact; the body and the standard frontmatter pass through.
- Substrate volatility is now a single tracked risk: the standard itself can change. See [open-questions/substrate-volatility-tracking](../open-questions/substrate-volatility-tracking.md).
- Envelope-fidelity (invocation control, tool gating) is *not* guaranteed exact even when the body is; see [open-questions/on-demand-envelope-fidelity](../open-questions/on-demand-envelope-fidelity.md).
