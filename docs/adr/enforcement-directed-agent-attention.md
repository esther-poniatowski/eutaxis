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

Static classification is necessary but insufficient for packet issuance. A mechanical packet requires an exact checker runner binding and one process-local `KnownFailureAssurance`. The existing `execute_known_failure_fixtures` function issues this assurance after every named fixture returns its declared expected result. The assurance implements the existing read-only `Mapping[str, CheckerResult]` interface, so callers retain fixture lookup and canonical iteration without a parallel execution path.

`KnownFailureAssurance` is an identity-valued, frozen aggregate with a disabled public constructor and an execution-owned issuer stamp. Its own equality, inequality, and hash methods use object identity rather than mapping contents. Python cannot force an unrelated left operand to adopt those semantics, so authorization never uses `==`; the planner uses `is` and validates the issuer stamp. Copying, pickling, and reconstruction fail; the stamp is private to the execution module and absent from public exports. This boundary prevents ordinary construction through the public API; it does not claim protection against hostile Python introspection. The aggregate retains the exact declaration registry, fixture index, and checker runner registry objects used by the execution event. It contains one immutable entry for every checker contract in the registry, including a checker that no current obligation references. Each entry holds the exact evaluator reference and an authored-order tuple of immutable pairs. Each pair holds one declared fixture identifier and the frozen, post-validation `CheckerResult` returned for that fixture. Issuance requires the pair count and identifiers to equal the complete declared fixture tuple. Fixture descriptors not declared by a checker remain permissible in the index, but the executor neither runs nor records them.

Execution uses one order throughout the aggregate: evaluator references sorted by identifier and version, then each evaluator's declared fixture identifiers in authored order. The same order governs checker invocation, the evaluator entries, and the flattened mapping. Therefore, descriptor path order cannot alter the run or the exposed result order.

The fixture index is itself a process-local, loader-issued aggregate. Its public constructor, copying, serialization, and reconstruction fail. The known-failure executor checks its private loader stamp before it reads any fixture field or invokes any runner. Therefore, replacing a public fixture leaf cannot create a certified index; only the validating loader assembles the fixture mapping. The index retains one immutable digest record for each descriptor-field occurrence, even when two occurrences resolve to the same canonical path. Each record contains the canonical path, a lowercase 64-character SHA-256 digest, the owning fixture identifier, the resource role, and the descriptor document path. The document paths are `$` for the descriptor, `$.input.sources[i]` for a source, and `$.input.facet-registry` for the facet registry. An implementation may cache one computed digest per canonical path, but a diagnostic names the first failing occurrence in canonical execution order.

The known-failure executor verifies all records for a fixture immediately before its invocation. Whether the callable returns or raises, the executor verifies them again before it admits the invocation result or exception. A changed or unreadable resource takes precedence over a simultaneous runner exception or invalid result because the invocation no longer corresponds to the loaded fixture snapshot. After every invocation finishes, the executor performs one final sweep over all declared fixture records immediately before issuance. A changed or unreadable file owns a located execution error, and no assurance is issued. Tests plant mutation with a runner exception and with an invalid result to fix this precedence.

These digest checks assume that no concurrent actor performs an undetected change-and-restoration cycle while a path-based runner executes. Eutaxis does not control the file read inside a registered callable, so the assurance does not prove which bytes the callable opened under hostile concurrent mutation. The checks instead establish that the loaded snapshot was present at each controlled boundary and remained current immediately before issuance. The later packet planner rechecks the assured digests before it authorizes a packet. It also requires object identity with all three retained inputs, validates the private issuer stamp, and rechecks each evaluator entry against the current declaration's complete fixture tuple. A different registry, fixture index, or runner registry, an incomplete entry, or a stale resource owns a readiness error in that planner.

The assurance proves one exact execution event under the no-concurrent-mutation assumption. It does not prove that an arbitrary Python callable will behave identically in the future. Checker runners are reviewed, code-owned process objects; their stability between assurance and use is part of that trust boundary. An assurance cannot be serialized, restored, or reused across processes. Packet planning must consume it in the same process with the same runner registry. These constraints narrow the claim to validated fixture behavior at issuance while retaining later detection of mutable fixture resources.

