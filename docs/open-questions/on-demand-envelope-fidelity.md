---
tags: []
aliases:
  - "On-demand fidelity: payload vs envelope"
index: "[Open architectural questions](_index.md)"
---

# On-demand fidelity: payload vs envelope

**Severity.** Medium. **Phase-blocking.** None (commands subsystem already addresses the load-bearing part). **Origin.** Adversarial review of the cross-agent compiler proposal, objections O4 and §10 Q4.

## Question

The on-demand regime compiles to Agent Skill directories on both target agents ([convergence-on-agent-skills-standard](../adr/convergence-on-agent-skills-standard.md)). The original proposal graded this row "Exact (adapter handles path, frontmatter, and invocation-sigil deltas)". The review argued that the deltas exceed "path / frontmatter / sigil":

- **Invocation control surfaces differ in shape.** Claude controls implicit invocation through `SKILL.md` frontmatter (`disable-model-invocation`, `user-invocable`) plus a settings field (`skillOverrides`). Codex controls it through a separate file, `agents/openai.yaml` (`policy.allow_implicit_invocation`).
- **Tool-restriction frontmatter differs.** Claude `allowed-tools` is a first-class permission grant; Codex `allowed-tools` is experimental and documented as metadata only.
- **Discovery semantics differ.** Claude's project-skill walk (start-dir up to repo root, plus nested-on-demand) does not match Codex's `.agents/skills/` walk.
- **Live-reload semantics differ.** Claude reloads skills mid-session; Codex's reload behaviour is not equivalently documented.

The behavioural-equivalence claim (the same procedure runs when triggered) is mostly true. The **operational** claim (the skill is invocable and controllable the same way) is not.

A separate sub-question: **fidelity policy.** When an artifact compiles at "approximate" fidelity, should the build fail, emit a warning, or be configurable per component? The current contract ([same-source-not-same-behaviour](../adr/same-source-not-same-behaviour.md)) surfaces the grade via `eutaxis explain` but does not gate the build.

## Current state — partial resolution

The commands subsystem of Eutaxis explicitly addresses several of the review's bullets:

- The Codex adapter now writes `agents/openai.yaml` carrying `policy.allow_implicit_invocation: false` from `regime: user-invoked`. See [regime-and-permission-mapping](../adr/regime-and-permission-mapping.md).
- The Codex adapter **refuses** `allowed-tools` passthrough, since the doc marks it metadata-only. The asymmetry is surfaced at authoring time.
- The multi-file artifact model ([multi-file-artifact-model](../adr/multi-file-artifact-model.md)) is general enough to carry the per-agent envelope differences.

What remains open in the framework:

- The **mapping matrix** in any future ADR or doc should reflect *envelope fidelity* (the agent-specific frontmatter / sibling-file shape) separately from *payload fidelity* (the body).
- **Discovery and live-reload deltas** are not currently surfaced by `eutaxis explain`. They affect iteration-time UX, not build-time semantics.
- The **fidelity policy** question (build / warn / configurable) remains undecided.

## Architectural components that depend on this

- `eutaxis explain` output design.
- Any future ADR that re-tabulates the regime-to-mechanism mapping matrix.
- The contract surfaced to authors when they write a new on-demand component.

## Candidate resolution

- **Demote on-demand from a single fidelity grade to two:** payload-fidelity (Exact, both agents) and invocation-fidelity (Approximate). Surface both in `eutaxis explain`.
- **Decide the fidelity policy** as a default with per-component override: warn by default; `--strict` fails the build on any Approximate or Unsupported row.

## Decision required before

A user-facing release of `eutaxis explain` that promises a fidelity contract beyond what the commands subsystem already delivers.
