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

The enforcement class is not a subjective priority score. The evaluator's declared capabilities determine the class.

Each evaluator contract records `kind` (`checker`, `detector`, or `manual`), registry reference, `coverage` (`total`, `partial`, or `none`), `adjudication` (`authoritative`, `candidate`, or `manual`), timing, failure behavior, evidence form, evaluator version, and applicable artifact revision. Version 1 admits exactly three triples: checker/total/authoritative, detector/partial/candidate, and manual/none/manual. Mechanical evaluators also name a known-failure test. A checker cannot claim total authoritative coverage until a planted failure proves that the check can fail and the contract names the class it covers.

## Enforcement classification boundary

Version 1 classifies each evaluator-backed obligation, not its enclosing declaration. One rule may therefore contribute assignments to several enforcement classes. Evaluator-backed predicates of procedures and operations use the same classes, so a manual or detector-backed predicate cannot disappear behind an execution boundary. A predicate without an evaluator reference remains executable predicate logic owned by procedure or operation execution.

`EnforcementClass` is the closed enumeration `mechanical`, `assisted`, and `deliberative`. `derive_enforcement_class(evaluator)` maps only the three admitted evaluator triples to this enumeration. The function rejects any other triple instead of guessing from one field. For a checker, the declared contract must also name at least one known-failure fixture, as required by the evaluator schema.

The resulting class is a *declared classification*. The class does not prove that an evaluator can run or that its claims have passed their assurance gate. Static filtering alone must not remove an obligation from agent attention or authorize an attention packet.

Three frozen locator types preserve the source distinction:

- `RuleCriterionEnforcement(declaration, criterion, evaluator, enforcement)` identifies one rule-local criterion
- `ProcedurePredicateEnforcement(declaration, phase, predicate, evaluator, enforcement)` identifies one evaluator-backed predicate, where `phase` is `precondition`, `invariant`, or `postcondition`
- `OperationPredicateEnforcement(operation, predicate, evaluator, enforcement)` identifies one precondition on an exact operation reference

These locators do not copy criterion statements, predicate expressions, or evaluator contracts. Callers recover those objects from the catalog, which remains their authority.

`DeclarationCatalog.filter_enforcement(enforcement)` returns all three locator types from live records. Rule and procedure declarations follow identifier order. Rule criteria retain authored order. Procedure predicates follow phase order—preconditions, invariants, then postconditions—and authored order within each phase. Operation contracts follow exact `(identifier, version)` order, and their preconditions retain authored order. Unversioned locators precede operation locators, matching the catalog's existing record traversal. A declaration or operation with obligations in two classes appears in both corresponding results. An obligation without an evaluator reference appears in none. The operation is static: it classifies every authored evaluator-backed obligation without evaluating applicability.

The attention planner intersects rule locators with final projected criteria and procedure locators with final effective procedure components. The planner expands an operation locator once for each action of an effective procedure that invokes that exact operation. The expanded completion key is `(procedure identifier, action identifier, operation reference, predicate identifier)`. Thus, two actions that invoke one operation contract receive distinct evidence records, even when they share bindings.

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

### Attention planner boundary

Resolution uses one exact registry. The planner must correlate every effective
obligation with that registry. Three candidate roots fail this criterion:

- a catalog field changes a portable query view into an authorization object
- a separate planning context duplicates the successful resolution result
- a public catalog locator lacks issuance authority

`ResolutionResult` consequently retains the exact `DeclarationRegistry` and carries a private
process-local resolver stamp. The planner checks the stamp before reading the
result. A private canonical enumerator reads authored obligations through a
neutral read-only interface. The interface supplies unversioned records and
exact evaluator or operation lookup. One adapter reads the resolution registry;
another reads the live catalog mappings. Both the planner and
`DeclarationCatalog.filter_enforcement` project from this enumerator, so a new
obligation kind or procedure phase cannot enter only one surface. The enumerator
supplies no issuance authority. Planner authority comes from the stamped result
and its registry adapter.

The resolver stamp protects the ordinary public construction boundary. Hostile
Python code can still inspect private attributes. The planner independently
checks the structures consumed from the result against the retained registry.
The checks cover every resolved coordinate and each referenced declaration or
exact contract.
The stamp establishes process-local provenance. The structural checks establish
agreement with the source authority.

Three public obligation-key types identify concrete work:

- `RuleCriterionKey(declaration, criterion)` identifies one effective rule
  criterion
- `ProcedurePredicateKey(declaration, phase, predicate)` identifies one
  predicate of an effective procedure
- `OperationPredicateKey(procedure, action, operation, predicate)` identifies
  one operation precondition expanded for one effective procedure action

The keys contain no copied evaluator or enforcement class. A two-stage API
prevents callers from duplicating the planner's key derivation. First,
`derive_attention_requirements` returns a privately issued
`AttentionRequirements`. Each runnable requirement states:

- its canonical key
- its evaluator and enforcement class
- its evaluator-input operation
- the admitted revisions
- the input schema

The runner binding owns the evaluator-input operation. The evaluator-input
operation differs from the subject operation named by an expanded operation key.
The requirements aggregate retains the exact resolution result and each runner
registry needed by its effective classes.

Second, `plan_attention` accepts the issued requirements and one
`EvaluatorInput(input_revision, input_data)` for each runnable requirement.
Missing input leaves runnable work undefined, so missing input blocks
the plan. Additional input indicates a stale or incorrectly scoped plan.
Additional input also blocks the plan. The planner freezes each
supplied JSON object. The admitted revisions must contain the supplied revision.
The frozen object must satisfy the bound input schema.
The resulting `EvaluatorInvocation` states four values:

- the exact evaluator
- the evaluator-input operation
- the admitted revision
- the immutable input

One privately issued `AttentionPlan` retains the exact requirements, resolution
result, and readiness authorities. The resolution trace remains on the
resolution result. No packet copies the trace. No completion operation accepts
a resolution event as evidence. The packet entries have distinct
information boundaries:

- a deliberative entry contains the complete selected obligation and the exact
  immutable `EvaluatorDeclaration` for its manual evaluator
- an assisted entry contains the complete selected obligation, a validated
  detector invocation, and the detector's residual question
- a mechanical entry contains only the obligation key, a validated checker
  invocation, and the evaluator's evidence schema

Three normalized snapshots retain declaration values rather than prose
reconstructed by the planner:

- `RuleObligationSnapshot` retains the rule axis, failure mode, visibility
  requirement, title, rationale, selected criterion, and referenced effective
  norms
- `ProcedureObligationSnapshot` retains the purpose, title, rationale,
  parameter schema, effects, failures, phase, and selected predicate
- `OperationObligationSnapshot` retains the procedure purpose, parameter
  context, action, exact operation input schema, effects, failure outcomes,
  recovery rule, and selected predicate

