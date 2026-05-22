# Native precedence, not a parallel resolution engine

## Status

Accepted.

## Context

Both target agents define cumulative global-then-project loading with
documented precedence rules. Claude Code loads `~/.claude/CLAUDE.md`
plus `<project>/CLAUDE.md` and resolves precedence in its own order;
Codex loads `~/.codex/AGENTS.md` plus `<project>/AGENTS.md` with
root-to-leaf merge subject to `project_doc_max_bytes` (default 32
KiB). Skills follow analogous scope hierarchies (enterprise / personal
/ project / plugin).

A cross-agent compiler could attempt to *reproduce* a layering engine
above the agents, deciding from the source which scope wins for each
component. Doing so introduces a second authority over what the agent
already does for itself, with a structural risk that the two
disagree.

## Decision

Eutaxis maps source components onto **native scopes** and lets the
platform resolve precedence. The compiler **does not** introduce a
parallel resolution engine for cross-scope layering. Per-scope output
is the unit of compilation; per-component layering across scopes is
the platform's job.

Concretely:

- A component declared at `global` scope is compiled to the global
  artifact path (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, or
  `~/.claude/skills/<name>/`, `~/.agents/skills/<name>/`).
- A component declared at `project` scope is compiled to the
  project-local equivalent.
- When the same component appears at both scopes, Eutaxis emits both
  artifacts; the platform decides which wins at load time.

The decision applies to **cross-scope layering only**. It does not
answer how multiple components within a single scope (multiple
always-on components into one `CLAUDE.md`, multiple skills into one
directory tree) compose; that is **intra-artifact composition**, an
unrelated and still-open question.

## Discarded alternatives

- **Build a Eutaxis-side precedence engine** that decides per-component
  which scope's artifact "wins" and emits only the winner. Rejected
  because the agent already resolves the same question and the two
  engines could disagree; the user would have to debug both.
- **Refuse cross-scope conflicts** (fail the build if a component
  exists at both global and project scope). Rejected because
  cross-scope overrides are a legitimate authoring pattern (project
  overrides personal default).
- **Adopt one agent's precedence rules as canonical** and translate
  the other. Rejected because the rules diverge in details (Claude's
  parent-directory walk vs Codex's root-to-leaf merge with
  `project_doc_max_bytes`); canonicalisation would lose information.

## Rationale

Native precedence works. Re-inventing it would either match the
platform (no value added) or diverge from it (silent bugs). The
compiler's job is to *populate* the slots the platform already
arbitrates between; it is not the platform's job.

This principle is the second leg of the build-time stance
([compiler-not-runtime-activation](compiler-not-runtime-activation.md)):
the compiler emits and the platform resolves.

## Consequences

- The same component declared at multiple scopes produces multiple
  artifacts on each target agent.
- Intra-artifact composition (multiple components in one
  `CLAUDE.md`, ordering, conflict policy) is **not** answered by this
  ADR. It is tracked at
  [open-questions/intra-artifact-composition](../open-questions/intra-artifact-composition.md).
- A future feature that needs Eutaxis to "select the winner" before
  emission requires revisiting this decision. The current architecture
  forecloses that path.
- Drift detection (`eutaxis check`) compares Eutaxis-emitted artifacts
  against on-disk state per (scope, target). It does not attempt to
  reason about which scope is currently winning in the agent.
