# Eutaxis as a build-time compiler, not a runtime activation mechanism

## Status

Accepted. **Supersedes**
[prompt-level-component-activation](prompt-level-component-activation.md).

## Context

Eutaxis customises multiple coding agents (Claude Code, Codex) from a
shared body of authored content. An earlier proposal introduced a
runtime prompt directive (`@eutaxis rule:... role:...`), a portable
component registry, and agent-specific adapters layered *beneath* a
canonical directive syntax. The intent was to make the same string
take effect on any client.

An adversarial audit judged that direction unsound. Three failures were
identified:

- **The directive was portable as text, not as behaviour.** It depended
  on a non-portable interpreter (the agent or a wrapper); without one,
  it reached the model as inert prose.
- **The sigil collided.** `@` is reserved for file-reference preprocessing
  in both target clients; the directive could not pass through unmolested.
- **Runtime context injection clashed with the project's review
  discipline.** Eutaxis relies on golden-file review of generated
  artifacts; a runtime mechanism produces effects that no file
  captures, so review cannot exercise it.

Empirically, no target agent exposes per-prompt activation: output
styles are fixed at session start, skills load on invocation and
persist, profiles are selected at startup. The genuine requirement the
directive expressed — on-demand loading that does not inflate
always-active context — is met natively by skills, which already load
only when invoked.

## Decision

Eutaxis is a **cross-agent configuration compiler**, not a runtime
activation mechanism. A single authoritative source — Markdown
fragments plus a declarative manifest — is compiled into the native
customisation artifacts of each target agent. Compilation is
deterministic and one-way; "synchronisation" denotes regeneration
together with drift detection, not bidirectional reconciliation.
Bidirectional merge is out of scope.

The build-time stance has direct architectural consequences, codified
in separate ADRs:

- The author writes one source; each agent receives its native
  artifact via an adapter. See
  [same-source-not-same-behaviour](same-source-not-same-behaviour.md).
- The classification axis is the activation regime, not a typed
  identifier. See
  [activation-regime-as-classification-axis](activation-regime-as-classification-axis.md).
- The compiler does not reinvent layering; native precedence resolves
  cross-scope conflicts. See
  [native-precedence-over-parallel-engine](native-precedence-over-parallel-engine.md).
- Every artifact is reviewable as a file. See
  [golden-file-review-as-correctness-contract](golden-file-review-as-correctness-contract.md).

## Discarded alternatives

- **Runtime prompt directive (`@eutaxis ...`)** with a portable
  interpreter and agent-specific adapters underneath. Rejected for the
  three reasons above (text-not-behaviour, sigil collision, review
  discipline). Documented in the superseded
  [prompt-level-component-activation](prompt-level-component-activation.md).
- **Bidirectional synchronisation** between source and generated
  artifacts. Rejected because the targets reside in mutable locations
  that users and agents themselves modify; a merge engine that
  reconciles those edits back into the source would inflate scope and
  reintroduce the review-discipline problem.
- **A uniform runtime activation protocol** layered above per-agent
  adapters. Rejected because the convergence point empirically is
  source content, not activation. No two target agents share an
  activation protocol the compiler could canonicalise.

## Rationale

A build-time compiler eliminates the runtime portability failure (no
directive to mis-route), removes the sigil collision (no sigil
emitted), and is reviewable by inspection of the generated artifacts.
The build-time stance also respects how the agents are actually
built: each one exposes its own customisation surface, and the source
layer is the only place a unification can hold.

## Consequences

- Eutaxis ships `generate`, `check`, `plan`, `explain` as the
  command surface — operations on artifacts, not on running sessions.
- The author cannot ask Eutaxis to "activate" a component on the fly;
  activation lives where the platform puts it (file edit, settings
  key, slash invocation).
- The earlier `@eutaxis ...` syntax is removed without replacement.
  Documents that referenced it have been migrated to native
  invocations (`/<name>`, `$<name>`, file paths, etc.).
- The earlier resolver-as-runtime command is retained only as a
  build-time and diagnostic facility (subsumed by `plan` and
  `explain`).
