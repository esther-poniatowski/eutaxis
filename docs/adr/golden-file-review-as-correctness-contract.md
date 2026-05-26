# Golden-file review as the correctness contract

## Status

Accepted.

## Context

Eutaxis customises agents whose behavioural response to a given input
cannot be reproduced offline (the agents are remote, non-deterministic
to some degree, and frequently updated). A compiler that promises
behavioural correctness would need a behavioural-validation loop: run
smoke prompts against each target with the compiled configuration,
compare the response against expected signatures. No such loop is in
scope for v1.

The build-time stance (compiler-not-runtime-activation) reframes the
correctness question. Compilation is a deterministic function of the
source. Every artifact is reviewable as a file. The contract Eutaxis
can credibly support is: **given this source, this is the artifact
installed on disk**. Behavioural correctness is downstream.

## Decision

The correctness contract is **golden-file review**: every generated
artifact is a committed file, compilation is deterministic, and a
diff against the source tree is the unit of verification. The
contract has three operational rules:

1. **Compilation is reproducible.** `eutaxis generate` from the same
   source produces byte-identical artifacts. Non-deterministic inputs
   (timestamps, hash salts, environment paths) are excluded from
   serialised artifacts where avoidable, and recorded with
   documented provenance where unavoidable.
2. **Drift is detectable.** `eutaxis check` re-executes the pipeline
   and reports any difference between the planned artifacts and
   their on-disk state. Drift is a first-class CLI report, not a
   silent re-emit.
3. **Artifacts are reviewable.** Every emitted file is plain text in
   a checked-in format (Markdown, YAML, JSON). Binary blobs are not
   emitted; structured-configuration artifacts (`config.toml`,
   `settings.json` excerpts) follow the same review path.

The golden file is the **artifact**, not the source. The source can
change in ways the artifact does not; the artifact can change in
ways the source did not. Both directions are caught by `check`.

This contract **does not** certify behavioural correctness. Whether
the agent actually behaves the way the artifact suggests is a
separate question, tracked at
[open-questions/behavioural-validation](../open-questions/behavioural-validation.md).

## Discarded alternatives

- **Behavioural-validation as the contract** (run prompts against
  each target, assert response shapes). Rejected for v1 because it
  requires a remote, possibly paid, and non-deterministic loop that
  does not fit the build-time stance. Tracked as a follow-up.
- **No correctness contract** (treat Eutaxis as best-effort).
  Rejected because the system writes into shared user files and into
  privilege-granting configuration; absence of a contract makes
  every change implicit.
- **Hash-only contract** (record an artifact hash in the registry;
  compare hashes). Rejected: hashes catch *change*, not *intent*. A
  diff over the artifact text gives the reviewer the actual delta.
- **Snapshot tests inside the CI pipeline only** (no on-disk
  golden). Rejected because the user-visible artifacts live on the
  filesystem and the user must be able to inspect them. CI is a
  complement, not a substitute.

## Rationale

Golden-file review is the contract a deterministic compiler can
actually deliver. It is also the discipline the project's existing
implementation already uses (the legacy `eutaxis generate` for
instruction files). The contract scales: it covers always-on
instruction files, on-demand skill directories, session-preset
output-style artifacts, and capability configuration.

## Consequences

- Every generated artifact format must serialise deterministically.
  Renderers sort keys; YAML emitters disable flow style; JSON dumps
  pass `sort_keys=True` and `indent=2`.
- The CI suite includes a `check` invocation against the committed
  source and committed golden artifacts.
- Behavioural validation, when introduced, **complements** this
  contract; it does not replace it.
- `eutaxis explain` surfaces per-target fidelity grades
  ([same-source-not-same-behaviour](same-source-not-same-behaviour.md))
  alongside the file diff so the reviewer sees both layers in one
  report.
