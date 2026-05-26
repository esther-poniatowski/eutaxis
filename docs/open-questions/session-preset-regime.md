# Session-preset regime mismodel

**Severity.** High.
**Phase-blocking.** Phase 2 (session-preset compilation).
**Origin.** Adversarial review of the cross-agent compiler proposal,
objection O1.

## Question

The proposed mapping for the **session-preset regime** routes a single
authored component to a Claude Code output style *and* to a Codex
`[profiles.<id>]` block carrying `developer_instructions`. The two
mechanisms differ in two structural ways that "approximate fidelity"
does not capture:

1. **Semantics diverge.** A Claude Code output style is
   **substitutive** — it replaces the software-engineering portion of
   the system prompt. A Codex profile with `developer_instructions`
   is **additive** — it appends instructions to the base personality.
   The same source produces a *replacement* on one agent and an
   *addition* on the other.
2. **Activation is single-slot and out-of-band.** Only one Codex
   profile is active per session; selection is governed by the
   top-level `profile = "<name>"` key in `config.toml` or by
   `--profile`. The Claude output style is activated by an
   `outputStyle` settings key. Eutaxis can install per-role artifacts
   but cannot make a session *respect* a particular session-preset for
   a given task. Writing the activation key on behalf of a component
   is destructive — it overwrites the user's active selection.

## Current state

The session-preset regime is **declared** in
[activation-regime-as-classification-axis](../adr/activation-regime-as-classification-axis.md)
as one of the four regimes, but **not yet implemented**. The
phasing
([cross-agent compiler architecture](../adr/compiler-not-runtime-activation.md))
places this regime after Phase 1 (always-on plus on-demand). No
artifact in the current codebase compiles to an output style or to a
profile block.

## Architectural components that depend on this

- The session-preset row of the mechanism mapping matrix.
- The fidelity vocabulary
  ([same-source-not-same-behaviour](../adr/same-source-not-same-behaviour.md))
  — the "Approximate" grade currently understates the asymmetry.
- The capability-vs-instruction split
  ([two-source-kinds-instruction-vs-capability](../adr/two-source-kinds-instruction-vs-capability.md))
  — if Eutaxis must write the activation key, that path becomes
  privilege-adjacent.

## Candidate resolution

The recommended correction combines two moves:

- **Demote session-preset artifacts to catalogued, manually activated
  artifacts.** The compiler may emit output-style files or profile
  fragments, but it does not write the active selection key. `eutaxis
  explain` reports that activation is out of band.
- **Route role components to subagents where the target platform
  supports subagents.** A reviewer, writer, auditor, or domain expert
  role is a delegated-agent concern, not a session-profile concern.
  Output styles and profiles remain available for non-role session
  preferences such as communication style.

Cross-agent equivalence is not claimed for session presets. The
fidelity grade must distinguish "artifact installed" from "session
activated" and from "role isolation achieved." This question should
be resolved together with
[subagent-vs-role-routing](subagent-vs-role-routing.md), then promoted
to an ADR before Phase 2 implementation.

## Decision required before

Any release that compiles session-preset components.
