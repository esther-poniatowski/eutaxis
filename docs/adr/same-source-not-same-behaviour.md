# Same source, not same behaviour: declared per-target fidelity

## Status

Accepted.

## Context

Eutaxis compiles one source into native artifacts on multiple agents whose customisation surfaces are structurally different. Output styles in Claude Code are a first-class, system-prompt-level mechanism that **substitutes** the software-engineering role; Codex has no registry counterpart and approximates the same effect with a profile combined with **additive** `developer_instructions`. Profiles, conversely, are a Codex-only construct declared in TOML configuration, with no Claude Code equivalent. Codex rules are a Starlark command-policy layer with no behavioural analogue in Claude Code. Hook event vocabularies differ by an order of magnitude.

A compiler that promises identical behaviour across agents would have to bridge mechanisms that are not equivalent. The promise would fail silently — same source, divergent behaviour, no warning. The adversarial review of the parent proposal flagged this as the single issue most likely to mislead authors.

## Decision

The contract Eutaxis offers is **reproducible configuration from one source**, not **behavioural identity across agents**. Every compiled artifact is assigned, per target, an explicit **fidelity grade**:

- **Exact** — the native mechanism faithfully implements the source's intent. Example: `SKILL.md` body content rendered to Claude `~/.claude/skills/<name>/SKILL.md` and Codex `~/.agents/skills/<name>/SKILL.md`. The Agent Skills standard makes this row exact at the payload level.
- **Approximate** — the native mechanisms differ in shape but the compiled artifacts implement the same intent within documented asymmetry. Example: regime `user-invoked` maps to Claude `disable-model-invocation: true` (in `SKILL.md`) and Codex `policy.allow_implicit_invocation: false` (in `agents/openai.yaml`) — same intent, different mechanism, different file.
- **Unsupported** — no native mechanism on this target captures the source's intent. The compiler refuses or warns; what to do is the fidelity-policy question, tracked in [open-questions/on-demand-envelope-fidelity](../open-questions/on-demand-envelope-fidelity.md).

The fidelity grade is surfaced by `eutaxis explain` per (component, target). Authors see, before installation, where the mechanisms diverge.

## Discarded alternatives

- **Promise behavioural identity** ("compile once, behave the same"). Rejected because the mechanisms are non-isomorphic; the promise would be false in a way users could not easily detect.
- **Suppress the asymmetry** (compile both targets to a single lowest-common-denominator mechanism). Rejected because that would forgo first-class agent features (Claude `allowed-tools`, Codex `agents/openai.yaml` UI metadata) and produce worse outputs than the agents support natively.
- **Compile only where exact fidelity is achievable.** Rejected because most regimes have at least one Approximate row; this rule would gut the cross-agent compiler's reach.
- **Leave fidelity implicit in the mapping matrix.** Rejected because authors then have to read the mapping table to know what they get; surfacing it per artifact via `explain` is the visible commitment.

## Rationale

Declaring asymmetry up front is more useful than pretending equivalence. The grade is a UX contract: when a row is Approximate, the author owes the divergence a thought; when it is Unsupported, the author owes a different design.

## Consequences

- Adapters declare a fidelity grade for every (regime, mechanism) row they support. The grade is part of the mapping matrix, not a per-component override.
- `eutaxis explain` is a first-class CLI surface (alongside `generate` / `check` / `plan`).
- The compiler cannot certify behavioural correctness; that requires a behavioural-validation phase tracked in [open-questions/behavioural-validation](../open-questions/behavioural-validation.md).
- The fidelity vocabulary applies across regimes; specific commands ADRs (e.g. [regime-and-permission-mapping](regime-and-permission-mapping.md)) inherit it.