Execution retains its existing diagnostic ownership. Missing or mismatched fixtures, missing runners, invalid inputs, changed resources, and invalid results fail with located execution diagnostics and issue nothing. The later packet planner owns only assurance-readiness mismatches discovered after successful issuance.

An assisted packet requires an exact detector runner binding and the detector's residual question. A missing detector runner raises a blocking readiness error. Known-failure assurance applies only to total authoritative checkers; it does not convert a partial detector into an authoritative evaluator. The planner never silently emits the packet and never reclassifies the obligation as deliberative.

### Detector runner boundary

The detector boundary must preserve the semantic distinction between authoritative checking and candidate detection. Three designs were considered. Extending `CheckerRunnerRegistry` would let partial candidate producers enter a registry whose name, result states, and assurance contract promise authoritative decisions. A fully independent detector implementation would preserve that distinction but duplicate exact-reference, operation-contract, ordering, and callable validation. A public generalized evaluator registry would expose combinations that version 1 does not admit. Therefore, version 1 uses separate public checker and detector façades over one private runner-registry validator.

The detector façade consists of `DetectorRunner`, `DetectorRunnerBinding`, `DetectorRunnerRegistry`, and `build_detector_runner_registry`. A binding contains one exact detector reference, one exact operation reference, and one synchronous reviewed callable. The builder sorts bindings by evaluator identifier and version, then operation identifier and version. It rejects duplicate evaluator references, unresolved or wrong-kind contracts, checker and manual evaluators, and unsupported callables with detector-specific located registry errors. The resulting mappings are immutable and retain the exact declaration registry object. Existing checker types, messages, and public behavior remain unchanged while their builder delegates the common structural checks to the same private validator.

`DetectorRunnerRegistry` is a process-local, builder-issued aggregate. Its public constructor, copying, serialization, and reconstruction fail. A private stamp authenticates the builder, and the later planner validates that stamp and compares the retained declaration registry with `is`. Therefore, an ordinary caller cannot establish detector readiness through the public construction boundary. This cooperative process-local provenance check does not resist hostile Python introspection of private attributes. The stronger ordinary-API boundary is necessary because assisted readiness has no known-failure assurance equivalent.

Binding readiness authenticates only the exact process-local callable object and the synchronous signature observed when the registry was built. A mutable callable or closure remains inside the reviewed, code-owned trust boundary; registry authenticity does not prove its later behavior. The detector executor must validate every returned result independently and must never treat registry authenticity as result evidence.

A detector callable returns `DetectorResult`, a frozen value containing its exact evaluator reference, input revision, and evidence. It has no `satisfied` or `violated` state because partial candidate evidence cannot decide an obligation. A successful run may report zero candidates; the evaluator's evidence schema defines its output. Version 1 detector declarations require `failure-behavior: block`; `candidate` and `record` remain unavailable until their exception, evidence, and ledger semantics are specified. A runner exception therefore blocks detector execution. Registration validates only bindings and callable shape. The later detector executor will freeze and validate the input, exact identity, admitted revision, and evidence schema before it admits a result.

The detector-registry implementation applies the blocking invariant as one atomic contract migration. It updates the normative declaration schema, the persisted catalog schema, every valid detector fixture, source-boundary and persisted-index negative cases for both rejected alternatives, and any affected generated or golden catalog artifact. Both schemas require `failure-behavior: block` when `evaluator-kind` is `detector`; the registry cannot close while either boundary still admits `candidate` or `record`.

The builder-issued registry establishes binding readiness only. It does not establish that a callable returns `DetectorResult` or produces contract-valid evidence. Therefore, this bounded registry step does not authorize runnable assisted work, issue an assisted packet, or execute a detector. The dependency order is detector registry, detector executor, then packet planner. Packet planning will receive concrete inputs separately, validate them against the bound operation contract, and include the invocation together with the residual question. Detector execution and residual judgment will later contribute distinct records to the completion ledger.

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