One test binds an operation input to a declared procedure parameter. A
manual-only test uses a non-trivial evidence schema. That test checks every
evaluator field needed to produce ledger-admissible evidence. The future ledger
validates manual evidence against this retained evaluator contract.

Packet order follows the resolved component order. Rule criteria keep authored
order when the final criterion projection selects them. A procedure contributes
obligations in this order:

1. procedure preconditions in authored order
2. each action in authored order, followed by that action's operation
   preconditions in authored order
3. procedure invariants in authored order
4. procedure postconditions in authored order

Each obligation enters the packet for its derived class. Its relative place in
that packet remains unchanged. Empty packets are valid.

Mechanical requirements need an exact checker registry. The checker registry
uses the same builder-issued boundary as the detector registry: public
construction, copying, serialization, and reconstruction fail. Checker
execution validates its private stamp before reading any mapping. Mechanical
plan issuance additionally needs the exact fixture index and the exact
`KnownFailureAssurance` issued for that index, the checker registry, and the
resolution registry. The planner validates the assurance stamp. Each retained
object must have the required identity. Each checker entry must match its
current authored fixture sequence. Every fixture digest is rechecked.

Assisted requirements need a builder-issued detector registry whose declaration
registry is the resolution registry. Every effective assisted evaluator must
have an exact binding. The final plan retains that registry for comparison with
later `DetectorExecution` evidence. The completion ledger requires the exact
assisted entry to match the retained registry identity and invocation values.
This match covers the evaluator reference, input revision, and immutable input.
The ledger also associates the execution with that entry's obligation key. One execution cannot discharge another key unless a
later contract defines an explicit sharing rule.

Mechanical evidence does not accept a caller-supplied `CheckerResult`. A
procedure evidence transaction or rule evidence transaction invokes the checker
through the exact registry retained by the plan, validates the result through
`execute_checker`, and records the validated value before ledger construction.
This route makes a public result carrier insufficient as evidence. The plan
retains the exact checker registry, fixture index, assurance, and detector
registry used to issue it. Each authority is present only when its corresponding
packet is non-empty. Immediately before and after a mechanical invocation, the
evidence transaction revalidates the assurance stamp and every retained identity.
It also compares the authored fixture sequences and rechecks their digests. A
stale resource prevents evidence issuance. The ledger imports only authenticated
evidence and never invokes an evaluator. Tests mutate a fixture after plan
issuance and prove that no stale evidence reaches the ledger.

`ResolutionResult`, `AttentionRequirements`, and `AttentionPlan` use private
process-local issuer stamps. Their public constructors fail. Every ordinary
reconstruction route also fails, including copying and serialization.
All three aggregates additionally use module-owned weak identity records with
opaque tokens and complete issuance snapshots. Their validators compare the
external token and state with the current graph before any consumer reads it;
rewriting an embedded state cannot attest a mutation.

The weak authority store is identity-indexed and never hashes or compares an
aggregate. It maps `id(aggregate)` to the aggregate's weak reference, opaque
token, and issuance state under one module lock. Validation requires both the
integer key and `stored_reference() is aggregate`. The weak-reference callback
removes the entry only when the stored reference is the callback's own reference,
so delayed collection cannot delete a later object that reuses the integer
identity. This representation preserves `ResolutionResult` semantic equality,
admits traces containing unhashable JSON values, and gives distinct but
semantically equal results independent issuance records. The same store shape is
used for requirements and plans to keep the authority mechanism uniform.

The resolution snapshot covers the `ResolutionResult` carrier and issuer;
registry origin and facet-registry issuance state; resolved-unit carrier and
manifest; ordered component tuple and every component carrier, declaration,
version, and declaration kind recovered from the exact registry; dependency and
rule-projection tuple carriers, member carriers, and semantic values; trace
carrier; and ordered event tuple, event carriers, and event values. Equal-value
replacement of the unit, component tuple, one component, dependency, rule
projection, trace, event tuple, or one event invalidates the result. Adding,
removing, reordering, or replacing an effective procedure—including one with no
obligation—therefore invalidates every downstream attention authority.

The requirements snapshot covers the exact resolution authority; canonical
completion tuple; every requirement, key, obligation snapshot, evaluator, and
enforcement value; every class-specific projection and its correlation to the
canonical tuple; mapping and tuple carrier identities; canonical order; and
frozen semantic values. The plan snapshot adds each packet carrier and entry;
evaluator invocation; input and evidence schema; residual question; checker and
detector registry origin, issuer, binding, runner identity, and contract state;
fixture-index authority; and known-failure-assurance authority. Executable
callables contribute identity but not mutable internal state. Equal-value
replacement of any top-level projection or nested authority invalidates the
aggregate.

`ResolutionResult` preserves semantic equality over its unit and trace. Its
retained registry, issuer stamp, token, and authority state do not participate in
that equality, and authorization never relies on semantic equality. These
cooperative boundaries do not resist hostile access to private Python
attributes.

An empty effective class requires no authority for that class. Supplying a
checker registry for an empty mechanical requirement set is an error. Supplying
a detector registry for an empty assisted set is also an error. Likewise, an
empty mechanical packet rejects a fixture index or known-failure assurance. A
resolution with no evaluator-backed obligation still issues one plan containing
three empty packets. Any mismatch in planning inputs or authorities raises
`AttentionPlanningError`; no partial aggregate is issued. Tests cover
no-evaluator, manual-only, mechanical-only, and assisted-only plans.

### Detector runner boundary

The detector boundary must preserve the semantic distinction between authoritative checking and candidate detection. Three designs were considered. Extending `CheckerRunnerRegistry` would let partial candidate producers enter a registry whose name, result states, and assurance contract promise authoritative decisions. A fully independent detector implementation would preserve that distinction but duplicate exact-reference, operation-contract, ordering, and callable validation. A public generalized evaluator registry would expose combinations that version 1 does not admit. Therefore, version 1 uses separate public checker and detector façades over one private runner-registry validator.

The detector façade consists of `DetectorRunner`, `DetectorRunnerBinding`, `DetectorRunnerRegistry`, and `build_detector_runner_registry`. A binding contains one exact detector reference, one exact operation reference, and one synchronous reviewed callable. The builder sorts bindings by evaluator identifier and version, then operation identifier and version. The builder rejects duplicate evaluator references, unresolved or wrong-kind contracts, checker and manual evaluators, and unsupported callables with detector-specific located registry errors. The resulting mappings are immutable and retain the exact declaration registry object. Checker binding types, builder entrypoint, ordering, validation diagnostics, and valid builder-produced execution behavior remain unchanged while the builder delegates structural checks to the same private validator. Direct construction and reconstruction of the checker aggregate become invalid.

