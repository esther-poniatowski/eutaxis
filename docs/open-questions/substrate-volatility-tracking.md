# Substrate volatility: tracking vendor doc drift

**Severity.** Low.
**Phase-blocking.** None.
**Origin.** Adversarial review of the cross-agent compiler proposal,
objection O9.

## Question

The architecture pins itself to the **stable substrates** of the two
target agents: the instruction-file layer
(`CLAUDE.md` / `AGENTS.md`) and the Agent Skills open standard
([convergence-on-agent-skills-standard](../adr/convergence-on-agent-skills-standard.md)).
The deferred surfaces (hooks, Codex rules, plugin manifests, etc.)
are listed under "decisions deferred until agent surfaces stabilise"
in the legacy proposal.

The implicit assumption — that the committed substrates are stable —
is empirically thin. Both have moved materially in the last 18
months:

- Skills absorbed custom commands (Claude) and deprecated custom
  prompts (Codex). The commands subsystem of Eutaxis was rewritten
  to track this change; see
  [agent-skills-as-target-surface](../adr/agent-skills-as-target-surface.md).
- `AGENTS.override.md` and `project_doc_max_bytes` are recent
  additions to the instruction-file layer.
- The Agent Skills "open standard" is young; its status as an open
  standard is asserted by the agents' own docs rather than by an
  independent body.

The framework treats stability as a binary. The reality is that even
the committed substrates change, and the question is whether the
framework has a discipline for noticing.

## Current state

No mechanism currently tracks vendor-doc revision. The supporting
notes under `~/Documents/work/techne/tutorials/ai-agents/` are the
de facto reference, with no automatic check that they remain in
sync with upstream documentation.

The commands subsystem rewrite (the work that produced the existing
ADR set) is itself an unforced response to substrate movement — the
legacy `.claude/commands/` and `~/.codex/prompts/` surfaces were
deprecated; the rewrite is the catch-up.

## Architectural components that depend on this

- The mapping matrix in any future ADR.
- The fidelity grades in
  [same-source-not-same-behaviour](../adr/same-source-not-same-behaviour.md)
  — a grade based on a stale doc is wrong.
- The "stable substrate" claim implicit in the deferral list.

## Candidate resolution

A small, mechanical discipline:

- **Per-adapter `vendor-doc-revision` field** recording the
  documentation revision the adapter was last reconciled to.
- **Verification check** that flags drift between the recorded
  revision and the current vendor docs (or, at minimum, between the
  recorded revision and the supporting techne notes' modification
  time).
- **`eutaxis explain`** surfaces the vendor-doc revision the
  adapter was reconciled to, so the user can judge currency.

This is a small addition; its value is honesty about substrate
volatility rather than feature reach.

## Decision required before

No release is blocked on this. The discipline can be added
incrementally — start by recording the revision in adapter
metadata, then build the verification check.
