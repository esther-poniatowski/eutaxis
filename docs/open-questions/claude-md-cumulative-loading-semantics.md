# Claude Code `CLAUDE.md` cumulative-loading semantics

**Severity.** Medium. **Phase-blocking.** Phase 1 (always-on regime adapter for Claude code). **Origin.** Cross-agent customisation-mechanism review, recorded in [silent-failure-rules-as-always-on](../adr/silent-failure-rules-as-always-on.md). Surfaced by the asymmetry between Codex `AGENTS.md` cumulative loading (documented) and Claude Code `CLAUDE.md` merge semantics (undocumented for nested paths).

## Question

The always-on regime adapter compiles authored components into the agent's main instruction file. On the Codex side the contract is explicit: `AGENTS.md` has a [documented cumulative loading order](../../../instructions/...) — global, project, and intermediate parent directories merge in a known sequence, with a documented `project_doc_max_bytes` cap. A modular authoring layout (one file per rule set in a structured directory tree) can be rendered into multiple `AGENTS.md` files at different scopes and rely on Codex to merge them.

On the Claude Code side, the comparable behaviour for `CLAUDE.md` is **not documented**:

- Global `~/.claude/CLAUDE.md` and project `<project>/CLAUDE.md` are both loaded; this is documented.
- Whether `CLAUDE.md` files in directories *between* the project root and the working directory are merged, and in what order, is not documented.
- Whether nested-directory `CLAUDE.md` files below the working directory are loaded on demand (analogous to nested skill discovery) is not documented.
- No `project_doc_max_bytes` analogue is documented; truncation behaviour at large file sizes is unknown.

The adapter must commit to a rendering strategy without confirmation from vendor documentation. The candidate strategies have different failure modes:

- **Trust observed behaviour** (assume parent directories merge like Codex). Risk: silent behaviour change on Claude Code update.
- **Render a single concatenated `CLAUDE.md` per scope** (global, project). Risk: loses modular authoring on disk for Claude users but eliminates the dependency on undocumented merge semantics.
- **Render one `CLAUDE.md` per directory level and verify empirically** before each release. Risk: verification debt; no signal when the platform changes between verifications.

## Current state

- Codex side: covered by [codex/agents-loading-precedence](../../../tutorials/ai-agents/codex/agents-loading-precedence.md) (external — Techne notes). Cumulative loading is the documented contract.
- Claude side: covered by [claude/instructions-preferences](../../../tutorials/ai-agents/claude/instructions-preferences.md) for the global and project files; nested behaviour is not documented in the vendor surface.
- The [customization-mechanisms](../../../tutorials/ai-agents/customization-mechanisms.md) comparative note flags the asymmetry directly:
  > Claude Code uses a `CLAUDE.md` file (merge order and limit not documented).
- The current eutaxis legacy `generate` writes a single file per scope; the question has not been exercised because no scope beyond global / project has been emitted.

## Architectural components that depend on this

- The Phase 1 always-on regime adapter on the Claude side.
- The modular rule-set authoring layout proposed in the session (proposal 2 — structured rule templates), insofar as it relies on the platform to merge rendered output.
- The intra-artifact composition layer ([intra-artifact-composition](intra-artifact-composition.md)) — if the platform merges files, intra-artifact composition is partly platform-delegated on Codex but cannot be delegated on Claude until this question resolves.

## Candidate resolution

The defensible default is the **concatenation strategy**:

- The Claude adapter renders a single `CLAUDE.md` per scope (global, project) by concatenating all rule modules at compile time.
- Section ordering inside the file is governed by [intra-artifact-composition](intra-artifact-composition.md); ordering does not depend on a platform-merge contract.
- Modular authoring is preserved at the source level; on-disk rendering is a single file per scope.

Two reasons to keep this conservative:

1. The behaviour is testable end-to-end without needing vendor confirmation — the adapter writes one file, the platform loads one file.
2. The strategy survives a future Claude Code change that formalises (or breaks) nested merge semantics.

The fallback path, should vendor documentation later confirm cumulative loading, is to relax the renderer to emit per-scope files. The relaxation is non-breaking; the conservative path remains correct.

Two questions to resolve before landing the conservative path:

- **Size budget.** Concatenated `CLAUDE.md` for a non-trivial rule set may approach or exceed any undocumented cap. Without a documented `project_doc_max_bytes` analogue, the adapter needs a configurable warning threshold and an empirical probe.
- **Edit ownership.** A single concatenated file under partial Eutaxis ownership couples this question to [instruction-file-ownership](instruction-file-ownership.md). The managed-region delimiters proposed there must accommodate the full concatenated output without forcing the user to migrate every existing hand-authored line.

## Decision required before

Any release that compiles modular always-on components into Claude-side artifacts. Codex-side compilation can proceed independently using the documented cumulative loading.