`DetectorRunnerRegistry` is a process-local, builder-issued aggregate. Its public constructor, copying, serialization, and reconstruction fail. A private stamp authenticates the builder, and the later planner validates that stamp and compares the retained declaration registry with `is`. Therefore, an ordinary caller cannot establish detector readiness through the public construction boundary. This cooperative process-local provenance check does not resist hostile Python introspection of private attributes. The stronger ordinary-API boundary is necessary because assisted readiness has no known-failure assurance equivalent.

Binding readiness authenticates only the exact process-local callable object and the synchronous signature observed when the registry was built. A mutable callable or closure remains inside the reviewed, code-owned trust boundary; registry authenticity does not prove its later behavior. The detector executor must validate every returned result independently and must never treat registry authenticity as result evidence.

A detector callable returns `DetectorResult`, a frozen value containing its exact evaluator reference, input revision, and evidence. It has no `satisfied` or `violated` state because partial candidate evidence cannot decide an obligation. A successful run may report zero candidates; the evaluator's evidence schema defines its output. Version 1 detector declarations require `failure-behavior: block`; `candidate` and `record` remain unavailable until their exception, evidence, and ledger semantics are specified. A runner exception therefore blocks detector execution. Registration validates only bindings and callable shape. The later detector executor will freeze and validate the input, exact identity, admitted revision, and evidence schema before it admits a result.

The detector-registry implementation applies the blocking invariant as one atomic contract migration. It updates the normative declaration schema, the persisted catalog schema, every valid detector fixture, source-boundary and persisted-index negative cases for both rejected alternatives, and any affected generated or golden catalog artifact. Both schemas require `failure-behavior: block` when `evaluator-kind` is `detector`; the registry cannot close while either boundary still admits `candidate` or `record`.

The builder-issued registry establishes binding readiness only. It does not establish that a callable returns `DetectorResult` or produces contract-valid evidence. Therefore, this bounded registry step does not authorize runnable assisted work, issue an assisted packet, or execute a detector. The dependency order is detector registry, detector executor, then packet planner. Packet planning will receive concrete inputs separately, validate them against the bound operation contract, and include the invocation together with the residual question. Detector execution and residual judgment will later contribute distinct records to the completion ledger.

### Detector execution boundary

`execute_detector` receives one builder-issued detector registry, one exact evaluator reference, one admitted input revision, and one input object. It validates the registry stamp before reading its mappings. It then requires an exact binding, freezes the input, validates it against the bound operation input schema, and invokes the reviewed callable. A runner exception raises `DetectorExecutionError` at `$.runner`; because version 1 detectors block on failure, no candidate evidence accompanies that error.

The runner returns a public `DetectorResult` carrier. The executor treats its structural fields as untrusted: it requires the carrier type, the invoked evaluator reference, the invoked input revision, object-shaped finite JSON evidence, and evidence that satisfies the evaluator's declared schema. However, the convention that a return means successful detection and an exception means failure remains inside the reviewed, code-owned callable trust boundary. Generic evidence validation cannot detect a callable that mistakenly encodes an internal failure as schema-valid candidate evidence, so the executor does not claim to enforce that behavioral classification.

Successful validation issues a separate process-local `DetectorExecution`. This aggregate retains the exact builder-issued registry, evaluator reference, input revision, frozen input, and immutable validated evidence. Its public constructor, copying, serialization, and reconstruction fail, and an execution-owned stamp authenticates it for the later ledger. A private validator checks type and stamp identity. The ledger must use that validator and compare registry identity with `is`; a bare `DetectorResult` never counts as completion evidence. As with the registry stamp, this cooperative boundary prevents ordinary public reconstruction but does not resist hostile introspection of private Python attributes. Zero candidates remain a successful schema-valid execution, while a runner exception produces no aggregate and remains a blocking diagnostic.

Checker and detector execution share private input-freezing, operation-schema, and evidence-freezing helpers. Each public façade supplies its own error factory and result-specific checks, so reuse cannot change checker exception types, paths, expected-state validation, or messages. The shared regression matrix covers non-object, cyclic, and operation-invalid inputs; runner exceptions, including an exception whose string conversion fails; non-object, cyclic, and schema-invalid evidence; and post-return mutation isolation. Each façade also tests its own registry authority and result-specific fields. Detector tests cover an unstamped registry, a missing binding, an inadmissible revision, runner mutation attempts, wrong result type, evaluator and revision mismatch, and aggregate construction, copying, serialization, stamp, and identity.

Resolution and completion use separate ledgers. Events such as `declaration-evaluated`, `declaration-excluded`, `norm-removed`, and `norm-substituted` explain selection, exclusion, and final norm projection. Resolution events never count as completion evidence.

The completion ledger contains one record for every criterion of every effective rule, every predicate of every effective procedure, and every operation precondition expanded per effective procedure action. Evaluator-less predicates receive evidence from procedure or operation execution. Evaluator-backed obligations also record their enforcement class. Ledger completion states are `satisfied`, `violated`, `blocked`, `unchecked`, and `inapplicable`. This ledger enumeration is distinct from `EvaluationState`: an evaluator may return only `satisfied`, `violated`, or `blocked`. A ledger record becomes `inapplicable` only after a declared procedure terminal closes the realized path and excludes that requirement. `unchecked`, `violated`, or `blocked` prevents successful completion. The only other terminal non-blocking exception is an explicit migration baseline that names the finding, owner, expiry condition, and migration it awaits; a baseline cannot be created silently by a run under evaluation.

### Rule evidence boundary

Rule criteria require an authenticated evidence transaction before completion
reconciliation. The rejected alternative makes the completion-ledger builder
execute evaluators. That route combines evidence acquisition, retry semantics,
authority revalidation, reconciliation, timestamping, and issuance in one
transaction. The accepted route adds a single-use `RuleEvidenceSession` and
keeps the ledger builder free of evaluator callbacks.

`create_rule_evidence_session(plan)` accepts one exact issued `AttentionPlan`.
The session selects only `RuleCriterionKey` requirements, in their relative
order within `plan.requirements.completion`, and correlates them with the exact
packet entries and evaluator authorities retained by that plan. A module-owned
weak claim permits one session for that plan without retaining an otherwise
unreachable plan. The session state is `ready`, `running`, `completed`, or
`failed-after-execution`. It enters `running` before the first detector, checker,
or residual-provider call. Every later exit is terminal and non-retryable.

