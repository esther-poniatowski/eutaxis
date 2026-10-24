---
tags: []
aliases:
  - Configuration
index: ""
---

# Configuration

The `generate` command reads a YAML file that declares shared sources, per-agent sources, and output targets. Relative paths resolve against the configured root. By default, the root is the config file's parent directory. A config can override this with the top-level `root` key, and the CLI can override it with `--root`.

Default config file name: `agent-instructions.yaml`.

## Top-level keys

```yaml
root: .                          # optional root for relative paths
common_sources:                  # source entries shared across all agents
task_modules:                    # source entries compiled to Skill artifacts
task_modules_router_enabled:     # default true; set false to suppress the pointer section
skill_entrypoint_max_bytes:      # optional byte limit checked by `skills budget`
skill_loading_units:       # finite task-specific Skill reads and their limits
instruction_chains:              # generated targets plus project instruction files
strict_rule_labels:              # default false; set true to fail generate and check on a rejected label line
agents:                          # cumulative-file targets
```

All keys are optional. An empty `common_sources` list (or omitted key) means no shared content. An empty `agents` list produces no output. Absolute target paths and paths beginning with `~` can target files outside the configured root, such as `~/.codex/AGENTS.md`.

The `common_sources` list feeds the cumulative-file surface (`eutaxis generate`). The `task_modules` list feeds the on-demand Skill surface (`eutaxis skills install`). The two lists are independent. See [Concepts: two compilation surfaces](concepts.md) for the mental model.

## Source entries

Each entry in `common_sources` or an agent's `sources` list has the form:

```yaml
- path: <relative-path-to-markdown-file>
  sections:            # optional
    - "Heading text"
    - "Another heading"
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | yes | Path to a markdown source file, relative to the configured root. |
| `sections` | list of strings | no | Heading titles to extract. When omitted, the full file content is included. |
| `exclude_sections` | list of strings | no | Heading titles to remove. Removed sections include nested subsections. |
| `heading_offset` | integer | no | Number of levels to add to all headings in this source. |
| `strip_frontmatter` | bool | no | Strip top-level YAML frontmatter before assembly. Defaults to `true`. |

When `sections` is present, the generator extracts only the content under headings whose text matches exactly. Each extracted block runs from its heading to the next heading at the same or higher level. YAML frontmatter (`---` fences at the top of a file) is stripped before extraction.

Missing source files abort generation. This prevents stale generated instruction files from silently omitting required modules.

## Task module entries

Each entry in `task_modules` references a Markdown file eligible for compilation to a Skill artifact:

```yaml
task_modules:
  - id: prose-writing-style
    title: Prose writing style
    path: docs/instructions/tasks/prose-writing-style.md
    trigger: when drafting or revising documentation, articles, or long-form prose
    description: How to write expository prose.   # optional; falls back to frontmatter
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | yes | Unique slug identifying the rule set. Used by `eutaxis skills` commands. |
| `title` | string | yes | Human-readable title used in the pointer section when emitted. |
| `path` | string | yes | Path to the source Markdown file, relative to the configured root. |
| `trigger` | string | yes | Plain-language activation hint, surfaced in the pointer section when emitted. |
| `description` | string | no | One-line summary. When omitted, the loader reads it from the source file's YAML frontmatter. |

Each referenced file must declare the source-schema frontmatter required by the Skills compiler (`invocation`, `failure-mode`, optionally `required-visibility`). The fields and their roles are documented in [Concepts: source schema](concepts.md). The Skill compiler refuses to emit an artifact from a file that omits any required field.

The default cumulative file carries a pointer section that lists each `task_modules` entry. When the rule sets are also compiled to Skills via `eutaxis skills install`, the pointer section is redundant; suppress it by setting `task_modules_router_enabled: false` at the top level of the configuration.

## Skill loading budgets ^skill-loading-budgets

The configuration key `skill_entrypoint_max_bytes` limits each rendered `SKILL.md`. A declared loading unit lists the exact entrypoints and rule files for one task:

```yaml
skill_entrypoint_max_bytes: 16384
skill_loading_units:
  - name: prose-batch
    max_bytes: 40000
    members:
      - module: prose-authoring-workflow
        rules:
          - prose-section-tier
          - prose-reading-pass
      - module: prose-writing-style
        include_entrypoint: false
        rules:
          - priority-core
  - name: prose-route
    max_bytes: 92160
    includes:
      - prose-batch
```

