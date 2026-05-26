# Registries and validation

This file specifies the registries and the validation toolchain that govern a vault under eutaxis. The vault is treated as a graph of typed content units rather than a flat collection of documents. The registries make the global structure explicit, so that automated checks, an agent, and a human supervisor share one description of the vault state.

The specifics of the typed vocabulary (content kinds, output types, statement roles) are project-specific and must be declared in the project's governance directory. This file fixes the *shape* of the registries and the *contract* of the toolchain, while the entries are domain-defined.

---

## Format

Maintain machine-readable indexes (YAML or JSON) usable simultaneously by a human supervisor, a program, and an agent.

> [!WARNING] Avoid duplicating registry logic at every scale
> - **Workspace level** holds only the project catalog and global terminology, when shared across projects.
> - **Project level** holds the authoritative registries for the project.
> - **Module level** holds at most a local index, not a duplicate of the project graph.

---

## Registry files

### Content graph

**Role.** Encodes the dependencies between notes as a typed graph. A note rarely depends on another note as a whole, since it depends on a specific declared object inside that note. Without typed imports, the dependency list is a citation list rather than a structural map, and coarse dependencies are a primary cause of accidental overlap and hidden duplication.

**Suggested fields per note entry:**

- `id`, `path`: identification and location;
- `type`: one of the project-declared note types;
- `status`: a value from the project-declared status enum (see [Status transitions](#^status-transitions));
- `objective`: the note's local purpose;
- **typed imports**: each import names the source note, the kind of object imported, the object name, and optionally its role inside the importing note;
- **typed outputs**: each output declares an ID, an object type from the project's output enum, and a statement role;
- `consumers`: downstream note IDs that use this note's outputs;
- `revision_history`: change log.

**Project-declared enums.** The set of admissible import kinds, output types, and statement roles is project-specific and declared in the project's governance directory. The registry schema enforces that every entry's `kind`, `type`, and `statement_role` come from the declared enum.

**Upstream-instability propagation.** When a completed note is revised, downstream consumers may silently inherit stale inputs. The registry tracks this explicitly: when a note's status transitions to `revised`, three fields appear — `revision_note` (what changed), `downstream_affected` (consumer note IDs), and `propagation_status`.

`propagation_status` values:

- **unresolved**: the revision has not been checked against downstream consumers;
- **checked**: downstream consumers have been inspected; some require revision;
- **cleared**: all downstream consumers have been confirmed or updated.

**Drafting gate.** Before any drafting pass begins, the agent checks whether any declared import has `propagation_status: unresolved`. If so, drafting is blocked until the upstream instability is resolved — either by confirming that the importing note's content remains valid under the revised input, or by revising the importing note itself. ^drafting-gate

### Open questions

**Role.** Enumerates unresolved tasks, so that the next note is determined by the registry rather than by ad-hoc choice.

**Suggested fields per entry:** `id`, `priority` (high / medium / low), `question` (the open question as a sentence), `prerequisite_notes` (note IDs that must be completed first), `status` (pending / in-progress / done), `blocking_reason`.

### Dependencies

**Role.** Tracks reusable objects and their provenance, thereby reducing accidental redefinition and hidden duplication.

**Suggested fields per entry:** `id`, `kind` (from the project's import-kind enum), a provenance field whose name depends on the kind (e.g. `defined_in`, `produced_in`), optional kind-specific fields declared by the schema, and `imported_by` (note IDs that use the object). The schema enables the validation toolchain to detect regenerations, orphaned objects, and missing imports.

### Terminology

**Role.** Keeps naming stable across notes. Terminology drift — variant names for the same concept — silently degrades cross-note coherence and makes dependency tracking unreliable. The terminology registry is enforced by an automated linter at the draft and audit stages.

**Suggested fields per entry:** `canonical_name` (the authorized term) and `forbidden_variants` (strings the linter flags and replaces).

---

## Validation toolchain

Registry corruption is a silent, compounding failure: it does not surface immediately but progressively degrades the agent's ability to reason about the vault's established content. Validation must be **external, automated, and a hard gate** — it cannot rely on the agent's self-correction.

### Architecture ^validation-architecture


| Layer | Mechanism | Failure mode addressed |
| --- | --- | --- |
| **Schema enforcement** | JSON Schema validation on write | Field name drift, missing required fields, type errors |
| **Referential integrity** | Cross-registry ID resolution script | Dangling dependency IDs, references to non-existent notes |
| **Graph integrity** | Cycle detection on dependency edges | Circular dependencies introduced silently |
| **Uniqueness checks** | ID and path uniqueness validation | Duplicate entries |
| **Status transitions** | Permitted-transition validation | Arbitrary status changes |
| **Terminology enforcement** | Linter scanning note prose against the terminology registry | Naming drift across notes |
| **Human gate** | Diff-based review of all registry mutations | Semantic errors that pass structural checks |

### Schema requirements ^schema-requirements

**Directory.** `governance/schemas/`. One JSON Schema per registry file: `content_graph.schema.json`, `dependencies.schema.json`, `open_questions.schema.json`, `terminology.schema.json`. Critical properties:

- **`additionalProperties: false`** on all note entries: prevents silently accepted novel field names from a drifting agent;
- **Typed imports** enforced in schema: `imports` entries must have `from`, `kind`, and `object` fields, rather than bare note IDs;
- **Enumerated types**: `type`, `status`, `propagation_status`, import `kind`, and output `statement_role` must be enum-constrained;
- **ID format**: a uniform identifier pattern enforced across all IDs (e.g. `^[a-z0-9-]+$`).

### Status transitions ^status-transitions

The set of admissible statuses and their permitted transitions is project-declared. The schema enforces both. As a baseline pattern that suits most vaults:

| From | Allowed transitions |
| --- | --- |
| `pending` | `in-progress` |
| `in-progress` | `done`, `pending` (with justification) |
| `done` | `revised` |
| `revised` | `done` |

Any transition outside the declared set is a validation error.

### Staging area

The agent must never modify live registry files directly. All proposed updates land in `registries/staging/`. Promotion to the live `registries/` directory requires:

1. all automated validation checks pass with zero errors;
2. a human reviews the structured diff between live and staging for semantic correctness — naming consistency, transition legitimacy, dependency justification, completeness of consumer lists;
3. on approval, staging is promoted to live; on rejection, field-level errors return to the agent and the cycle repeats;
4. confirmation validation runs against the promoted state to guard against copy errors.

### Tooling ^tooling

Three scripts in `tools/`:

- **`validate_registry.py`**: schema validation, ID uniqueness, path existence, referential integrity, cycle detection on dependency edges, status-transition validity, propagation consistency, cross-registry consistency. Exits non-zero on any failure.
- **`registry_diff.py`**: produces a structured diff between live and staging registries, showing all mutations by change type (added, removed, modified) with old and new values.
- **`lint_terminology.py`**: scans note Markdown files against the terminology registry. For each `preferred_terms` entry, searches for `forbidden_variants` in the prose and reports violations with the canonical replacement. Also flags terms that appear to introduce new concepts absent from the registry. Exits non-zero on any forbidden-variant match.
