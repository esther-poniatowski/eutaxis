# Architecture

## Hierarchical levels

The architecture should reflect **distinct scales of organization**:

| Scale               | Contents                                                                                                                                                                         |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Workspace scale** | Shared governance, shared specifications and templates, global terminology, cross-project standards                                                                              |
| **Project scale**   | One coherent body of work with its own content graph, registry state, and integration structure                                                                                  |
| **Module scale**    | One coherent subdomain within a project, with its own local index, local frontier of open questions, and note production.<br>(+ Cross-module integration if necessary)           |

> [!CHECK] General organization
> - **Global rules** should be centralized
> - **Contracts, notes, audits, registry state, artifacts** should be attached to the scale at which content control is exercised (project or module).
> - **Legacy materials** should remain close enough to their original context to preserve traceability, but isolated from active authoritative notes.

The vault's governance is distributed across the following components:

| Component | Directory |
| --- | --- |
| Decision rules | `governance/rules/` |
| Note specifications | `governance/specs/` |
| Contract templates | `governance/contracts/` |
| Audit checklists and report | `governance/audits/` |
| Workflow and pass specs | `governance/workflow/` |
| Registry files and validation | `registries/` + `tools/` + `governance/schemas/` |

Each component carries one or more abstract responsibilities; the concrete content of each is project-declared. The audit responsibilities are detailed in [audits](audits), the workflow responsibilities in [procedural-workflows](procedural-workflows), and the registry-and-validation responsibilities in [registries](registries). Decision rules, note specifications, and contract templates are domain-specific and authored by the project deploying eutaxis.

## Directory layout

```text
vault/
├── AGENTS.md                          # entry point — always loaded first
│
├── governance/                        # normative: rules of the system
│   ├── rules/
│   │   ├── _index.md
│   │   ├── <rule>.md                  # one per decision rule
│   │   └── ...
│   ├── specs/
│   │   ├── _index.md
│   │   ├── <note_type>.md            # one per note type
│   │   └── ...
│   ├── contracts/
│   │   ├── <note_type>.md            # one per note type
│   │   └── ...
│   ├── audits/
│   │   ├── checklists.md
│   │   └── report_template.md
│   ├── schemas/
│   │   ├── content_graph.schema.json
│   │   ├── dependencies.schema.json
│   │   ├── open_questions.schema.json
│   │   └── terminology.schema.json
│   └── workflow/                  # pipeline prompts and pass specs
│
├── registries/                        # descriptive: global state
│   ├── terminology.yaml
│   ├── conventions.yaml
│   └── project_catalog.yaml
│
├── tools/
│   ├── validate_registry.py
│   ├── registry_diff.py
│   └── lint_terminology.py
│
├── projects/
│   ├── <project>/
│   │   ├── index.md
│   │   ├── governance/                # project-local overrides
│   │   │   ├── project_scope.md
│   │   │   └── specs/
│   │   ├── registry/
│   │   │   ├── staging/
│   │   │   ├── content_graph.yaml
│   │   │   ├── open_questions.yaml
│   │   │   ├── terminology.yaml
│   │   │   └── dependencies.yaml
│   │   ├── <module>/
│   │   │   ├── index.md
│   │   │   ├── notes/
│   │   │   ├── contracts/
│   │   │   ├── audits/
│   │   │   ├── legacy/
│   │   │   │   ├── reviewed/
│   │   │   │   ├── superseded/
│   │   │   │   └── archived/
│   │   │   ├── scratch/
│   │   │   │   ├── planning/
│   │   │   │   └── deferred/
│   │   │   └── assets/
│   │   └── ...
│   └── ...
└── ...
```

The vault root contains `AGENTS.md` (the agent entry point, always loaded first) and four top-level directories that separate **normative** content (how the system works) from **descriptive** content (what state the system is in):

**`governance/`** contains the normative rules of the system — static, authoritative, amended only by explicit human decision:

- `rules/` — one file per project-declared decision rule, plus an `_index.md` as cross-referencing hub
- `specs/` — one project-declared note specification per type, plus an `_index.md` as note-type index
- `contracts/` — one project-declared contract template per note type
- `audits/` — [audit checklists and report template](audits)
- `schemas/` — one JSON Schema per registry file (see [schema requirements](registries#^schema-requirements))
- `workflow/` — pipeline prompts and [pass specifications](procedural-workflows)

**`registries/`** contains the descriptive global state — dynamic, updated as the vault evolves:

- `terminology.yaml` — global terminology registry (if shared across projects)
- `conventions.yaml` — global stylistic conventions (if shared across projects)
- `project_catalog.yaml` — catalog of all projects with their primary objective and content-graph entry point

**`tools/`** contains the validation scripts specified in [tooling](registries#^tooling): `validate_registry.py`, `registry_diff.py`, `lint_terminology.py`.

**`projects/`** contains one directory per project. Each project directory mirrors the normative/descriptive split:

- `index.md` — project entry point
- `governance/` — project-local overrides: `project_scope.md` (project-declared scope admissibility), and optionally `specs/` for project-specific note-type overrides
- `registry/` — machine-readable state of the local project (see [registries](registries)):
	- `content_graph.yaml` — the typed dependency graph of the project
	- `open_questions.yaml` — the current frontier of open questions
	- `terminology.yaml` — project-specific terminology registry
	- `dependencies.yaml` — provenance and usage tracking for reusable objects
	- `staging/` — subdirectory where the agent writes proposed updates
- One directory per module, each containing:
	- `index.md` — module entry point
	- `notes/` — active notes that follow the governance and contribute to the content graph; these are the only notes that the agent may cite or import from when drafting new notes
	- `contracts/` — contracts associated to draft notes
	- `audits/` — external evaluations of draft notes
	- `legacy/` — non-authoritative archived materials (with `reviewed/`, `superseded/`, `archived/` subdirectories)
	- `scratch/` — non-authoritative temporary materials (with `planning/` and `deferred/`), and `assets/`

## Global instruction file

**File**: `AGENTS.md` (at the vault root)

**Role**: This file is the **entry point** for the agent, always loaded first. It must direct the agent toward the authoritative files in `governance/`. It should coordinate, not contain the entire doctrine.

**Suggested structure**: This file must be **short, hierarchical, and procedural**. It should contain exactly the following sections:

- **Mission.** A one-sentence statement: the vault is a modular content system whose typed notes compose toward a project-declared primary objective.
- **Core invariants.** Three non-negotiable constraints: (1) no note may be drafted without an explicit contract, (2) no note may introduce a major output unless contracted, (3) no note may regenerate content already established unless the contract explicitly permits it.
- **Workflow.** A pointer to `governance/workflow/` stating that the staged pipeline governs all note production and that stages must not be combined.
- **Context injection.** A pointer to the context injection protocol in `governance/workflow/`, stating that each pass receives only its designated governance files, not all files.
- **Conflict resolution.** Priority ordering: note contract over note specification, note specification over global policy, project scope over stylistic preference.

## File naming conventions

Enforce a stable naming discipline

**Contracts**: Use the exact note identifier, e.g., `contracts/active/<note_id>.contract.md` or simply `contracts/active/<note_id>.md`.

**Audits**: Attach the note identifier and audit type, e.g., `audits/active/<note_id>.coherence_audit.md`, or use a single consolidated file: `audits/active/<note_id>.audit.md`.

**Legacy files**: Preserve original names when possible, but prepend status metadata inside the file.
