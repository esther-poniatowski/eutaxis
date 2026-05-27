---
tags: []
aliases:
  - Activation regime as the classification axis
index: "[Architecture decisions](_index.md)"
---

# Activation regime as the classification axis

## Status

Accepted.

## Context

A cross-agent compiler must decide, for each authored component, what native mechanism on each target agent should carry it. Two candidate axes exist:

- A **typed identifier taxonomy** such as `rule:`, `role:`, `style:`, `tool:`. The earlier proposal used this; the prefix selected the mechanism. The audit found the taxonomy embeds a closed vocabulary into syntax and forces premature classification of components whose nominal "type" does not determine where they belong on each agent.
- An **activation regime** — *when and how* the component must be active during a session. A component that is a "rule" by name may belong always-on (an interaction norm), on-demand (a checklist), or session-preset (a role); the right native mechanism follows from the regime, not the noun.

The reframing that selected the activation regime is foundational to the rest of the architecture: it determines what kinds of source the compiler accepts, what kinds of artifacts it emits, and what kinds of adapters it needs.

## Decision

The classification axis is the **activation regime**. The source declares a regime for each component; adapters map regimes to native mechanisms (Decision: how each regime compiles is the per-adapter mapping matrix; see [native-precedence-over-parallel-engine](native-precedence-over-parallel-engine.md) for what the compiler does with multi-component scopes).

Four regimes partition the component space:

- **Always-on** — content that must be present on every turn. Examples: interaction norms, file-authority rules, project conventions. Native targets: `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `<project>/CLAUDE.md`, `<project>/AGENTS.md`.
- **On-demand** — a procedure, checklist, output contract, or reference body relevant only to certain tasks; loaded on invocation so always-active context stays compact. Native targets: Claude skills at `~/.claude/skills/<name>/SKILL.md`, Codex skills at `~/.agents/skills/<name>/SKILL.md`. See the commands subsystem ADRs: [agent-skills-as-target-surface](agent-skills-as-target-surface.md), [multi-file-artifact-model](multi-file-artifact-model.md).
- **Session-preset** — a role, mode, or communication style fixed for the duration of a session. Mapping to native mechanisms is **structurally asymmetric** and is treated as an open question; see [open-questions/session-preset-regime](../open-questions/session-preset-regime.md).
- **Capability** — a tool, MCP server, or permission binding. This regime is configuration, not instruction content, and is privilege-granting; see [two-source-kinds-instruction-vs-capability](two-source-kinds-instruction-vs-capability.md).

The four regimes are exhaustive for the surfaces in scope. A component that does not fit (e.g. an agent-emitted hook) is either deferred ([open-questions/substrate-volatility-tracking](../open-questions/substrate-volatility-tracking.md)) or refused with a clear message.

## Discarded alternatives

- **Typed-identifier taxonomy** (`rule:`, `role:`, ...). Rejected: the noun does not determine the activation pattern; two components with the same prefix can belong to different regimes and therefore different native mechanisms.
- **Native-mechanism taxonomy** (component prefix says "this is a skill"). Rejected because it tethers the source to the current per-agent mechanism set; a future surface change reclassifies every component.
- **No taxonomy; route every component to every mechanism on every agent.** Rejected because the compiler then has no basis for selection, and the artifact-set explodes combinatorially.
- **Three-regime split** (collapsing session-preset into always-on). Rejected because the activation lifecycle of a session-fixed role differs from a permanent norm: session-preset is single-active-slot on both target agents, always-on is cumulative.

## Rationale

Selecting by regime preserves the source vocabulary the author cares about (one rule, one role, one tool — but expressed as content, not as syntax-typed identifiers) while letting adapters do the work of mapping to native targets. The classification has empirical support in the platform: the four regimes correspond to four distinct lifecycle behaviours documented by each agent.

## Consequences

- Adapters declare a regime → mechanism mapping with a fidelity grade per row.
- A component cannot belong to two regimes simultaneously; if its intended behaviour spans two (e.g. "always available as a checklist and sometimes invoked directly"), the source must split it.
- New regimes require an architecture decision; they are not added by declaring a string. This keeps the taxonomy closed in a way the typed-identifier proposal could not.
- The capability regime is privilege-granting and follows separate review and security rules; see [two-source-kinds-instruction-vs-capability](two-source-kinds-instruction-vs-capability.md).
