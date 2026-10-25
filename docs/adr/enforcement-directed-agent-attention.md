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

Mechanical verification should consume machine time. Agent attention should be reserved for obligations whose truth depends on meaning, evidence, purpose, or trade-offs. A clean checker result establishes only the exact obligations mapped to that evaluator.

## Enforcement classes

The catalog derives one enforcement class from each evaluator-backed obligation's evaluator contract:

- `mechanical` declares a checker with total coverage and authoritative adjudication
- `assisted` declares a detector with partial coverage and candidate adjudication
- `deliberative` declares a manual evaluator with no machine coverage or adjudication

These classes state capabilities, not runtime readiness. After the readiness gate issues a packet, the agent runs mechanical work and reasons further only on a failure, dispute, or checker change. For assisted work, the agent triages every detector candidate and answers the residual question. For deliberative work, the agent judges the obligation from the artifact, its purpose, and the evidence.

The class is not a subjective priority score. It follows from the evaluator's declared capabilities.

Each evaluator contract records `kind` (`checker`, `detector`, or `manual`), registry reference, `coverage` (`total`, `partial`, or `none`), `adjudication` (`authoritative`, `candidate`, or `manual`), timing, failure behavior, evidence form, evaluator version, and applicable artifact revision. Version 1 admits exactly three triples: checker/total/authoritative, detector/partial/candidate, and manual/none/manual. Mechanical evaluators also name a known-failure test. A checker cannot claim total authoritative coverage until a planted failure proves that the check can fail and the contract names the class it covers.

## Enforcement classification boundary

Version 1 classifies each evaluator-backed obligation, not its enclosing declaration. One rule may therefore contribute assignments to several enforcement classes. Evaluator-backed predicates of procedures and operations use the same classes, so a manual or detector-backed predicate cannot disappear behind an execution boundary. A predicate without an evaluator reference remains executable predicate logic owned by procedure or operation execution.

`EnforcementClass` is the closed enumeration `mechanical`, `assisted`, and `deliberative`. `derive_enforcement_class(evaluator)` maps only the three admitted evaluator triples to this enumeration. It rejects any other triple instead of guessing from one field. For a checker, the declared contract must also name at least one known-failure fixture, as required by the evaluator schema.

This result is a *declared classification*. It does not prove that an evaluator can run or that its claims have passed their assurance gate. Static filtering alone must not remove an obligation from agent attention or authorize an attention packet.

Three frozen locator types preserve the source distinction:

- `RuleCriterionEnforcement(declaration, criterion, evaluator, enforcement)` identifies one rule-local criterion
- `ProcedurePredicateEnforcement(declaration, phase, predicate, evaluator, enforcement)` identifies one evaluator-backed predicate, where `phase` is `precondition`, `invariant`, or `postcondition`
- `OperationPredicateEnforcement(operation, predicate, evaluator, enforcement)` identifies one precondition on an exact operation reference

These locators do not copy criterion statements, predicate expressions, or evaluator contracts. Callers recover those objects from the catalog, which remains their authority.

`DeclarationCatalog.filter_enforcement(enforcement)` returns all three locator types from live records. Rule and procedure declarations follow identifier order. Rule criteria retain authored order. Procedure predicates follow phase order—preconditions, invariants, then postconditions—and authored order within each phase. Operation contracts follow exact `(identifier, version)` order, and their preconditions retain authored order. Unversioned locators precede operation locators, matching the catalog's existing record traversal. A declaration or operation with obligations in two classes appears in both corresponding results. An obligation without an evaluator reference appears in none. The operation is static: it classifies every authored evaluator-backed obligation without evaluating applicability.

The attention planner intersects rule locators with final projected criteria and procedure locators with final effective procedure components. It expands an operation locator once for each action of an effective procedure that invokes that exact operation. The expanded completion key is `(procedure identifier, action identifier, operation reference, predicate identifier)`. Thus, two actions that invoke one operation contract receive distinct evidence records, even when they share bindings.

Detector contracts gain one canonical `residual-question` field. The field states the judgment left after the detector reports its candidates. The schema requires a non-empty residual question for a detector and forbids it for a checker or manual evaluator. The detector owns this question because it describes the limit of that evaluator's coverage; the packet supplies the selected criterion or predicate as the object to which the question applies.

The current persisted index cannot implement this filter because its rows omit obligation-to-evaluator references. This limitation is explicit rather than silently reconstructing incomplete records. Persisted parity requires a separately versioned index projection that retains those references; it must still derive the class from evaluator contracts instead of storing a copied class.

## Attention plan

After applicability and resolution, the enforcement planner produces three packets:

1. a deliberation packet containing the complete deliberative obligations, read before design
2. an assisted packet containing each detector invocation and its residual judgment question
3. a mechanical packet containing checker identifiers, inputs, and expected evidence rather than the full prose of each source declaration

Static classification is necessary but insufficient for packet issuance. A mechanical packet requires an exact checker runner binding and a `KnownFailureAssurance` issued only by the known-failure executor after every named fixture returns its declared expected result. The aggregate is immutable and rejects direct construction. It retains the exact declaration registry, fixture index, and checker runner registry objects used by the run. For each exact evaluator reference, it records the complete declared fixture tuple and its validated results. The packet planner receives the current versions of all three inputs and requires object identity with all three retained assurance inputs. It then verifies that the assurance entry names the evaluator's complete current fixture tuple. Assurance from another declaration, fixture, or runner snapshot, or from an incomplete fixture set, cannot authorize a packet.

An assisted packet requires an exact detector runner binding and the detector's residual question. Missing runner or assurance evidence raises a blocking readiness error. The planner never silently emits the packet and never reclassifies the obligation as deliberative. A separate detector-runner boundary must therefore precede assisted packet implementation; the existing checker-only runner registry cannot issue assisted work.

Resolution and completion use separate ledgers. Events such as `declaration-evaluated`, `declaration-excluded`, `norm-removed`, and `norm-substituted` explain selection, exclusion, and final norm projection. Resolution events never count as completion evidence.

The completion ledger contains one record for every criterion of every effective rule, every predicate of every effective procedure, and every operation precondition expanded per effective procedure action. Evaluator-less predicates receive evidence from procedure or operation execution. Evaluator-backed obligations also record their enforcement class. Ledger states are `satisfied`, `violated`, `blocked`, and `unchecked`, with evaluator identity when present, evidence, and timestamp. `unchecked`, `violated`, or `blocked` prevents successful completion. The only terminal non-blocking exception is an explicit migration baseline that names the finding, owner, expiry condition, and migration it awaits; a baseline cannot be created silently by a run under evaluation.

Mechanical results are reported compactly after the purpose check; they do not substitute for it. Assisted obligations require both detector evidence and the recorded residual judgment. Deliberative obligations require manual evidence against the criterion or predicate, not a general assertion that the artifact was reviewed.

Failure mode and enforcement class remain orthogonal. A mechanically checked obligation may belong to a rule whose failure mode still requires a resident trip-wire because the check runs only after an irreversible action. Conversely, a visible prose defect can require deliberative enforcement.

## Consequences

- The canonical declaration owns the evaluator mapping; checker registries and reports refer to its identifier rather than restating the rule.
- Mixed declarations remain visible at obligation granularity rather than receiving one lossy class.
- Declared mechanical capability and proved runtime readiness remain separate facts.
- Query output answers three distinct questions: what must be deliberated, what must be inspected with assistance, and what must be run.
- Agent reports emphasize decisions and residual uncertainty. Checker verdicts occupy one compact evidence block.
- Migration must not classify a fluent but pattern-detectable prose construction as deliberative merely because agents currently check it by reading.
