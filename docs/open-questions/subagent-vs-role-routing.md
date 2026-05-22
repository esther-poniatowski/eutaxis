# Subagent deferral vs role routing

**Severity.** Medium.
**Phase-blocking.** Phase 2 (session-preset compilation).
**Origin.** Adversarial review of the cross-agent compiler proposal,
objection O6.

## Question

The original proposal defers subagents on the grounds that their
declaration models differ between agents. It then routes role /
session-preset components to **output styles** (Claude) and
**profiles** (Codex) — see
[session-preset-regime](session-preset-regime.md) for why that
mapping is structurally wrong.

Subagents are the **native role-isolation mechanism** on both agents:
separate context, separate tool set, separate model. A "role"
component, in the sense the prior proposal used (`role:reviewer`,
`role:writer`), maps to a subagent on both platforms cleanly.

The decision currently chosen — defer the mechanism best aligned with
P3 (`activation-regime-as-classification-axis`) and fully model the
mechanism worst aligned with it — is empirically inverted. The
declaration-model-differs justification applies equally to profiles
(TOML, single active slot, top-level selection key) and output
styles (markdown plus settings activation). The differences are real
for subagents but no more severe than for the regime already
supported.

## Current state

Subagents are listed under "decisions deferred until agent surfaces
stabilise" in the legacy proposal. They are not in any current ADR.
The session-preset regime, currently routed to output styles /
profiles, has its own open question
([session-preset-regime](session-preset-regime.md)).

The two open questions are coupled: a satisfying resolution likely
addresses both at once.

## Architectural components that depend on this

- The session-preset row of the mechanism mapping matrix.
- The regime-to-mechanism rules in
  [activation-regime-as-classification-axis](../adr/activation-regime-as-classification-axis.md).
- The mechanism set the framework commits to in
  [convergence-on-agent-skills-standard](../adr/convergence-on-agent-skills-standard.md)
  — subagents are not Agent Skills, so a separate convergence story
  is needed if they are adopted.

## Candidate resolution

- **Promote subagents from "deferred" to "in scope".** Their
  declaration model is no more divergent than profile / output-style.
- **Re-evaluate session-preset.** Role components should target
  subagents where the platform supports it; output-style /
  profile-fragment artifacts become a fallback for non-role
  session-preset components (e.g. communication style).
- **At minimum, surface the asymmetry** in the matrix: the framework
  currently picks the worse-fit native mechanism for role-style
  components. Document this in `eutaxis explain` until a better
  routing is implemented.

## Decision required before

Any release that ships session-preset compilation as a first-class
regime. The subagent question should be resolved before, or
simultaneously with,
[session-preset-regime](session-preset-regime.md).