`execute` accepts
`manual: Mapping[RuleCriterionKey, RuleManualJudgmentSubmission]` and
`residual_providers: Mapping[RuleCriterionKey, RuleResidualJudgmentProvider]`.
It atomically claims the session and enters `running` before traversing either
caller mapping or inspecting a provider signature. It snapshots each mapping
once, retaining the mapping-origin identity only as provenance of that capture.
Their required keys are respectively the deliberative and assisted
rule-criterion keys. Missing, additional, copied-equal, or wrong-kind keys fail
the session; mutable mappings are never traversed again. After the snapshot,
changes to the caller's containers are irrelevant and neither change execution
nor invalidate completed evidence. Session authority covers only the immutable
captured key identities, submission carriers until canonicalization, and
provider callable identities. Mechanical criteria require no caller-supplied
result. An empty rule set issues empty rule evidence without invoking a callback.

`RuleManualJudgmentSubmission` contains an exact `RuleCriterionKey`, evaluator
reference, admitted input revision, and evidence object. The session freezes the
evidence and validates it against the retained manual evaluator before deriving
the state from the canonical conclusion field. `RuleResidualJudgmentRequest` is
privately issued with the exact `CompletionRequirement`, residual question, and
issued `DetectorExecution`. `RuleResidualJudgmentSubmission` contains schema
version 1, that exact request object, an `EvaluationState`, and a non-empty
rationale. `RuleResidualJudgmentProvider` accepts the request and returns that
submission.

`RuleEvidenceRecord` is the closed union of `RuleManualEvidence`,
`RuleAssistedEvidence`, and `RuleMechanicalEvidence`. Every variant retains the
exact source requirement and state. The manual variant retains the validated
submission. The assisted variant retains either its issued detector execution
and residual judgment or a blocking diagnostic. The mechanical variant retains
either its validated `CheckerResult` or a blocking diagnostic. No variant admits
a caller-supplied state independent of its evidence.

Each successful record owns canonical carriers. `RuleManualEvidence` retains a
new submission with a copied key and evaluator reference and frozen evidence,
not the caller's submission object. A residual judgment is reconstructed after
validation with schema version 1, its exact privately issued request, the
validated state, and rationale. `RuleAssistedEvidence` retains that canonical
judgment together with the exact issued `DetectorExecution`; copying the
execution would destroy its authority. `RuleMechanicalEvidence` retains a new
`CheckerResult` with a copied evaluator reference and frozen evidence, not the
runner-returned result object.

The record variants exclude contradictory states. A successful assisted record
has an execution and judgment and no diagnostic; its blocking form has blocked
state, no execution, no judgment, and a non-empty diagnostic. A successful
mechanical record has a result and no diagnostic; its blocking form has blocked
state, no result, and a non-empty diagnostic. A manual record always has its
canonical submission and no diagnostic.

A deliberative rule record validates one `RuleManualJudgmentSubmission` against
the exact manual evaluator and its canonical conclusion schema. An assisted
record executes the retained detector invocation, then requests one residual
judgment correlated with that exact issued execution. A mechanical record
executes the retained checker invocation through the plan's checker authority.
Detector or checker runner and result failures produce blocked records only
after authority revalidation. Mechanical execution additionally revalidates the
known-failure assurance and fixture digests before and after each invocation;
fixture staleness takes precedence over a simultaneous checker failure. The
transaction continues after a valid blocked record and produces one record for
every effective rule criterion.

Residual-provider signatures are validated from the captured callable objects.
After every ordinary or interrupting mapping traversal, signature inspection,
detector call, or residual-provider call, the session revalidates structural
plan and captured mapping authority before classifying the callback outcome. A
structural defect takes precedence over the callback's evidence failure. After a
checker call, the session revalidates both structural authority and fixture
freshness; either authority defect takes precedence over the checker outcome.

Every exception after the session enters `running` publishes
`failed-after-execution` with no `RuleEvidence`, and no later callback runs. An
ordinary exception is exposed as `RuleEvidenceError` after publication. A
`BaseException` outside `Exception`, including `KeyboardInterrupt`, publishes the
same terminal state and is re-raised unchanged. Replacing a provider, submission,
or key inside the private session snapshot is an authority failure even when the
replacement is equal or would return the same result. Replacing an entry in the
original caller mapping after its one traversal is not an authority change.
When initial traversal raises or interrupts, no complete mapping snapshot exists;
the session revalidates structural plan authority, publishes the terminal state,
then applies the same ordinary-exception or `BaseException` rule.

`RuleEvidence` is a privately issued, immutable, process-local aggregate. It
retains the exact plan and a typed record for every rule criterion. Its external
weak issuance record covers the plan, canonical requirement and packet-entry
correlations, canonical source record carriers, result values, and diagnostics.
Caller mapping origins, submission carriers, provider carriers, and provider
callable identities are session-only authorities and are not retained after
successful issuance. Therefore, later mutation of a provider or caller mapping
does not invalidate completed evidence. Public construction, copying,
serialization, token replacement, embedded-state replacement, and equal-value
record-carrier substitution cannot establish authority. The completion ledger
imports these records without re-executing or revalidating their judgments.

### Completion ledger boundary

The ledger receives its record universe from the attention planner. The ledger does not
enumerate the registry again. `AttentionRequirements` retains one canonical
tuple of `CompletionRequirement` values. Each value contains the obligation key,
the complete obligation snapshot, and either both an exact evaluator contract
and its enforcement class or neither field. The latter form identifies an
evaluator-less predicate. The tuple follows resolved component order and the
within-component order defined for attention planning. The three class-specific
requirement tuples and packets are projections of this tuple. Thus, the
canonical tuple retains evaluator-less predicates and the global interleaving
that the three packets cannot represent.

`build_completion_ledger` receives the exact issued plan, an optional exact
`RuleEvidence`, a mapping from effective procedure identifier to procedure
outcome, and a clock. The builder snapshots the procedure mapping exactly once.
Its admitted value union contains an authentic terminal
`ProcedureExecutionTranscript` or authentic, complete, uncleared
`PreActionEvidence`. An uncleared pre-action aggregate preserves actual violated
or blocked entry evidence when lifecycle execution cannot begin. A cleared
pre-action aggregate without its terminal transcript is invalid because it
would permit a caller to stop before lifecycle execution. Every supplied
outcome must originate from the exact attention plan and must name its mapping
key. Additional, duplicate, copied-equal, malformed, or cross-plan outcomes
raise `CompletionLedgerError`.

The outcome mapping is sparse. An omitted effective procedure produces
unchecked records and an incomplete procedure outcome, including when that
procedure declares no obligation. A transcript imports its exact retained entry
evidence, lifecycle boundary evidence, applicability, graph disposition, and
adjudication disposition. An uncleared pre-action outcome imports its exact
precondition records and leaves every later lifecycle requirement unchecked.
No outcome may be supplied for a declaration that is not an effective procedure.
The builder discovers effective procedure identifiers from the plan's issued
resolution authority, not from the supplied mapping and not only from the
requirement tuple.

The first ledger prerequisite implements only this canonical tuple. Until an
admissible execution path exists, evaluator-less requirements can produce only
`unchecked` records. An operation result does not prove its precondition. The
result cannot bind an invocation to its procedure action and frozen input.
Moreover, the public result omits the observed context and evaluated predicate.

