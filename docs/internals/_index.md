---
tags:
  - index
aliases:
  - Design Documentation — Methods
index: "[Eutaxis](../index.md)"
---

# Design documentation — methods

Design-time reference documents for the eutaxis governance system. These files describe the rationale, structure, and specification of each governance component as **planned** — the runtime artifacts they describe (deployment under `src/eutaxis/data/governance/`, staged pipelines, post-draft audits) are not yet implemented in the current code. The contents define an architectural target, not shipping behaviour.

## Components

| Document                                                          | Scope                                  |
| ----------------------------------------------------------------- | -------------------------------------- |
| [motivations-problem-statement](motivations-problem-statement.md) | Master plan and problem diagnosis      |
| [architecture](architecture.md)                                   | Directory layout and file organization |
| [registries](registries.md)                                       | Registry files and validation          |
| [audits](audits.md)                                               | Post-draft verification checklists     |

## Plans

| Document                                              | Scope                                                          |
| ----------------------------------------------------- | -------------------------------------------------------------- |
| [api-docs-pipeline-plan](api-docs-pipeline-plan.md)   | Staged plan to introduce `sphinx-markdown-builder` for the API |

