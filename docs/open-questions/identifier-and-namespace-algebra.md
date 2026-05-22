# Identifier and namespace algebra

**Severity.** Medium.
**Phase-blocking.** Phase 1 if cross-repository fragments are consumed.
**Origin.** Adversarial review of the cross-agent compiler proposal,
objection O10 (and §10 Q5).

## Question

The example identifier `hermeneia/prose-writing` is namespaced by
repository. The legacy proposal defers the namespacing rules but the
architecture already presumes:

- A registry of components.
- Dependency resolution between components.
- Conflict semantics within and across scopes.

Without a defined namespace algebra, "dependency" and "conflict" have
no addressable referent. The questions to settle:

- **Namespacing rules.** Is `<repo>/<name>` the canonical form, or
  `<repo>:<name>`, or `<repo>.<name>`? Are nested namespaces
  permitted? How are name collisions across repositories surfaced?
- **Version pinning syntax.** Is a component identified by `(name,
  version)`, by `(name, hash)`, or by a path in a lockfile?
- **Lockfile format.** Same as the question above, from the storage
  side. JSON, YAML, TOML?
- **Conflict policy for duplicate identifiers.** When two sources
  provide the same `<repo>/<name>`, what is the resolution rule?

## Current state — partial resolution

The **commands subsystem** has resolved one piece of the algebra:

- Codex skills require the `SKILL.md` `name` field to **equal the
  parent directory name**
  ([skills-comparison.md:67]). The commands subsystem codifies
  this: the source `name` is both the slug used in `<...>/<name>/`
  and the value emitted into `SKILL.md`. See
  [agent-skills-as-target-surface](../adr/agent-skills-as-target-surface.md).
- Within a single source layer (built-in, user, project), `name`
  is unique. Cross-layer collisions are resolved by precedence
  (project > user > built-in).

What remains open:

- **Cross-repository namespacing.** The commands subsystem only
  resolves intra-project naming; the cross-repo `<repo>/<name>` form
  is not implemented.
- **Versioning.** No component version is tracked.
- **Lockfile.** No lockfile exists.
- **Dependency resolution.** Components do not declare dependencies
  in the current implementation.

## Architectural components that depend on this

- The Resolution-core layer of the cross-agent compiler pipeline.
- Cross-repo fragment acquisition
  ([cross-repository-source-acquisition](cross-repository-source-acquisition.md))
  — the lockfile shape is half of that question.
- The capability split
  ([capability-regime-split](capability-regime-split.md)) — privilege
  changes need a namespace-aware audit trail.

## Candidate resolution

A minimal namespace algebra sufficient for Phase 1:

- **Canonical form:** `<repo>/<name>` with no nested separators in
  `<name>`. Naming a sub-namespace is deferred until a real case
  needs it.
- **Identity:** `(canonical-form, content-hash)`. Version strings
  are deferred; the hash is the durable identifier.
- **Conflict policy:** within a scope, the same canonical form
  appearing twice is a build error. Across scopes, native precedence
  resolves it
  ([native-precedence-over-parallel-engine](../adr/native-precedence-over-parallel-engine.md)).
- **Lockfile:** JSON for parity with the existing
  `installed-commands.json` registry. The file is committed.

The full versioning algebra (semver ranges, `^` constraints, etc.)
can wait until at least one external rule-owning project lands.

## Decision required before

Any release that consumes external (cross-repository) fragments. The
commands subsystem does not need this work to land; the broader
cross-agent compiler does.
