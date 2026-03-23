# Continuation prompt — Optimizing the agent instruction system

## Context

You are working on a set of planning documents in `docs/methods/` that architect an AI agent instruction system for research note generation in an Obsidian vault. The system constrains AI agents at the level of inferential behavior: what must be proven, from which premises, in what order, and what counts as success.

The directory contains these files:

| File | Role | Lines | Status |
|---|---|---|---|
| `plan-agents-humain-generation.md` | Entry point — goal, diagnosis, 8-component table | 63 | Stable |
| `decision-rules.md` | Decision rule definitions (4 layers: epistemic, argumentative, stylistic, integrative) | 463 | Needs optimization based on expert feedback |
| `formal-contracts.md` | Two-phase contract system (pre-draft spec + post-draft integration record) | 98 | Stable |
| `note-types.md` | 11 note type definitions + index note specifications | 61 | Stable |
| `procedural-workflows.md` | 9-stage pipeline, 4 passes, context injection, decision-rule dispatch | 132 | Needs clarity and redundancy improvements |
| `workspace-architecture.md` | Directory layout, normative/descriptive split, AGENTS.md spec, naming conventions | 159 | Stable |
| `audits.md` | Audit dimensions, checklists, report template | 40 | Thin — needs substantial development |
| `registries.md` | Registry files (reasoning graph, dependencies, open questions, terminology) + validation toolchain | 154 | Stable |
| `prompt-writing-methods.md` | Prompt engineering methods for agent instruction files | 480 | Stable |
| `migration-reasoning-graph.md` | Migration strategy for existing vault content | 663 | Not in scope for this conversation |
| `plan-revisions.md` | Expert assessment of the decision rule system + revision tasks | 90 | Input for this conversation |

Cross-links: Each note has a `[!INFO] See also` block with mutual links. The entry point (`plan-agents-humain-generation.md`) has a component table linking all 8 notes.

The workspace architecture uses:
- `governance/` for normative files (rules, specs, contracts, audits, schemas, workflow)
- `registries/` for descriptive state
- `AGENTS.md` at the vault root
- `projects/<project>/governance/` and `projects/<project>/registry/` mirroring the split

## Tasks for this conversation

### Task 1 — Develop the audit note (`audits.md`)

The current audit note is thin: it lists eight audit dimensions with one-line descriptions and an audit report template structure, mostly carried over from the previous location in `workspace-architecture.md`.

**Goal**: Develop `audits.md` into a substantive specification of the audit system. Use the following external sources to inform the design:

- Academic and industry best practices for structured code/document review systems
- The existing decision rules in `decision-rules.md` (each audit dimension verifies specific rules)
- The contract structure in `formal-contracts.md` (audit verifies contract compliance)
- The procedural workflows in `procedural-workflows.md` (audit is Stage 5, produces audit reports consumed by Stage 6 revision)

**Specific areas to develop**:
- Severity classification for audit findings (what warrants revision vs. excision vs. deferral vs. return to architect)
- The relationship between audit dimensions and the return-trigger table in `procedural-workflows.md`
- How audit findings feed back into the contract (divergence assessment) and registry (propagation)
- Audit independence: the audit pass must not patch the note directly — it produces findings that route to the appropriate earlier pass

### Task 2 — Optimize decision rules (`decision-rules.md`) based on expert feedback

The file `plan-revisions.md` contains a detailed expert assessment (sections I–III + summary table). The key recommendations are:

**Mergers and demotions**:
- Side-result criterion → absorb into local necessity as condition 6 (authorization check)
- Functional motivation → demote to sub-criterion of local necessity condition 2 (major construct threshold)
- Retention audit operator → demote to audit-phase enforcement mechanism; retain Test C (non-redundancy) as an independent sub-criterion
- Mathematical standards → demote to enforcement checklist referencing existing rules, not re-specifying them
- Writing principles → label explicitly as stylistic facade/translation interface, not a peer-level rule
- Scope admissibility → relocate to contract formation protocol (it operates before generation, not during)
- Divergence resolution → relocate to procedural workflow specification (it is workflow routing, not a quality criterion)

**Additions**:
- Notational coherence — new rule: each major symbol has a unique referent throughout the note; notational changes relative to imported material are declared
- Transition quality — new sub-criterion within writing principles: each section-opening passage identifies what was established and why the current section follows

**Tightening**:
- Make the link between explanatory target and constructive-direction sub-criterion explicit
- Clarify the relationship between the interpretive sub-criterion (scope above) and claim/derivation/interpretation separation (scope below)
- Resolve the dual specification of objective unity's non-atomicity test and retention audit Test B (same test, different phases)

### Task 3 — Improve procedural workflows (`procedural-workflows.md`)

**Goal**: Improve clarity and remove redundancy, especially in light of the decision-rule changes from Task 2.

**Specific areas**:
- If divergence resolution moves from decision-rules.md to procedural-workflows.md, integrate it properly into the pipeline stages
- Update the context injection table and decision-rule dispatch tables to reflect the merged/relocated rules
- Ensure handoff artifacts and return triggers are consistent with the revised rule set
- Check that the audit pass description aligns with the developed audit note from Task 1

## Constraints

- These are planning documents that architect a system, not the implemented system itself. They describe what the workspace, registries, contracts, and agent instructions should contain.
- Do not rewrite notes wholesale. Propose targeted, justified changes and ask for approval before making large structural modifications.
- Read all relevant files before proposing changes.
- When restructuring decision rules, preserve the anchors (`^anchor-name`) that other files reference, or update all cross-references if anchors change.
- The writing style rules in CLAUDE.md apply to research notes in the vault, not to these planning documents — but the planning documents should still be clear and well-organized.
- Present your analysis and proposed changes to the user for approval before editing.