The first observation boundary covers evaluator-less procedure preconditions
at procedure occurrence zero. One builder-issued `ObservationProviderRegistry`
binds a reviewed synchronous batch provider to the exact declaration and facet
registries of the prepared run. The observer selects the canonical evaluator-less
precondition requirements from that run and derives the minimal facet request
recursively from their predicate expressions. Descriptive `observes` fields do
not determine the request. An empty requirement tuple issues empty evidence
without invoking the provider.

The provider request exposes only the boundary coordinate, selected facets, and
immutable procedure parameters. The request excludes the run plan and every
authority object. One provider call returns the complete boundary snapshot. The
observer traverses the result once, freezes its present values, and validates
them through the exact facet registry. Absent requested facets produce the
declared strong-Kleene result. Any malformed or additional result aborts issuance.
Invalid JSON structures and hostile provider behavior belong to this failure
class.

The privately issued aggregate retains its exact authorities, canonical
requirement correlations, and predicate results. The aggregate stores no second
context mapping because each atomic trace already carries its observation. The
evidence validator reconstructs one transient context across every trace,
rejects cross-trace disagreements, and replays each canonical predicate against
that shared context. Consequently, an accepted aggregate cannot combine
evidence from two snapshots. False and unknown remain evidence values. Neither
value maps to a completion state or authorizes procedure entry at this boundary.

The evaluator-backed procedure-precondition input boundary is now correlated,
and the pre-action evidence session evaluates those preconditions before it
derives clearance. The lifecycle contract below fixes the later invariant,
postcondition, and per-action operation-precondition boundaries. Each boundary
preserves five separate authorities:

- an observer acquires context
- an evaluator decides a predicate
- an authorizer permits a transition
- an executor performs an action
- a completion adjudicator closes the run

`execute_operation` remains a low-level exact-contract runner. The runner accepts only a
builder-issued, process-local operation registry and validates inputs and
results, but the runner does not claim to enforce procedure or operation preconditions.
Only the procedure executor defined below may consume a prepared procedure run and
interpret an operation invocation as part of precondition-gated semantics.

`prepare_procedure_run` establishes the preflight authority for that future
executor. The builder accepts the issued attention plan, the effective procedure,
the validated parameter object, and the builder-issued operation registry tied
to the same declaration registry. The resulting process-local plan retains those
exact authorities, every procedure-specific completion requirement in canonical
order, and every authored action with its exact operation contract and frozen
bound input. The plan projects executable and broad pre-action tuples, plus
exact procedure-precondition and evaluator-backed procedure-precondition tuples,
from the authoritative requirements. The broad pre-action tuple also retains
invariants and per-action operation preconditions for their later boundaries.
These projections do not mutate the authoritative tuple. Consequently, every
postcondition remains available. Preflight stops before runner invocation and
evidence issuance.

### Evaluator-backed precondition inputs

`plan_procedure_precondition_evaluations` prepares the evaluator-backed
procedure preconditions at the pre-action boundary. Version 1 fixes the phase to
`precondition` and the occurrence to `0`. The plan includes each evaluator-backed
procedure precondition in canonical requirement order. It does not include an
invariant, a postcondition, or an operation precondition.

A manual precondition retains its complete deliberative entry and requires no
input provider. Each assisted or mechanical precondition requires exactly one
provider under its canonical obligation key. Missing, additional, copied, or
non-canonical key authority is rejected. Provider-map order does not change the
canonical record order. The provider receives only the procedure
identifier, boundary coordinate, immutable run parameters, and selected
predicate. Its result must use the revision and input already admitted by the
attention invocation. The input is frozen again and validated against the exact
evaluator-input operation schema. The provider derives an input; it does not run
the detector or checker.

Procedure preflight materializes detached canonical parameters, predicates,
invocation inputs, and input schemas. Their carrier identities, scalar fields,
references, and frozen contents participate in run authority. Provider-facing
evaluation specifications consume only these detached canonical values. Each
provider request receives a further detached key and predicate. Consequently, a
provider cannot mutate the stored canonical input, and a later change to a live
attention or declaration mapping cannot become the provider input. Live
requirements, packet entries, registries, and declarations remain correlation
and diagnostic authorities. The records retain their exact live requirement and
packet-entry carriers, while repeated validation prevents a plan containing
stale correlations from being issued.

The run authority also binds the exact attention plan, operation-runner
registry, procedure and operation declarations, evaluator contracts, authored
action bindings, requirement partitions, packet entries, and evaluator-input
operation contracts. Mapping reads occur behind the public planning-error
boundary. After semantic reads, a callback-free pass rechecks carriers, scalar
values, transitions, references, and runner identities. A changed authority, or
a provider side effect that changes retained authority or a validated
correlation, aborts issuance.

The resulting `ProcedurePreconditionEvaluationPlan` is a process-local
correlation plan. It retains separate manual, assisted, and mechanical records,
the detached parameters, the exact provider mapping, and each detached
validated evaluator input returned during planning. It executes no
evaluator, makes no predicate judgment, records no completion evidence, and
grants no clearance. `create_pre_action_evidence_session` creates one
process-local transaction session from the
correlation plan and an issuer-stamped evaluator-less observation aggregate,
including an empty aggregate when that class has no requirements. The session
validates every authority and exact submission key set before execution. It then
executes each detector once, passes the issued execution to the corresponding
injected residual-judgment provider, validates the returned judgment, and
retains both records atomically. It executes each checker once through the
retained authority and detached evaluator input. Clearance is derived from the
combined evaluator-less, manual, assisted, and mechanical results and is true
only when every precondition is satisfied.

The completed aggregate contains one typed record for every item in
`run.procedure_precondition_requirements`, in that exact canonical order
regardless of submission-mapping order. Evaluator-less records retain the exact
requirement, mapped state, and predicate trace. Manual records retain the exact
requirement, state derived from `conclusion`, and frozen evidence. Successful
assisted records retain the exact requirement, residual state, issued
`DetectorExecution`, and frozen residual judgment. A detector runner or result
failure instead retains the exact requirement, `blocked` state, and diagnostic,
with no residual judgment. Successful mechanical records retain the exact
requirement, checker state, and validated `CheckerResult`; a checker runner or
result failure retains the exact requirement, `blocked` state, and diagnostic.
Blocked runner or result records do not abort the batch, so later canonical
preconditions are still evaluated. Only authority, correlation, or submission
failures terminate a running session. The transaction derives `cleared` only
after this complete tuple exists, and sets it exactly when every record is
`satisfied`.

Manual submissions and residual providers use separate exact key sets derived
from the correlation plan. A missing or additional key fails before `running`,
and mapping order has no semantic effect.

