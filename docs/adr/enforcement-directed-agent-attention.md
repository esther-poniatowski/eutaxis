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

Future mechanical completion does not accept a caller-supplied `CheckerResult`.
The completion operation invokes the checker through the exact registry retained
by the plan, validates the result through `execute_checker`, and records the
validated value inside the ledger transaction. This route makes a public result
carrier insufficient as evidence. The plan retains the exact checker registry,
fixture index, assurance, and detector registry used to issue it. Each authority
is present only when its corresponding packet is non-empty. Immediately before
one mechanical invocation or one atomic batch, completion revalidates the
assurance stamp and every retained identity. Completion also compares the
authored fixture sequences and rechecks their digests. A stale resource blocks
completion under the later ledger contract.
The ledger tests mutate a fixture after plan issuance.

`ResolutionResult`, `AttentionRequirements`, and `AttentionPlan` use private
process-local issuer stamps. Their public constructors fail. Every ordinary
reconstruction route also fails, including copying and serialization. Private
validators check the stamps before reading fields. Authorization compares
retained aggregates by identity rather than structural equality.
`ResolutionResult` preserves semantic
equality over its unit and trace. Its retained registry and issuer stamp do not
participate in that equality, and authorization never relies on it. These
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

The completion ledger contains one record for every criterion of every effective rule, every predicate of every effective procedure, and every operation precondition expanded per effective procedure action. Evaluator-less predicates receive evidence from procedure or operation execution. Evaluator-backed obligations also record their enforcement class. Ledger states are `satisfied`, `violated`, `blocked`, and `unchecked`, with evaluator identity when present, evidence, and timestamp. `unchecked`, `violated`, or `blocked` prevents successful completion. The only terminal non-blocking exception is an explicit migration baseline that names the finding, owner, expiry condition, and migration it awaits; a baseline cannot be created silently by a run under evaluation.

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

The first ledger prerequisite implements only this canonical tuple. Until an
admissible execution path exists, evaluator-less requirements can produce only
`unchecked` records. An operation result does not prove an operation
precondition: the current public result retains neither the procedure action,
the frozen input, the observed context, nor the evaluated predicate. The future
procedure executor must issue process-local predicate evidence. That evidence
must retain the exact declaration registry, procedure, phase or action,
operation reference when present, frozen bound inputs, relevant before-or-after
context, obligation key, predicate trace, and truth value. The procedure
execution contract must first define the observation point for each phase.

`execute_operation` remains a low-level exact-contract runner. The runner accepts only a
builder-issued, process-local operation registry and validates inputs and
results, but the runner does not claim to enforce procedure or operation preconditions.
Only the future procedure executor may consume a prepared procedure run and
interpret an operation invocation as part of precondition-gated semantics.

`prepare_procedure_run` establishes the preflight authority for that future
executor. The builder accepts the issued attention plan, the effective procedure,
the validated parameter object, and the builder-issued operation registry tied
to the same declaration registry. The resulting process-local plan retains those
exact authorities, every procedure-specific completion requirement in canonical
order, and every authored action with its exact operation contract and frozen
bound input. Executable and pre-action tuples are overlapping projections of the
authoritative requirements; neither projection can remove a postcondition from
the authoritative tuple. Preflight issues no observation, predicate verdict,
clearance, operation result, transcript, or completion evidence.

The ledger uses one atomic builder:
`build_completion_ledger(plan, *, manual, assisted, executable, clock)`. The
builder accepts only a privately issued plan and derives every record from its
canonical completion tuple. The builder snapshots each submitted mapping once. An
additional key, malformed carrier, invalid authority, or invalid evidence
raises `CompletionLedgerError` and prevents issuance. Missing evidence instead
produces an `unchecked` record. Every issued ledger contains the complete tuple
in canonical order, including records after a blocked evaluation. The ledger is
successful exactly when every record is `satisfied`. Migration baselines remain
outside this first ledger contract.

A `ManualJudgmentSubmission` is an untrusted human assertion. The assertion contains the
exact obligation key, evaluator reference, admitted input revision, and evidence
object. Every manual evaluator authored under declaration schema version 1,
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

