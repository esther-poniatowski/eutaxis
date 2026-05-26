# Instruction-file ownership policy

**Severity.** High. **Phase-blocking.** Phase 1 (always-on regime — generates `CLAUDE.md` and `AGENTS.md`). **Origin.** Adversarial review of the cross-agent compiler proposal, objection O3.

## Question

Generated artifacts are written into `~/.claude/`, `~/.codex/`, and project-local configuration files. These targets almost universally contain hand-authored content: project conventions, personal preferences, and notes accumulated over time. The compiler must decide how it coexists with that content.

Two ownership models:

- **Whole-file ownership.** Eutaxis owns the file end-to-end and refuses to overwrite a file it does not recognise as its own. Requires migration of every existing hand-authored line into a source fragment, or full file reservation.
- **Managed-region ownership.** Eutaxis owns a delimited region inside an otherwise free file. Requires delimiter syntax, robust idempotency, and a story for what happens when the user edits inside the managed region.

The choice is **structurally load-bearing**, not a detail. The security argument of [two-source-kinds-instruction-vs-capability](../adr/two-source-kinds-instruction-vs-capability.md) depends on knowing which content the compiler is authorised to overwrite.

## Current state — partial resolution

The **commands subsystem** has resolved its own ownership question via the dual-marker design:

- See [dual-ownership-marker](../adr/dual-ownership-marker.md). The artifact is a directory; ownership is signalled by a sidecar manifest plus an `x-eutaxis-owned` key in `SKILL.md` frontmatter.

This solves the **on-demand** regime (skill artifacts) but does **not** generalise to the always-on regime (instruction files), because:

- `CLAUDE.md` / `AGENTS.md` are loaded directly by the agent; an HTML comment above frontmatter or a JSON sidecar next to them is either inert or visible to the agent.
- The always-on file is normally **partially** hand-authored, not fully generated. Whole-file ownership would force migration.

The always-on regime in the current code is served by the legacy `generate` / `check` for instruction files. The ownership rules applied there are implicit; they have not been promoted to ADR status.

## Architectural components that depend on this

- The Phase 1 release of the always-on regime in the cross-agent compiler.
- The security claim that capability artifacts coexist safely with hand-authored content ([two-source-kinds-instruction-vs-capability](../adr/two-source-kinds-instruction-vs-capability.md)).
- Any future regime that writes into shared user files.

## ADR-ready resolution

A defensible compromise from the review:

- **Whole-file ownership for new generated artifacts** (skills, output-style files, profile fragments). Already implemented for skills via [dual-ownership-marker](../adr/dual-ownership-marker.md).
- **Managed-region ownership for the always-on regime.** Eutaxis
  writes between explicit delimiters (`<!-- eutaxis:begin name=... -->`
  and `<!-- eutaxis:end -->`) inside `CLAUDE.md` / `AGENTS.md`. The
  region is regenerated; content outside it is preserved.
- **Idempotency** is enforced by the marker plus a content hash; the delimiter survives reformatting.

This should be promoted to an ADR before any new always-on writer lands. The two halves of the ownership policy belong in one decision so callers do not have to read open-question pages to know what `eutaxis generate` will overwrite.

## Decision required before

Any release that generates instruction-file content under Eutaxis ownership beyond what the legacy `generate` already does. The boundary between Eutaxis-owned regions and user content is the contact surface most users will see first.