The session is single-use per exact `ProcedureRunPlan`; issuing a second
evaluation plan cannot reclaim the same run. A module-owned weak claim preserves
that ownership without retaining an unreachable run graph. Factory claims and
execution claims are atomic under separate locks, while callbacks execute
without either lock held. Its state is `ready` during pre-execution validation
and changes to `running` before the first evaluator invocation or residual
provider callback. A reentrant execution attempt therefore fails. Every exit
from `running` is terminal: either `completed`, with one immutable evidence
aggregate, or `failed-after-execution`, with no retry permitted. A validation
failure detected before `running` leaves the session `ready`. Thus, a stale
authority found after a runner call cannot lead the same session to invoke that
runner twice. A caller that needs a new attempt must prepare a new run and new
observation and evaluation plans. The completed aggregate retains all
precondition evidence for later completion. The completion ledger consumes
these records and never executes a retained precondition evaluator again.
State and evidence publish as one immutable control snapshot, so an interrupted
completion cannot expose evidence from a failed session.

### Procedure lifecycle execution boundary

`ProcedureExecutionSession` is the only high-level authority that assigns
procedure semantics to operation results. Its factory accepts exact issued
`PreActionEvidence` whose `cleared` value is true and the exact observation
provider registry of the run. The factory atomically installs one module-owned
weak claim on the retained `ProcedureRunPlan`. The claim stores an opaque token,
not the session, and survives session collection and every terminal result while
the run remains reachable. A second session for that run fails before any
callback. A separate per-session claim rejects concurrent or reentrant execution.

The lifecycle state is `ready`, `running`, or `terminal`. Callback-free authority
and provider-map validation may fail while the session remains `ready`. The
session snapshots each custom provider mapping exactly once while it owns the
execution claim, because mapping traversal can execute Python code. It validates
exact provider keys over the canonical evaluator-backed lifecycle universe:
procedure invariants, procedure postconditions, and operation preconditions
expanded per action. This universe excludes procedure-entry evidence and rule
criteria. The session enters `running` before the first observation, manual,
residual, detector, checker, or operation callback. Every exit after that
transition is terminal and non-retryable, and no callback runs after an abort.
Locks protect only claims and publication; no lock is held across a callback.

Each emitted boundary has a monotonically increasing `occurrence`, starting at
zero. The occurrence is the actual execution-boundary ordinal, not the authored
action index or predicate occurrence. An `action` boundary names the exact
prepared action and operation. One coherent provider snapshot evaluates every
evaluator-less procedure invariant and every evaluator-less precondition of that
operation occurrence. The first action boundary is also the initial invariant
check. Every enforcement class at the boundary must be `satisfied` before the
operation runner is invoked. A `violated` or `blocked` record aborts authorization,
publishes the complete boundary evidence, and invokes no operation.

After a declared operation result, the session selects the authored transition
without an external callback. A transition to another action emits the next
action boundary. That boundary is simultaneously the post-previous and pre-next
invariant checkpoint. A transition to a terminal emits a `terminal` boundary.
That boundary observes every invariant and, for a success terminal, only the
reached postcondition. A failure terminal selects no postcondition. The issued
terminal evidence retains the predecessor action, exact operation, validated
operation result and declared outcome, selected transition, and terminal
identifier. Therefore, convergent paths remain distinguishable even when they
reach the same terminal.

The provider-facing lifecycle request exposes only the procedure identifier,
boundary kind and ordinal, immutable parameters, requested facets, and the
minimum boundary coordinate. An action request includes the action identifier
and exact operation reference. A terminal request includes the terminal
identifier. The privately issued boundary evidence retains the fuller authority
correlation described above. Concrete manual and residual judgments are not
supplied before execution. Their exact providers are selected from the validated
maps only after a boundary is realized. Each request carries the exact boundary
coordinate and requirement, and each returned judgment must match both. The
same invariant provider may therefore be invoked once at each realized
occurrence. Mechanical assurance freshness is rechecked at each mechanical
occurrence; retained procedure-entry evidence is never rerun.

Evaluator timing states the earliest boundary at which an evaluator may run,
ordered as `pre-design`, `pre-action`, `post-action`, and `post-artifact`.
An action boundary admits `pre-design` and `pre-action`; a terminal boundary
also admits `post-action`. `post-artifact` is outside procedure lifecycle
execution. This cumulative interpretation lets one invariant evaluator serve
both its action and terminal occurrences without weakening its earliest-run
constraint. The lifecycle factory validates the timing of every selected
evaluator before it installs the run claim.

Procedure preflight retains entry-evaluation authority and lifecycle-evaluation
authority as separate projections. The lifecycle projection covers every
evaluator-backed procedure invariant, procedure postcondition, and operation
precondition expanded to an action. One canonical tuple contains a closed union
of manual, assisted, and mechanical specifications; class-specific subsets are
derived instead of retained as competing sources. Every variant retains its
canonical requirement ordinal, the live source-key, requirement, and packet-entry
identities, a detached requirement and evaluator contract, and its enforcement
class. An assisted variant additionally retains a detached invocation, input
schema, and residual question. A mechanical variant retains a detached
invocation, input schema, and evidence schema. The source packet entry serves
only as issuance authority. The execution session consumes the detached
requirement, evaluator, invocation, and schemas, so it does not reconstruct
evaluator authority from the live attention plan after execution begins.

Preflight also captures the detector-registry origin: the registry and
declaration identities, binding-map and contract-map identities, evaluator and
operation references, binding and runner identities, and frozen contract
contents. The session factory revalidates that state and then constructs its
detached executable detector registry. This division matches operation-runner
ownership: preflight establishes the live origin, while the execution factory
selects and freezes the runners that the transcript authorizes.

The session accepts one exact binding map over the supported evaluator-backed
lifecycle keys. A manual binding supplies one manual-judgment provider. An
assisted binding supplies one evaluator-input provider and one residual-judgment
provider. A mechanical binding supplies one evaluator-input provider; the
checker result comes only from the retained checker authority. The map is
traversed once while the session owns its execution claim, then validated by
exact source-key identity and enforcement class. `None` is admitted only when
the required key set is empty.

Every provider request is privately issued after its boundary is realized. A
manual request carries the exact coordinate, detached requirement, and detached
evaluator contract. Its submission retains that exact request, the input
revision, and the evidence object. An assisted input request carries the exact
coordinate and detached requirement. Version 1 treats the invocation recorded
by attention planning as canonical: the returned `EvaluatorInput` must have the
same revision and JSON value and must satisfy the detached input-operation
schema. After detector execution, the residual request carries the coordinate,
requirement, residual question, and exact issued execution. Its submission
retains that exact request, schema version, state, and rationale. Exact request
identity prevents a submission for one invariant occurrence from being replayed
at another occurrence. Boundary-varying evaluator input requires a later
attention-contract revision.

