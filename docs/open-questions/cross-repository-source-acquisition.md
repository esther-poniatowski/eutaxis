# Cross-repository source acquisition

**Severity.** Medium.
**Phase-blocking.** Phase 1 if external fragments are consumed.
**Origin.** Adversarial review of the cross-agent compiler proposal,
objection O8.

## Question

Source components may originate in separate rule-owning repositories
(vitruv, hermeneia, gnomon). The proposal pins components with
integrity hashes in a lockfile. The lockfile records identity but does
not constrain **how** the fragment arrived. Each acquisition mode has
different supply-chain properties:

- **Git submodule.** Pinned by commit; reproducible; requires submodule
  management.
- **Tarball / archive download at build time.** Reproducible if hashed;
  introduces a build-time network dependency.
- **Network fetch at build time** (HTTP / git clone). Turns `eutaxis
  generate` into an outbound-network operation; reproducibility
  depends on remote availability.
- **Vendored copy.** Reproducible; loses link to upstream; requires a
  vendoring workflow.

Combined with [capability-regime-split](capability-regime-split.md),
this is the missing half of the supply-chain story. A capability
fragment delivered through an unconstrained acquisition channel can
widen the agent's permission boundary in ways the integrity hash
alone does not prevent (an attacker who controls the upstream can
ship a different hash with widened permissions; the user signs the
new lockfile under whatever review they apply).

## Current state

No external-fragment acquisition is currently implemented. The
commands subsystem ships built-in source files under `data/commands/`;
the user-extension layer (`~/.eutaxis/commands/`,
`<project>/.eutaxis/commands/`) consumes flat local files; nothing
fetches from an external repository.

The architectural commitment to cross-repository source components
(§4.2 of the legacy proposal, now distributed across ADRs) is
explicit but unimplemented.

## Architectural components that depend on this

- The source schema for external-fragment references.
- The lockfile format (also referenced by
  [identifier-and-namespace-algebra](identifier-and-namespace-algebra.md)).
- The supply-chain security rules in
  [capability-regime-split](capability-regime-split.md).
- The `eutaxis check` behaviour when an external fragment has
  drifted.

## Candidate resolution

A minimal first-pass decision:

- **v1 (Phase 1):** fragments are resolved from a path-based registry.
  Network fetch is out of scope. External rule-owning projects are
  consumed via git submodule or vendored copy, neither of which is
  Eutaxis's responsibility to perform.
- **v2:** if a network acquisition mode is added, it is opt-in per
  invocation, deterministic (URL + hash), and refused for capability
  components by default
  ([capability-regime-split](capability-regime-split.md)).

Specifying the acquisition mode before Phase 1 ships is small as a
decision but consequential as a posture.

## Decision required before

Any release that consumes external fragments — or any release that
documents external-fragment consumption as a feature, even
unimplemented.
