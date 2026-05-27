---
tags: []
aliases:
  - Usage
index: ""
---

# Usage

This page sequences the operations a maintainer performs on an eutaxis configuration, from first setup to ongoing maintenance. It assumes the mental model from [Concepts](concepts.md). For command-by-command reference (options, exit codes), see [CLI Reference](cli-reference.md). For the YAML schema reference, see [Configuration](configuration.md).

## Get started

The first three steps take a fresh project from no configuration to one generated cumulative instruction file. The fourth step is optional and covers on-demand Skill artifacts.

### 1. Install eutaxis

Follow [Installation](installation.md) for prerequisites and source-install instructions. Verify with:

```sh
eutaxis info
```

### 2. Author or scaffold a configuration

The fastest path is the project scaffolder:

```sh
eutaxis init --template codex-project --target .
```

The command writes a starter `agent-instructions.yaml`, an `AGENTS.md` placeholder, and a `docs/instructions/` tree. Two templates are available; see [Project scaffolding](project-scaffolding.md) for the difference between them.

A configuration may also be written by hand. A minimal example:

```yaml
common_sources:
  - path: docs/instructions/file-authority.md
  - path: docs/instructions/environment-safety.md

agents:
  - name: codex
    target:
      path: AGENTS.md
```

### 3. Generate the cumulative instruction file

```sh
eutaxis generate -c agent-instructions.yaml
```

The command writes the file declared under `agents[0].target.path` (the project `AGENTS.md` in the example above). The on-disk path is also reported by `eutaxis list -c agent-instructions.yaml`.

Without the `-c` flag, `eutaxis generate` defaults to `agent-instructions.yaml` in the current directory.

### 4. Compile on-demand rule sets to Skills (optional)

This step applies only when the configuration's `task_modules` list is non-empty and the referenced files carry the source-schema frontmatter (`invocation`, `failure-mode`, optionally `required-visibility`). See [Concepts: source schema](concepts.md) for the schema, and [Concepts: failure-mode gate](concepts.md) for the placement rules.

Inspect the configured Skill sources first:

```sh
eutaxis skills list -c agent-instructions.yaml
```

Each line shows the invocation routes and the failure-mode tag, surfacing misclassified sources before any artifact is written.

Install every configured Skill source on every registered adapter:

```sh
eutaxis skills install all -c agent-instructions.yaml
```