Each `module` must match a task-module `id`. The optional `rules` list selects files in `rules/` for that skill. The field `include_entrypoint` defaults to `true`. Set it to `false` only for a direct rule-file dependency that does not activate the Skill. The optional `includes` list composes other declared loading units. Eutaxis deduplicates files shared by several included units and rejects composition cycles.

Use small loading units for tool-read batches and composite loading units for complete task routes. A batch limit prevents one tool response from truncating. A route limit constrains the full context activated by the task. The command `eutaxis skills budget -c <config> --agent <adapter>` reports every entrypoint, batch, and route. The command fails when bytes cross a declared limit or the rendered skill lacks a named rule.

## Cumulative instruction chains

The agent can append project instruction files to one generated target. An instruction chain measures their total bytes:

```yaml
instruction_chains:
  - name: codex-largest-project
    agent: global-codex
    sources:
      - /path/to/largest/project/AGENTS.md
    max_bytes: 106496
```

The `agent` value names an entry in `agents`. Relative source paths resolve against `root`. The measured chain includes the generated target, every project source, and the two newline bytes inserted before each project source. Before writing a target, `eutaxis generate` checks every applicable chain. `eutaxis check` prints the generated-target budget and each cumulative-chain budget separately. Both commands fail if a project source is missing or a chain exceeds its limit.

## Agent definitions

Each entry in `agents` has the following structure:

```yaml
- name: claude
  enabled: true
  target:
    path: .claude/CLAUDE.md
    header: |
      # CLAUDE.md
      Agent instructions (auto-generated).
    footer: |
      ---
      *Auto-generated by eutaxis.*
  sources:
    - path: docs/instructions/claude-specific.md
```

### Agent fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | yes | -- | Identifier for the agent (used in log output). |
| `enabled` | bool | no | `true` | Set to `false` to skip generation for this agent. |
| `target` | mapping | yes | -- | Output file configuration. |
| `sources` | list of source entries | no | `[]` | Agent-specific source files appended after common sources. |
| `max_bytes` | positive integer | no | top-level `max_bytes` or unlimited | Maximum encoded size of this generated target; it does not include project instruction files. |

### Target fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | yes | Output file path, relative to the configured root unless absolute. Parent directories are created automatically. |
| `header` | string | no | Text prepended before all source content. |
| `footer` | string | no | Text appended after all source content. |

## Assembly order

The generator concatenates content for each agent in this order:

1. `target.header` (trimmed)
2. Each `common_sources` entry, in list order
3. Each agent-specific `sources` entry, in list order
4. The task-module router, when enabled and populated
5. The reference-document section, when populated
6. The rule-index section or pointer, when enabled
7. `target.footer` (trimmed)

Parts are joined with double newlines. The output file ends with a single trailing newline.

## Full example

```yaml
common_sources:
  - path: docs/instructions/style-rules.md
    sections:
      - "Hard blockers"
  - path: docs/instructions/note-template.md

agents:
  - name: claude
    enabled: true
    target:
      path: .claude/CLAUDE.md
      header: |
        # CLAUDE.md
      footer: |
        ---
        *Auto-generated by eutaxis.*
    sources:
      - path: docs/instructions/claude-workflow.md

  - name: copilot
    enabled: false
    target:
      path: .github/copilot-instructions.md
    sources:
      - path: docs/instructions/copilot-workflow.md
```

Running `eutaxis generate -c agent-instructions.yaml` with this config writes `.claude/CLAUDE.md` (the claude agent) and skips the disabled copilot agent.

## Global configuration example

A global config can write an absolute target path while sourcing shared modules from a separate agent-config directory:

```yaml
root: ~/agent-config

common_sources:
  - modules/global/file-authority.md
  - modules/global/git-safety.md
  - modules/global/verification.md

agents:
  - name: global-codex
    target:
      path: ~/.codex/AGENTS.md
      header: |
        # Global Agent Instructions
      footer: |
        ---
        *Generated by eutaxis. Do not edit directly.*
```

Running the `generate` command against this configuration writes the file at the absolute target path declared above:

```sh
eutaxis generate -c global-agent-instructions.yaml
```
