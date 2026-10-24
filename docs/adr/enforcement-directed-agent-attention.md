---
tags: []
aliases:
  - Enforcement-directed agent attention
index: "[Architecture decisions](_index.md)"
---

# Enforcement-directed agent attention

## Status

Accepted.

## Purpose

Mechanical verification should consume machine time. Agent attention should be reserved for criteria whose truth depends on meaning, evidence, purpose, or trade-offs. A clean checker result establishes only the rules mapped to that checker.

## Enforcement classes

The catalog derives one enforcement class from each criterion's evaluator contract:

- `mechanical` means a registered checker has total declared coverage and authoritative adjudication; the agent runs the checker and reasons further only on a failure, dispute, or checker change
- `assisted` means a detector has partial coverage and candidate adjudication; the agent triages every candidate and answers the declared residual question
- `deliberative` means no machine evaluator decides the criterion; the agent must judge it from the artifact, its purpose, and the evidence

The class is not a subjective priority score. It follows from the evaluator's declared capabilities.

Each evaluator contract records `kind` (`checker`, `detector`, or `manual`), registry reference, `coverage` (`total`, `partial`, or `none`), `adjudication` (`authoritative`, `candidate`, or `manual`), timing, failure behavior, evidence form, evaluator version, and applicable artifact revision. Version 1 admits exactly three triples: checker/total/authoritative, detector/partial/candidate, and manual/none/manual. Mechanical evaluators also name a known-failure test. A checker cannot claim total authoritative coverage until a planted failure proves that the check can fail and the contract names the class it covers.

## Attention plan

After applicability and resolution, the catalog produces three packets:

1. a deliberation packet containing the complete deliberative criteria, read before design
2. an assisted packet containing each detector invocation and its residual judgment question
3. a mechanical packet containing checker identifiers, inputs, and expected evidence rather than the full prose of their rules

Resolution and completion use separate ledgers. The resolution trace records declaration-level events such as `inapplicable`, `waived`, `substituted`, and `overridden`; these events explain why a declaration is absent and never count as criterion evidence.

The completion ledger contains one record for every criterion of every effective declaration, regardless of enforcement class. Its states are `satisfied`, `violated`, `blocked`, and `unchecked`, with evaluator identity, version, evidence, and timestamp. `unchecked`, `violated`, or `blocked` prevents successful completion. The only terminal non-blocking exception is an explicit migration baseline that names the finding, owner, expiry condition, and migration it awaits; a baseline cannot be created silently by a run under evaluation.

Mechanical results are reported compactly after the purpose check; they do not substitute for it. Assisted criteria require both detector evidence and the recorded residual judgment. Deliberative criteria require manual evidence against the criterion, not a general assertion that the artifact was reviewed.

Failure mode and enforcement class remain orthogonal. A mechanically checked rule can still require a resident trip-wire when the check runs only after an irreversible action. Conversely, a visible prose defect can require deliberative enforcement.

## Consequences

- The canonical declaration owns the evaluator mapping; checker registries and reports refer to its identifier rather than restating the rule.
- Query output answers three distinct questions: what must be deliberated, what must be inspected with assistance, and what must be run.
- Agent reports emphasize decisions and residual uncertainty. Checker verdicts occupy one compact evidence block.
- Migration must not classify a fluent but pattern-detectable prose construction as deliberative merely because agents currently check it by reading.
