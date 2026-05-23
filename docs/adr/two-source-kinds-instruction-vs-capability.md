# Two source kinds: instruction content and capability configuration

## Status

Accepted.

## Context

A cross-agent compiler that emits artifacts into `~/.claude/`,
`~/.codex/`, project `CLAUDE.md` / `AGENTS.md`, and native settings
files crosses two qualitatively different surfaces:

- **Instruction content** — Markdown the agent reads as guidance.
  Authoring errors produce *behavioural drift*: the agent does the
  wrong thing, but no privilege is granted.
- **Capability configuration** — MCP server bindings, permission
  rules, command policies. Authoring errors produce *privilege
  drift*: the agent acquires (or loses) tool reach. This is a
  security surface.

Treating both kinds with the same validation, review, and rollout
discipline is wrong in both directions: instruction edits become
heavyweight; capability edits become casual. The adversarial review of
the parent proposal flagged this conflation as O5 — "the capability
regime conflates tool wiring with security policy."

## Decision

The source carries **two source kinds**, distinguished at the manifest
level:

- **Instruction components** — content compiled to instruction files
  (`CLAUDE.md`, `AGENTS.md`), skills (`SKILL.md`), or output-style /
  profile artifacts. The body is Markdown; the compiler templates and
  positions it but does not interpret it semantically.
- **Capability components** — declarative configuration compiled to
  MCP server definitions, settings permission rules, and equivalent
  native configuration. The body is a structured declaration; the
  compiler validates the shape against the target agent's schema.
  Capability components carry a subtype: `tool-wiring` for tool
  registration and toggles, or `policy` for permission rules,
  command policy, sandbox configuration, and approval behaviour.

The two kinds follow different paths through the pipeline:

| Stage         | Instruction                                | Capability                                         |
| ------------- | ------------------------------------------ | -------------------------------------------------- |
| Validation    | Markdown shape, length budget              | Schema validation, privilege boundary analysis     |
| Review gate   | Diff in `eutaxis check`                    | Diff plus an explicit privilege-change summary     |
| Emit policy   | Direct write under ownership rules         | Opt-in per run; never applied silently             |
| Audit trail   | Golden file diff                           | Golden file diff plus before/after privilege scope |

Capability emission is **never automatic** in routine `eutaxis
generate` runs. A separate flag (e.g. `--with-capabilities`) gates the
write, and the planned changes are summarised with their privilege
delta before any artifact lands.

Approximate fidelity is valid only for `tool-wiring`. For `policy`,
the compiler must either represent the same boundary exactly on the
target surface or refuse the build. A policy source that compiles to
a looser or stricter privilege boundary is not an approximate match;
it is a privilege change and requires an explicit policy decision.

Externally sourced capability components (from cross-repo rule-owning
projects) are subject to additional supply-chain rules; see
[open-questions/cross-repository-source-acquisition](../open-questions/cross-repository-source-acquisition.md)
and [open-questions/capability-regime-split](../open-questions/capability-regime-split.md).

## Discarded alternatives

- **One source kind, no distinction.** Rejected because instruction
  edits would inherit the heavyweight review path needed for
  capability edits, slowing the common case and confusing the
  security surface.
- **Three or more kinds** (e.g. split instruction further by regime).
  Rejected because the regime axis already partitions instruction
  components; adding a kind axis on top duplicates the discriminator.
- **Reject capability compilation entirely; keep eutaxis to
  instruction artifacts.** Considered but rejected: MCP wiring is
  legitimately cross-agent and benefits from a single source. The
  decision is to compile capability with stricter discipline, not to
  refuse it.
- **Treat capability artifacts as instruction artifacts with a
  warning.** Rejected: warnings on a privilege surface are not enough.
  An explicit opt-in is the floor.

## Rationale

The two kinds correspond to two distinct failure modes and to two
distinct review responsibilities. Folding them into one regime would
either over-secure instruction edits or under-secure capability
edits. A separate kind makes the boundary visible at the source-schema
level, where it belongs.

## Consequences

- The manifest schema distinguishes `instruction:` and `capability:`
  components (or the equivalent in the chosen schema).
- The `eutaxis explain` output reports privilege deltas for capability
  components separately from content drift for instruction
  components.
- A capability component cannot be compiled "by mistake" — a flag
  must be passed and a diff acknowledged.
- The capability regime split into `tool-wiring` and `policy` is
  required before capability emission. The remaining open work in
  [open-questions/capability-regime-split](../open-questions/capability-regime-split.md)
  concerns exact schema vocabulary and supply-chain gates, not the
  existence of the split.
