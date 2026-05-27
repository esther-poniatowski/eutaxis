# Instruction-file ownership boundaries (navigation only)

## Status

Accepted.

## Context

Generated artifacts land in target classes whose ownership stories are governed by different ADRs. Without an explicit boundary statement, an author or reviewer must read the open question [instruction-file-ownership](../open-questions/instruction-file-ownership.md) to know which ADR applies to which target class. This ADR records the boundary; it does not introduce any new ownership mechanism.

## Decision

The ownership policy for every generated target class is delegated to the existing ADR that governs that class. The boundary is:

| Target class | Example | Ownership ADR | Marker |
|---|---|---|---|
| **On-demand skill artifacts** | `~/.claude/skills/<name>/`, `~/.agents/skills/<name>/` | [dual-ownership-marker](dual-ownership-marker.md) | YAML frontmatter `x-eutaxis-owned` + JSON sidecar `.eutaxis-owned.json` (both metadata) |
| **Always-on whole-file writers** | `~/.codex/AGENTS.md`, `~/.claude/CLAUDE.md` as a consumer's instruction-assembly target reserves them | No ADR; current behaviour: the generator rewrites the file end-to-end | None (the consumer reserves the path for Eutaxis output) |
| **Always-on partial-ownership writers** | A hypothetical `CLAUDE.md` that mixes hand-authored project conventions and generated rule blocks | No ADR; deferred until a concrete consumer requires it | None (no mechanism yet; see [instruction-file-ownership](../open-questions/instruction-file-ownership.md)) |

The Skills-compilation work — both the `commands` subsystem and the `eutaxis skills` config-driven analogue — produces only on-demand skill artifacts and is fully covered by [dual-ownership-marker](dual-ownership-marker.md). It does not depend on the always-on policies.

## Discarded alternatives

- **Promote the current whole-file behaviour to an ADR.** Rejected as premature: the behaviour has not surfaced a conflict that the consumers cannot resolve by reserving the target path. An ADR documenting "current behaviour, no constraint" adds noise without adding decision content.
- **Promote a managed-region (partial-ownership) policy to an ADR speculatively.** Rejected per the open question's framing: no consumer needs the mechanism today; locking the delimiter syntax before a real consumer can describe its needs would force a redesign later.
- **Withdraw the open question.** Rejected: the always-on partial-ownership case remains a legitimate open design problem when a real consumer surfaces it. The open question is the right home for that follow-up.

## Rationale

The boundary statement is a navigation aid for the reader. Each target class points at the ADR (or the open question) that governs it. The Skills work proceeds on a single covered branch (dual-marker); the other two branches stay parked at their current state. A reader who needs to know "what overwrites what" reads this one ADR rather than reconstructing the answer from the open question's discussion.

## Consequences

- The open question [instruction-file-ownership](../open-questions/instruction-file-ownership.md) is **not** closed. Its scope is narrowed to the always-on partial-ownership case. The on-demand half is removed from its scope by reference to this ADR and to [dual-ownership-marker](dual-ownership-marker.md).
- The Skills-compilation extension lands without further ownership decisions.
- Any future writer that emits content into a target outside the three classes above must reference this ADR and either match an existing class or introduce its own.