Boundary evidence contains one record for every selected requirement in
canonical run order. Its record union distinguishes evaluator-less observation,
manual evidence, assisted evidence, and mechanical evidence. Each record retains
the detached requirement and the resulting `EvaluationState`. An assisted
detector runner or result failure produces a blocked record with a diagnostic
and no residual judgment. A mechanical checker runner or result failure likewise
produces a blocked record with a diagnostic and no result, but only after the
session revalidates structural authority and fixture freshness. The session then
continues the remaining requirements at that boundary. Every other invalid
evaluator input, manual submission, residual submission, or authority correlation
terminates the evidence transaction. A `complete` flag distinguishes a fully
evaluated boundary from the canonical record prefix published after a later
callback fails. Authorization and terminal acceptance require a complete
boundary whose records are all satisfied.

The factory snapshot also retains the exact detector-registry origin and a
detached detector registry containing its runner identities and invocation
contracts. Detector calls use only the detached registry. Live authority is
revalidated after every provider callback, callable-signature inspection, and
detector call. Thus, a lasting mutation aborts the run, while a transient
binding substitution cannot select another runner. The transcript separately
retains the execution-time binding-map origin, canonical keys, binding carriers,
and callable identities, and its authenticity snapshot covers these authorities
and every nested boundary-evidence carrier.

When the lifecycle contains a mechanical requirement, the factory also retains
the live checker registry, fixture index, and known-failure assurance as origins,
then constructs a detached checker registry for execution. Known-failure
assurance issuance is recorded in a module-owned identity ledger. Rewriting the
assurance's embedded state therefore cannot attest a mutated assurance. The
authority projection covers the checker-registry issuer, bindings, runner
identities, contracts, evaluator records, fixture carriers, and assurance
results. Mutable fields inside a runner remain outside semantic authority.

Fixture freshness is occurrence-scoped. The factory does not read fixture files,
and an unreachable mechanical postcondition does not inspect them. At each
realized mechanical occurrence, the session validates assurance authority and
re-reads the declared fixture digests before input provision, after input
provision, before checker execution, and after checker success, failure, or
interruption. These checks never rerun a known-failure fixture and never rerun
retained procedure-entry evidence. If fixture staleness coincides with a provider
or checker failure, the authority failure takes precedence.

Failure classification distinguishes untrusted evidence from retained authority.
An evaluator-input callback has its own `evaluator-input` stage. A provider that
raises an ordinary exception, returns an invalid carrier, returns the wrong
request, supplies an inadmissible revision or mismatched input, violates an
evidence schema, supplies an invalid conclusion or state, leaves a blank
rationale, or replays an earlier occurrence produces `evidence-aborted`. A
retained run, packet, registry, evaluator, input contract, provider snapshot, or
detached specification that changed or no longer matches its issuance authority
produces `authority-aborted`. A detector runner or result failure becomes a
blocked record only after authority revalidation; a checker runner or result
failure becomes blocked only after both authority and fixture-freshness
revalidation. Any other evaluator-execution error is an authority failure. A
`BaseException` at any callback stage is re-raised only after terminal
publication of the completed record prefix, and no callback runs after an abort.

Every terminal publication atomically couples the lifecycle state with an
immutable transcript. The transcript retains the completed boundary and action
prefix, the exact current coordinate, all retained authorities, and a failure
record when execution did not complete normally. That record identifies the
active stage, including observation, manual judgment, detector, residual
judgment, checker, authorization, operation runner or result, authority, and
interruption. It also retains a diagnostic when one can be produced safely. A
`BaseException` is re-raised only after this terminal snapshot is published.

Two orthogonal fields state the result. `graph_disposition` is
`success-terminal`, `failure-terminal`, or `no-terminal`.
`adjudication_disposition` is `accepted`, `terminal-evidence-rejected`,
`authorization-aborted`, `evidence-aborted`, `execution-aborted`, or
`authority-aborted`. Neither field overrides the other. For example, a reached
failure terminal may pair with rejected invariant evidence, and a reached
success terminal may pair with an interrupted terminal observation. Procedure
success is exactly `success-terminal` plus `accepted`.

Path applicability is assigned only after a declared success or failure terminal
is reached. At that point, requirements of unvisited actions and unselected
postconditions become `inapplicable`. If the session aborts before a graph
terminal, every not-yet-reached requirement remains `unchecked`. An authorization
abort has `no-terminal` and `authorization-aborted`; it publishes the completed
boundary records and leaves the runner uncalled. A runner or result exception has
`no-terminal` and `execution-aborted`. A declared `OperationFailure` instead
follows its authored transition and may reach either another action or a failure
terminal.

Every invariant occurrence remains in the transcript. The invariant's canonical
ledger record aggregates those occurrences as `violated` when any occurrence is
violated, otherwise `blocked` when an actual retained occurrence is blocked,
otherwise `unchecked` when an emitted boundary selected the invariant but its
partial evidence prefix contains no record, and otherwise `satisfied`. Thus, the
precedence is `violated`, `blocked`, `unchecked`, then `satisfied`. A missing
record never asserts blocked evidence. A boundary never emitted after an abort
creates no expected occurrence; its later requirements remain `unchecked`. The
same missing-record rule applies to a reached operation precondition and the
selected postcondition. Their states otherwise come from their retained
occurrence records.
The terminal graph and adjudication dispositions remain separate ledger
authorities: obligation records alone cannot convert a declared failure or an
aborted run into successful completion.

The ledger uses one atomic reconciliation builder. It accepts only a privately
issued plan, optional exact rule evidence, and the once-snapshotted procedure
outcomes. It derives every record from the plan's canonical completion tuple and
imports retained evidence without executing an observation, evaluator, residual
provider, checker fixture, or operation. An additional key, malformed carrier,
invalid authority, invalid evidence correlation, or copied-equal authority
raises `CompletionLedgerError` and prevents issuance. An omitted rule aggregate,
an omitted procedure outcome, or an absent record in a valid partial prefix
instead produces `unchecked` at the affected canonical records. Every issued
ledger contains the complete tuple in canonical order.

Ledger success requires an authentic terminal transcript for every effective
procedure, with `success-terminal` graph disposition and `accepted` adjudication,
and requires every canonical record to be `satisfied` or validly
`inapplicable`. Every `inapplicable` record must be justified by the reached
authored terminal of its procedure. A plan with no effective procedure applies
only the record condition. Therefore, a satisfied rule-only plan succeeds, and
an empty plan succeeds after valid issuance. An uncleared pre-action outcome, a
missing outcome even for a zero-obligation procedure, a failure-terminal or
aborted transcript, or any unchecked, violated, or blocked record prevents
success. Migration baselines remain outside this first ledger contract.

