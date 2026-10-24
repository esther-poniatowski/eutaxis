---
tags:
  - index
aliases:
  - Open architectural questions
index: "[Eutaxis](../index.md)"
---

# Open architectural questions

Open questions for the eutaxis cross-agent compiler that the current ADR set does **not** resolve. Each file states one question, the architectural component that depends on it, and any partial work that has landed. An adversarial review of the cross-agent compiler proposal originally surfaced these questions; the review file itself has been retired in favour of this modular set.

## Triage

| Question | Severity | Phase-blocking | Status |
| --- | --- | --- | --- |
| [session-preset-regime](session-preset-regime.md) | High | Phase 2 | Open |
| [instruction-file-ownership](instruction-file-ownership.md) | High | Phase 1 (always-on regime) | Partial — commands subsystem solved separately |
| [on-demand-envelope-fidelity](on-demand-envelope-fidelity.md) | Medium | None | Partial — commands subsystem uses `agents/openai.yaml` |
| [capability-regime-split](capability-regime-split.md) | High | Phase 3 | Open |
| [subagent-vs-role-routing](subagent-vs-role-routing.md) | Medium | Phase 2 | Open |
| [behavioural-validation](behavioural-validation.md) | Medium | None (contract reframed via golden-file review) | Open as follow-up |
| [cross-repository-source-acquisition](cross-repository-source-acquisition.md) | Medium | Phase 1 (if external fragments are consumed) | Open |
| [substrate-volatility-tracking](substrate-volatility-tracking.md) | Low | None | Open |
| [identifier-and-namespace-algebra](identifier-and-namespace-algebra.md) | Medium | Phase 1 (cross-repo) | Partial — `name == directory` codified for Codex |
| [claude-md-cumulative-loading-semantics](claude-md-cumulative-loading-semantics.md) | Medium | Phase 1 (Claude-side always-on adapter) | Open |

## Resolved records

- [Silent-failure classification criterion](silent-failure-classification.md): explains the question resolved by the accepted failure-mode decision
