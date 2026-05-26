# Intra-artifact composition, ordering, and conflict

**Severity.** High.
**Phase-blocking.** Phase 1 (any scope with multiple components compiling to one artifact).
**Origin.** Adversarial review of the cross-agent compiler proposal,
objection O2.

## Question

Multiple components frequently compile into the **same output
artifact**. Many always-on components compile to one
`CLAUDE.md` / `AGENTS.md`. Multiple session-preset components share a
single active output-style or profile slot. The native-precedence
principle
([native-precedence-over-parallel-engine](../adr/native-precedence-over-parallel-engine.md))
addresses **cross-scope** layering (global vs project) — it does not
answer:

1. **Order.** In what order do two always-on components from the
   same scope appear inside `CLAUDE.md`? Order matters for
   instruction priming and section visibility.
2. **Conflict policy.** What happens when two components contradict
   each other within the same scope? "The platform resolves it" is
   false here — the platform sees one merged file.
3. **Single-slot collision.** What happens when two session-preset
   components target the same Codex profile name, or different role
   components want different `model` settings within one profile?
4. **Cross-regime references.** When always-on content references an
   on-demand artifact (e.g. an always-on router that points to
   skills), how is the router generated and what guarantees ordering
   between the router and the referenced skills?

These are not edge cases — they are the core compilation semantics for
any scope with more than one component.

## Current state

Only the on-demand regime currently has a usable answer: each skill is
its own directory, so there is no intra-artifact composition. Every
other regime that ships will encounter the question on its first
multi-component scope.

The commands subsystem of Eutaxis avoids the question because each
command is a separate skill artifact, so intra-artifact composition
is not exercised. The always-on regime, when it lands beyond the
legacy `generate`, will exercise it immediately.

## Architectural components that depend on this

- The Resolution-to-Adapter pipeline
  ([compiler-not-runtime-activation](../adr/compiler-not-runtime-activation.md)).
  The current architecture has Resolution emit a per-scope component
  set and Adapter render artifacts; the composition layer between
  them is unspecified.
- The fidelity contract — "approximate" is a per-component grade, but
  intra-artifact ordering can also be approximate or wrong.

## Candidate resolution

The review's recommended correction is to introduce an explicit
**intra-artifact composition layer** between Resolution and Adapter:

1. **Deterministic ordering keys** declared on components (e.g. a
   numeric `order:` field, or stable named anchors like
   `before: <id>` / `after: <id>`).
2. **A documented conflict policy** per regime: fail / last-writer /
   explicit-merge.
3. **A per-mechanism rule** for what "one artifact, many components"
   means: concatenated sections (always-on), single active slot
   (session-preset, single-slot mechanisms), separate directories
   (on-demand).

Without this layer, the compiler is not deterministic in any usable
sense.

## Decision required before

Any release that compiles always-on or session-preset components from
more than one source within a single scope. The legacy
instruction-file generator already runs into this; whatever rules it
uses informally should be lifted to ADR status.