The command writes one directory per rule set into the user-scope skill directory of every registered agent. The directories are dual-marker-owned, so re-running the command is idempotent and uninstall is safe. The concrete directory paths used by each agent are listed in the [Supported agents](../../README.md#supported-agents) table.

## Author always-on globals

The cumulative instruction file carries rules that must hold on every turn. The `common_sources` list in the configuration defines its content.

### Project-local versus global targets

Two deployment patterns differ only in the configuration's `root` field and the target paths:

- **Project-local.** The configuration sits at the project root; `root` is absent (defaults to the configuration's parent directory); target paths are project-relative.
- **Global.** The configuration sits outside any single project (typically a personal configuration repository); `root` points at that repository; target paths are absolute paths to each agent's global instruction file (see the [Supported agents](../../README.md#supported-agents) table for the per-agent paths).

A global configuration with two agent outputs:

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
  - name: global-claude
    target:
      path: ~/.claude/CLAUDE.md
      header: |
        # Global Claude Code Instructions
```

### Header and footer

A `target.header` block is prepended before the assembled body; a `target.footer` block is appended after it. Both are optional. Use them for top-level titles, generated-file warnings, or attribution.

### Multiple agent outputs from one configuration

A single configuration may declare any number of agent outputs. Each entry under `agents` produces one cumulative file:

```yaml
agents:
  - name: codex
    target:
      path: AGENTS.md
  - name: claude
    target:
      path: .claude/CLAUDE.md
  - name: copilot
    target:
      path: .github/copilot-instructions.md
```

Generation writes all enabled outputs. To restrict generation to one agent:

```sh
eutaxis generate -c agent-instructions.yaml --agent codex
```

To skip an output without removing it from the configuration, set `enabled: false` on the agent entry. The generator prints a notice and proceeds with the remaining outputs.

### Section extraction from a broader source

A source entry may extract only named sections of a broader Markdown file:

```yaml
common_sources:
  - path: docs/instructions/style-rules.md
    sections:
      - "Hard blockers"
      - "Formatting"
```

The extraction matches heading text exactly and includes every nested subsection until the next heading at the same or higher level. YAML frontmatter in the source file is stripped automatically.

The complementary `exclude_sections` field removes named sections from an otherwise included file. The `heading_offset` field shifts the heading levels of the extracted content when embedding it inside another structure. Full syntax is documented in [Configuration: source entries](configuration.md).

### Suppress the task-modules pointer section

When `task_modules` is populated and is also compiled to Skills, the default cumulative file carries a pointer section that is now redundant. Set `task_modules_router_enabled: false` at the top level of the configuration to suppress the pointer section while keeping the list available for the Skills compiler:

```yaml
task_modules_router_enabled: false
task_modules:
  - id: prose-writing-style
    ...
```

The cumulative file shrinks; the Skill artifacts continue to be produced by `eutaxis skills install`.

## Author on-demand rule sets as Skills

A rule set authored under `task_modules` becomes a Skill artifact when the source file declares the source-schema frontmatter and `eutaxis skills install` is run.

### Required source-schema frontmatter

Every Markdown file listed under `task_modules` must declare:

```markdown
---
name: prose-writing-style
description: How to write expository prose — documentation, articles, long-form text.
invocation: [model, user]
failure-mode: visible
---
```

The four required fields and their roles are documented in [Concepts: source schema](concepts.md). A source missing any required field raises a typed error naming the file and the missing field. The failure-mode gate refuses two placements; both refusals carry the source path and the violated rule.

### Render a single Skill before installing

```sh
eutaxis skills show <name> -c agent-instructions.yaml --agent claude
```

The command prints the rendered `SKILL.md` and any sibling files to stdout, without writing to disk. Use it to confirm the frontmatter and body before committing to an install.

### Install one Skill or every Skill

```sh
eutaxis skills install <name> -c agent-instructions.yaml --agent claude
eutaxis skills install all  -c agent-instructions.yaml
```

Without `--agent`, every registered adapter receives the Skill (see the [Supported agents](../../README.md#supported-agents) table for the current set). Without `--scope`, the install uses the source's declared `scope_default` (typically `user`, writing into the user-scope skill directory of each agent); `--scope project` writes into the project-scope skill directory instead.

### Detect drift

```sh
eutaxis skills diff -c agent-instructions.yaml
```

The command compares each rendered Skill artifact against its installed directory and reports drift. Exit code `1` on drift makes the command usable as a CI check.

### Uninstall

```sh
eutaxis skills uninstall <name> -c agent-instructions.yaml --agent claude
```

The dual ownership marker prevents the command from removing directories Eutaxis did not write.

## Verify and maintain

Four commands cover the recurring maintenance loop.

### Detect cumulative-file drift

```sh
eutaxis check -c agent-instructions.yaml
eutaxis check -c agent-instructions.yaml --diff
```

The first form reports `OK` or `OUTDATED` per agent and exits with code `1` when any output differs from the rendered content. The `--diff` flag prints a unified diff for each `OUTDATED` output.

### Detect Skill-artifact drift

```sh
eutaxis skills diff -c agent-instructions.yaml
```

Same purpose as `check` but for Skill directories instead of cumulative files. Equivalent exit-code semantics.

### Detect registry drift

```sh
eutaxis scan -c agent-instructions.yaml
```

The command compares the Markdown files registered in the configuration against the files present in the directories it walks. It reports three groups: registered-and-present, unregistered-and-present, and registered-but-missing. Exit code `1` when either of the latter two groups is non-empty.

Instruction files whose frontmatter declares `enabled: false` are skipped in the unregistered-present report. The flag opts a draft file out of the registry without forcing it into the rendered output.

To preview a YAML snippet that would register every unregistered file under `common_sources`:

```sh
eutaxis scan -c agent-instructions.yaml --register
```

The on-disk configuration is never rewritten. The snippet is printed to stdout for manual review and paste.

### Inspect the configuration

```sh
eutaxis list -c agent-instructions.yaml
```

The command prints every agent entry, its enabled status, its resolved target path, and any agent-specific sources. Useful for auditing what a configuration would actually produce before running `generate`.

## Advanced patterns

### Override `description` from a source's frontmatter

When a `task_modules` entry omits the `description` field, the loader reads `description` from the referenced file's YAML frontmatter. A configuration-level value, when present, always wins as an explicit override. Both absent raises a typed error naming the offending module.

### Python API

The Python API is suitable for embedding generation in another tool:

```python
from pathlib import Path

from eutaxis.instructions import InstructionGenerator, load_config

config = load_config(Path("agent-instructions.yaml"))
generator = InstructionGenerator(config)
generator.write_all()
```

For configuration loading, Markdown transformations, and exception types, see [Instruction assembly API](../api/instructions.md).

### Diagnostics

```sh
eutaxis info       # version + platform
eutaxis --version  # version only
```

### Built-in commands subsystem

The `eutaxis commands` subsystem covers built-in skills whose body is authored as a Markdown template with shell-backed actions. Today the subsystem ships one entry, `clean-memory`:

```sh
eutaxis commands install clean-memory
eutaxis ops clean-memory
```

The first form installs the skill into the user-scope skill directory of every registered agent and registers it. The second form runs the underlying operation directly, which is also what the installed skill's action invokes.

The commands subsystem is distinct from the config-driven `skills` subcommand: `commands` discovers sources from layered directories (built-in, user, project) under `~/.eutaxis/commands/`; `skills` discovers sources from the `task_modules` list of an instruction-assembly configuration.
