---
tags: []
aliases:
  - Usage
index: ""
---

# Usage

Eutaxis assembles instruction files from modular Markdown sources. A single configuration can generate project-local files such as `AGENTS.md` and `.claude/CLAUDE.md`, or global files such as `~/.codex/AGENTS.md`.

## Generate project instructions

Place `agent-instructions.yaml` at the project root and run:

```sh
eutaxis generate -c agent-instructions.yaml
```

Without `-c`, the command defaults to `agent-instructions.yaml`.

To create a starter Codex instruction layout in a project, run:

```sh
eutaxis init --template codex-project --target .
```

After scaffolding, edit the generated files inside the project. Project-specific instructions belong to the project repository, not to a personal configuration repository.

## Check generated files

Use `check` to detect stale generated files:

```sh
eutaxis check -c agent-instructions.yaml
```

Print diffs for stale outputs:

```sh
eutaxis check -c agent-instructions.yaml --diff
```

This command exits with code `1` when any selected output differs from the generated content.

## Scan for unregistered instruction files

Use `scan` to compare the instruction files on disk against the files the config registers:

```sh
eutaxis scan -c agent-instructions.yaml
```

The command reports three groups: registered-and-present, unregistered-and-present, and registered-but-missing. The exit code is `1` when any of the latter two groups is non-empty, which makes the command usable as a CI drift check.

Instruction files whose frontmatter sets `enabled: false` are skipped in the unregistered-present report. Authors use this opt-out flag to keep a draft under the instruction tree without forcing it into the rendered output.

To preview a YAML stanza that would register the unregistered files under `common_sources`, pass `--register`:

```sh
eutaxis scan -c agent-instructions.yaml --register
```

The on-disk config file is never rewritten. The snippet is printed to stdout for the user to paste into the desired section of the config.

Override the directory walked with `--root <dir>`. The default is the union of parent directories of every currently registered instruction file.

## Compile instruction files to Skill artifacts

Use `skills` to compile config-registered instruction files into native Agent Skill artifacts under `~/.claude/skills/<name>/` and `~/.agents/skills/<name>/`. The Skills surface replaces the heuristic router pattern in cumulative instruction files: each rule set ships as a Skill the agent loads when its description matches the task.

The eligibility requirement is the source-schema frontmatter. Each Markdown file listed under `task_modules` carries:

- `name`, `description` — slug and one-line summary.
- `invocation: [user]` or `[model, user]` — permitted invocation routes (list). When `model` is absent, Claude emits `disable-model-invocation: true` and Codex emits `policy.allow_implicit_invocation: false`; when `model` is present, both flags are omitted (user invocation remains available either way).
- `failure-mode: silent | visible` — silent-failure classification per the [failure-mode-as-source-field](../adr/failure-mode-as-source-field.md) ADR.
- `required-visibility: pre-invocation | pre-action` — mandatory when `failure-mode: silent`.

List the configured Skill sources:

```sh
eutaxis skills list -c agent-instructions.yaml
```

Each line shows the regime and failure-mode tags so an author can spot mis-classified sources at a glance.

Preview a single artifact without writing to disk:

```sh
eutaxis skills show <name> -c agent-instructions.yaml --agent claude
```

Install one source (or every source) into the selected adapter:

```sh
eutaxis skills install <name> -c agent-instructions.yaml --agent claude
eutaxis skills install all  -c agent-instructions.yaml
```

The renderer's failure-mode gate refuses to emit a skill that admits model invocation (`"model"` in `invocation`) from a silent-failure source, and any skill from a silent-failure source whose `required-visibility` is `pre-invocation`. There is no `--force` escape for these checks; the source moves to the always-on body instead.

Show drift between rendered output and what is installed on disk:

```sh
eutaxis skills diff -c agent-instructions.yaml
```

## List configured outputs

Use `list` to inspect configured agents, sources and resolved target paths:

```sh
eutaxis list -c agent-instructions.yaml
```

## Generate one output

Filter generation to a single agent output:

```sh
eutaxis generate -c agent-instructions.yaml --agent codex
```

Preview paths without writing files:

```sh
eutaxis generate -c agent-instructions.yaml --dry-run
```

## Configuration structure

The YAML config has two top-level keys:

- **`common_sources`** -- source files included in every agent's output.
- **`agents`** -- per-agent definitions controlling output path, ordering, and agent-specific sources.

Minimal example:

```yaml
common_sources:
  - path: docs/instructions/style-rules.md
  - path: docs/instructions/note-template.md

agents:
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
      - path: docs/instructions/claude-extra.md
```

The generator concatenates content in this order:

1. `target.header` (if present)
2. All `common_sources`, in list order
3. All agent-specific `sources`, in list order
4. `target.footer` (if present)

## Task module descriptions

`task_modules[i].description` is optional. When the config omits it, the loader reads it from the target file's YAML frontmatter (the `description` key). The config-level value, when present, always wins as an explicit override. When both are absent, the loader raises a typed error naming the offending module.

## Section extraction

Each source entry can include a `sections` list to extract only named markdown headings instead of the full file:

```yaml
common_sources:
  - path: docs/instructions/style-rules.md
    sections:
      - "Hard blockers"
      - "Formatting"
```

Section extraction matches heading text exactly and includes all content under that heading until the next heading at the same or higher level. YAML frontmatter in source files is stripped automatically.

Exclude sections with `exclude_sections`:

```yaml
common_sources:
  - path: docs/instructions/style-rules.md
    exclude_sections:
      - "Historical Notes"
```

Offset heading levels when embedding a source inside another structure:

```yaml
common_sources:
  - path: docs/instructions/style-rules.md
    heading_offset: 1
```

## Generate global instructions

Use `root` to point at the source module directory and an absolute target path for the generated global file:

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
```

Run:

```sh
eutaxis generate -c global-agent-instructions.yaml
```

## Disabled agents

Setting `enabled: false` on an agent skips generation for that agent. The generator prints a notice and moves on.

## Python API

Use the Python API when integrating instruction generation into another tool:

```python
from pathlib import Path

from eutaxis.instructions import InstructionGenerator, load_config

config = load_config(Path("agent-instructions.yaml"))
generator = InstructionGenerator(config)
generator.write_all()
```

## Diagnostics

The `info` command prints the installed version and platform details:

```sh
eutaxis info
```

Example output:

```text
eutaxis 0.1.0 | Platform: Darwin Python 3.12.5
```

The `--version` flag prints only the version string:

```sh
eutaxis --version
```

## Planned commands

### validate (stub)

```sh
eutaxis validate <paths...>
```

Validates prompt layouts and configuration files. Currently prints "Prompt validation is not yet implemented."
