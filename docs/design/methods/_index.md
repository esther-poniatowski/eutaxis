# Design Documentation — Methods

Design-time reference documents for the eutaxis governance system. These files
describe the rationale, structure, and specification of each governance component.
They are not loaded by agents at runtime — the deployed governance files in
`src/eutaxis/data/governance/` are the runtime artifacts.

## Components

| Document | Scope |
| --- | --- |
| [plan-agents-humain-generation](plan-agents-humain-generation.md) | Master plan and problem diagnosis |
| [workspace-architecture](workspace-architecture.md) | Directory layout and file organization |
| [decision-rules](../quality-criteria/decision-rules.md) | Verifiable quality criteria |
| [formal-contracts](formal-contracts.md) | Per-note inferential specifications |
| [note-types](note-types.md) | Per-type structural constraints |
| [procedural-workflows](procedural-workflows.md) | Staged pipelines and pass model |
| [audits](audits.md) | Post-draft verification checklists |
| [registries](registries.md) | Machine-readable project state |
| [prompt-writing-methods](prompt-writing-methods.md) | Agent prompt design principles |
