# Capability regime: split tool wiring from policy

**Severity.** High.
**Phase-blocking.** Phase 3 (capability compilation).
**Origin.** Adversarial review of the cross-agent compiler proposal,
objection O5 (and §10 Q7).

## Question

The capability regime as proposed folds "tool, MCP server, or
permission binding" into a single regime, then grades fidelity as
"Exact for MCP server definitions; approximate for permission and
command policy." MCP definitions and permission/command policy are
**categorically different objects**:

- **MCP server definitions** are declarative tool wiring. An
  "approximation" that points at the same server on both agents is
  acceptable.
- **Permission rules** (Claude `Bash(...)` patterns, `allow` / `deny`)
  and **Codex Starlark rules** are *security boundaries*.
  "Approximate" here means one agent grants slightly more or slightly
  less than the other. That is not fidelity degradation — it is a
  **vulnerability** if the looser side authorises something the
  stricter side blocks, and a **usability failure** if vice versa.

The fidelity vocabulary obscures the security stakes.

A secondary concern: the proposal allows external rule-owning projects
(vitruv, hermeneia) to ship source components. Permitting an external
fragment to expand the permission boundary — even with diff-and-review
— is a supply-chain surface that requires more than integrity hashes
to address. A permission widening hidden inside a long
`developer_instructions` payload is hard to spot even with diffs. This
couples to [cross-repository-source-acquisition](cross-repository-source-acquisition.md).

## Current state

The capability regime is **declared** in
[activation-regime-as-classification-axis](../adr/activation-regime-as-classification-axis.md)
and bracketed under
[two-source-kinds-instruction-vs-capability](../adr/two-source-kinds-instruction-vs-capability.md)
as the privilege-granting source kind. Nothing in the current
codebase compiles capability artifacts.

## Architectural components that depend on this

- The capability emission gate in `eutaxis generate
  --with-capabilities` (or equivalent).
- The supply-chain rules for cross-repository source components.
- The fidelity vocabulary
  ([same-source-not-same-behaviour](../adr/same-source-not-same-behaviour.md))
  — "Approximate" should not apply to security policy at all.

## Recommended resolution

Split the capability regime in two:

- **`tool-wiring`** (MCP server definitions, tool toggles). On-by-
  default after opt-in; "Approximate" fidelity is acceptable when the
  mechanisms differ.
- **`policy`** (permission rules, command policy, sandbox / approval
  configuration). Three rules:
  1. **Refuse cross-repo source components** by default. A
     vitruv-shipped permission widening is a supply-chain risk that
     the integrity-hash story does not address.
  2. **Refuse Approximate fidelity** entirely. If exact policy parity
     cannot be represented across the two agents, fail the build with
     a clear error.
  3. **Require a separate review gate** beyond the unified `eutaxis
     plan` diff. Privilege deltas are surfaced as a separate report
     section.

Codex Starlark rules in particular should remain **hand-authored** —
compiling them is not yet justified, and they remain on the deferred
list.

This split is ADR-ready. The open design work concerns the exact
schema vocabulary, the review gate, and the supply-chain policy for
externally sourced capability components. The adequacy principle is
settled: approximate fidelity may apply to tool wiring, but it must
not apply to security policy.

## Decision required before

Any release that compiles privilege-granting configuration. The split
should land before the implementation, not after.