A `ManualJudgmentSubmission` is an untrusted human assertion. The assertion contains the
exact obligation key, evaluator reference, admitted input revision, and evidence
object. The revision identifies the manual evidence protocol used to construct
the assertion and must belong to the retained evaluator's `input_revisions`.
Every manual evaluator authored under declaration schema version 1,
regardless of its evaluator contract version, uses one canonical fragment. Its
root evidence schema has object type, requires a top-level `conclusion` property,
and declares that property's schema as exactly the closed enum `satisfied`,
`violated`, and `blocked`; the enum order has no significance. The source schema
enforces this syntactic contract while the embedded-schema validator validates
the complete evidence schema.

The persisted query index deliberately omits evidence schemas. An index emitted
from validated sources inherits the source guarantee through its provenance,
but a standalone persisted index cannot prove the omitted contract. Therefore,
the catalog revision 1 schema and evaluator query payload remain unchanged. A
future consumer that requires persisted semantic contracts needs a separately
designed index revision rather than a copied summary field.

For procedure preconditions, the pre-action transaction snapshots each manual
submission, freezes its evidence, validates it against the exact manual
evaluator schema retained by the plan, and checks the key, evaluator, and
revision. The transaction derives the state from `conclusion`; the submission
carries no second state that could contradict the evidence. This validation
authenticates the shape and correlation of the assertion. Schema validation does not turn the
public submission into machine evidence. Contract tests plant each malformed
canonical fragment at the source boundary and prove that checker and detector
schemas remain unconstrained by this manual-only contract. The later ledger
imports these precondition records without revalidating their submissions or
deriving their states again. For a manual obligation at a later phase, the
lifecycle session requests and validates the judgment only after its exact
boundary has been realized. The ledger imports that retained record without
repeating the validation.

Assisted completion uses a fixed version 1 residual-judgment contract rather
than applying the detector's evidence schema to a different object. A
`ResidualJudgmentSubmission` contains its schema version, exact obligation key,
detector evaluator reference, admitted input revision, explicit completion
state, and non-empty rationale. One injected provider receives the exact
obligation, residual question, and issuer-stamped `DetectorExecution` after the
transaction has executed the detector. The transaction validates the returned
judgment against that execution and the retained detached invocation. A missing
or mismatched judgment is invalid evidence and terminates the session; no
separately executed detector may be submitted. A detector error located at its
runner or returned-result boundary maps to a blocked assisted record after the
transaction revalidates plan authority, and the residual provider is not called.
A registry, evaluator, revision, input, or correlation error is an authority
failure and terminates the session as `failed-after-execution`.

Mechanical evidence accepts no caller-supplied checker result. Version 1 first
restricts checker failure behavior to `block` at both source and persisted-schema
boundaries. The procedure pre-action, procedure lifecycle, and rule-evidence
transactions invoke their respective checkers through the registry retained by
the plan and in canonical order. Before and after each invocation, the owning
transaction revalidates the assurance stamp, retained identities, authored
fixture sequences, and fixture digests. A stale or unreadable fixture prevents
evidence issuance and takes precedence over a simultaneous runner or result
failure. A validated checker result maps its state directly. A registry stamp,
retained identity, binding, evaluator, revision, invocation input, assurance,
fixture sequence, or digest defect terminates the evidence transaction. After
those checks pass, an error located at the runner or returned-result boundary
produces a `blocked` record with a separate diagnostic. Registry, correlation,
input, assurance, and fixture errors are authority failures, never blocked
evidence. Tests plant both diagnostic classes.

Privately issued executable predicate evidence has a total state mapping.
`true` maps to `satisfied`, `false` maps to `violated`, and `unknown` maps to
`blocked`. An `unknown` result records an attempted evaluation that could not
decide because a required observation was unavailable. An absent execution
record remains `unchecked`. The procedure executor retains the predicate trace
that supports every mapped truth value.

The builder captures the exact injected clock callable before inspecting and
invoking it. It requires an exact synchronous zero-argument callable and
revalidates every source authority after signature inspection. The builder then
calls the captured clock once after evidence reconciliation. The clock must
return an exact aware `datetime` whose UTC offset is zero. The builder normalizes
that value to one canonical RFC 3339 string ending in `Z`, then revalidates the
plan, rule evidence, procedure mapping, and every procedure outcome before
issuance. Every record and the ledger share that transaction timestamp, which
participates in semantic equality. A clock exception, invalid carrier, naive
value, nonzero offset, authority mutation during the callback, or normalization
failure raises `CompletionLedgerError` and prevents issuance. A `BaseException`
propagates with no ledger issued. Tests inject a fixed clock, so identical inputs
remain comparable.

`CompletionLedger` is a privately issued, immutable, process-local aggregate.
Its public construction, copying, serialization, and reconstruction fail. Each
`CompletionRecord` contains its key, optional evaluator and enforcement class,
state, a typed tuple of exact source evidence records, a diagnostic tuple, and
the transaction timestamp. Repeated invariants retain every occurrence record
and every occurrence diagnostic. Unchecked and inapplicable records have empty
source and diagnostic tuples. Detached lifecycle requirements are correlated to
canonical completion requirements by validated semantic keys only after the
transcript authority passes; detached object identity is not expected to match.

The ledger retains the exact plan, optional rule evidence, procedure-mapping
origin, each procedure outcome, canonical records, per-procedure outcome status,
timestamp, and derived success. A module-owned weak issuance record stores an
opaque token and the complete issuance snapshot. Authenticity revalidates each
retained source authority and rejects later mutation, equal-value replacement,
token replacement, and embedded-state self-attestation. Resolution events never
satisfy a record. A future projection may serialize a reviewed ledger, but the
process-local authority itself is not a portable evidence token.

Mechanical results are reported compactly after the purpose check; they do not substitute for it. Assisted obligations require both detector evidence and the recorded residual judgment. Deliberative obligations require manual evidence against the criterion or predicate, not a general assertion that the artifact was reviewed.

Failure mode and enforcement class remain orthogonal. A mechanically checked obligation may belong to a rule whose failure mode still requires a resident trip-wire because the check runs only after an irreversible action. Conversely, a visible prose defect can require deliberative enforcement.

## Consequences

- The canonical declaration owns the evaluator mapping; checker registries and reports refer to its identifier rather than restating the rule.
- Mixed declarations remain visible at obligation granularity rather than receiving one lossy class.
- Declared mechanical capability and proved runtime readiness remain separate facts.
- Query output answers three distinct questions: what must be deliberated, what must be inspected with assistance, and what must be run.
- Agent reports emphasize decisions and residual uncertainty. Checker verdicts occupy one compact evidence block.
- Migration must not classify a fluent but pattern-detectable prose construction as deliberative merely because agents currently check it by reading.