The builder freezes the evidence, validates it against the exact manual
evaluator schema retained by the plan, and checks the key, evaluator, and
revision. The ledger derives its state from `conclusion`; the submission carries
no second state that could contradict the evidence. This validation
authenticates the shape and correlation of the assertion. Schema validation does not turn the
public submission into machine evidence. Contract tests plant each malformed
canonical fragment at the source boundary and prove that checker and detector
schemas remain unconstrained by this manual-only contract.

Assisted completion uses a fixed version 1 residual-judgment contract rather
than applying the detector's evidence schema to a different object. A
`ResidualJudgmentSubmission` contains its schema version, exact obligation key,
detector evaluator reference, admitted input revision, explicit completion
state, and non-empty rationale. An `AssistedCompletionSubmission` pairs that
judgment with one issuer-stamped `DetectorExecution`. The builder compares the
execution registry by identity and requires its evaluator, revision, and frozen
input to equal the packet invocation. The builder also requires the residual
judgment to name that obligation and invocation. Detector evidence without a residual
judgment leaves the record `unchecked`; a residual judgment paired with the
wrong execution is invalid evidence and prevents issuance.

Mechanical completion accepts no caller-supplied checker result. Version 1
completion first restricts checker failure behavior to `block` at both source
and persisted-schema boundaries. The ledger then invokes checkers through the
registry retained by the plan and in canonical completion order. Before the
batch, after each invocation, and immediately before issuance, the builder
revalidates the assurance stamp, retained identities, authored fixture
sequences, and fixture digests. A stale or unreadable fixture prevents issuance
and takes precedence over a simultaneous runner or result failure. A validated
checker result maps its state directly. A registry stamp, retained identity,
binding, evaluator, revision, invocation input, assurance, fixture sequence, or
digest defect raises `CompletionLedgerError` and prevents issuance. After those
checks pass, an exception raised by the reviewed runner or an invalid runner
return produces a `blocked` record with a separate diagnostic, provided that
the builder re-establishes freshness. Tests plant both diagnostic classes.

Privately issued executable predicate evidence has a total state mapping.
`true` maps to `satisfied`, `false` maps to `violated`, and `unknown` maps to
`blocked`. An `unknown` result records an attempted evaluation that could not
decide because a required observation was unavailable. An absent execution
record remains `unchecked`. The procedure executor retains the predicate trace
that supports every mapped truth value.

The builder calls an injected clock once after all validation and evaluation
passes. The clock must return a timezone-aware UTC value. The builder normalizes
that value to one canonical RFC 3339 string ending in `Z`; every record and the
ledger share that transaction timestamp. Timestamps participate in semantic
equality. A clock exception, non-UTC value, or normalization failure raises
`CompletionLedgerError` and prevents issuance. Tests inject a fixed clock, so
identical inputs remain comparable.

`CompletionLedger` is a privately issued, immutable, process-local aggregate.
Its public construction, copying, serialization, and reconstruction fail. Each
`CompletionRecord` contains its key, optional evaluator and enforcement class,
state, immutable evidence, optional blocking diagnostic, and transaction
timestamp. Resolution events never satisfy a record. A future projection may
serialize a reviewed ledger, but the process-local authority itself is not a
portable evidence token.

Mechanical results are reported compactly after the purpose check; they do not substitute for it. Assisted obligations require both detector evidence and the recorded residual judgment. Deliberative obligations require manual evidence against the criterion or predicate, not a general assertion that the artifact was reviewed.

Failure mode and enforcement class remain orthogonal. A mechanically checked obligation may belong to a rule whose failure mode still requires a resident trip-wire because the check runs only after an irreversible action. Conversely, a visible prose defect can require deliberative enforcement.

## Consequences

- The canonical declaration owns the evaluator mapping; checker registries and reports refer to its identifier rather than restating the rule.
- Mixed declarations remain visible at obligation granularity rather than receiving one lossy class.
- Declared mechanical capability and proved runtime readiness remain separate facts.
- Query output answers three distinct questions: what must be deliberated, what must be inspected with assistance, and what must be run.
- Agent reports emphasize decisions and residual uncertainty. Checker verdicts occupy one compact evidence block.
- Migration must not classify a fluent but pattern-detectable prose construction as deliberative merely because agents currently check it by reading.
