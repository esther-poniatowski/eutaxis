# eutaxis

[![Maintenance](https://img.shields.io/maintenance/yes/2026)](https://github.com/esther-poniatowski/eutaxis) [![Python](https://img.shields.io/badge/python-%E2%89%A53.12-blue)](https://www.python.org/) [![License: GPL](https://img.shields.io/badge/License-GPL--3.0-yellow.svg)](https://opensource.org/licenses/GPL-3.0)

Eutaxis assembles agent instruction files from modular Markdown sources. A single YAML configuration drives two compilation surfaces: the cumulative instruction file each agent loads on every turn (Codex `AGENTS.md`, Claude Code `CLAUDE.md`), and the on-demand Agent Skill artifacts each agent loads when a skill description matches the active task (directories under `~/.claude/skills/` and `~/.agents/skills/`). Both surfaces share one source-of-truth tree, so a rule authored once propagates to every agent target and every project that references it.

---

## Table of contents

- [Compilation surfaces](#compilation-surfaces)
- [Getting started](#getting-started)
- [Common tasks](#common-tasks)
- [Documentation](#documentation)
- [Ecosystem](#ecosystem)
- [Contributing](#contributing)
- [Acknowledgments](#acknowledgments)
- [License](#license)

## Compilation surfaces

The two surfaces correspond to two activation regimes built into Claude Code and Codex:

- **Cumulative instruction file** — every line enters the agent's context on every turn. The `eutaxis generate` command assembles the file from the modules listed under `common_sources` in the configuration. This surface carries unconditional rules — file authority, environment safety, verification policy.
- **On-demand Skill artifact** — one directory per rule set, loaded by the agent's native skill loader only when the rule set's description matches the active task. The `eutaxis skills install` command compiles each Markdown file listed under `task_modules` into a Skill artifact for every registered adapter. This surface carries task-specific rule sets — prose style, mathematical exposition, git workflow conventions.

Both surfaces read from the same configuration. A rule set listed under `task_modules` declares its eligibility for Skill compilation in its YAML frontmatter (`invocation`, `failure-mode`, optionally `required-visibility`). The renderer refuses placements that would route a silent-failure rule through the model's invocation gate; see the [failure-mode-as-source-field](docs/adr/failure-mode-as-source-field.md) ADR.

For the conceptual model behind these surfaces, read [Concepts](docs/guide/concepts.md). For the CLI surface, read [CLI Reference](docs/guide/cli-reference.md).

## Getting started

The walkthrough below assumes a single project that contains both shared and task-specific instruction modules. For the global-instruction pattern (one configuration that writes `~/.codex/AGENTS.md` and `~/.claude/CLAUDE.md`), see [Usage: author always-on globals](docs/guide/usage.md).

1. **Install the package.** See [Installation](docs/guide/installation.md) for prerequisites and source-install instructions.

2. **Scaffold a starter layout** (optional) inside an empty or existing project directory:

   ```sh
   eutaxis init --template codex-project --target .
   ```

   The command writes `AGENTS.md`, `agent-instructions.yaml`, and a starter `docs/instructions/` tree. See [Project scaffolding](docs/guide/project-scaffolding.md) for available templates.

3. **Generate the cumulative instruction file** declared in the configuration:

   ```sh
   eutaxis generate -c agent-instructions.yaml
   ```

   Inspect the written file. The on-disk path is recorded in the `target.path` field of each agent entry; the default scaffold writes `AGENTS.md` at the project root.

4. **Compile on-demand rule sets to Skills** (optional, only when `task_modules` is non-empty). Each Markdown file listed under `task_modules` must declare the source-schema frontmatter (`invocation`, `failure-mode`, optionally `required-visibility`); see [Concepts: source schema](docs/guide/concepts.md):

   ```sh
   eutaxis skills install all -c agent-instructions.yaml
   ```

   The command writes one directory per rule set under `~/.claude/skills/<name>/` and `~/.agents/skills/<name>/`.

For day-to-day operations after the first run, see the table below.

## Common tasks

The commands are grouped by use case rather than alphabetically.

### Daily

| Command | Purpose |
| ------- | ------- |
| `eutaxis generate -c <config>` | Regenerate every active cumulative instruction file. |
| `eutaxis skills install all -c <config>` | Recompile every `task_modules` source to a Skill artifact and update the installed directories. |
| `eutaxis check -c <config>` | Detect drift between the rendered cumulative file and the on-disk file. Exit code `1` on drift. Useful in CI. |
| `eutaxis skills diff -c <config>` | Detect drift between rendered Skill artifacts and the installed directories. |

### Inspection

| Command | Purpose |
| ------- | ------- |
| `eutaxis generate -c <config> --dry-run` | List the cumulative-file targets without writing. |
| `eutaxis list -c <config>` | List configured agent outputs and their resolved targets. |
| `eutaxis skills list -c <config>` | List `task_modules` sources with their invocation routes and failure-mode tags. |
| `eutaxis skills show <name> -c <config>` | Render a single Skill artifact to stdout, without writing. |
| `eutaxis info` | Print the installed eutaxis version and platform diagnostics. |

### Drift and registry hygiene

| Command | Purpose |
| ------- | ------- |
| `eutaxis scan -c <config>` | Report instruction files on disk that are not registered in the configuration, and registered files that are missing on disk. Exit code `1` on drift. |
| `eutaxis scan -c <config> --register` | Print a paste-ready YAML snippet that registers any unregistered files. The configuration file itself is never rewritten. |

### Commands subsystem

| Command | Purpose |
| ------- | ------- |
| `eutaxis commands install clean-memory` | Install the built-in `clean-memory` skill on every registered agent. The commands subsystem covers built-in skills authored as Markdown templates with shell-backed actions, distinct from the config-driven `skills` subcommand above. |
| `eutaxis ops clean-memory` | Run the `clean-memory` operation directly (used as the action body inside the installed skill). |

A regenerate-instructions skill that wraps `eutaxis generate` as a slash command is not yet shipped. The shape of such a skill — a one-shot CLI invocation rather than a Markdown body — does not match the current `commands` subsystem, whose skill sources are authored as Markdown (`src/eutaxis/data/commands/*.md`). Run `eutaxis generate -c <config>` directly until that surface lands.

---

## Documentation

| Guide | Content |
| ----- | ------- |
| [Installation](docs/guide/installation.md) | Prerequisites and source setup. |
| [Concepts](docs/guide/concepts.md) | Compilation surfaces, source schema, activation regimes — the mental model behind the CLI. Read this before the Usage guide. |
| [Usage](docs/guide/usage.md) | Step-by-step workflows: author always-on globals, author on-demand rule sets, verify and maintain. |
| [CLI Reference](docs/guide/cli-reference.md) | Commands, options, exit codes. |
| [Configuration](docs/guide/configuration.md) | YAML schema and worked examples. |
| [Project scaffolding](docs/guide/project-scaffolding.md) | Starter templates. |
| [Instruction assembly API](docs/api/instructions.md) | Python API for embedding generation in another tool. |
| [Proposal](PROPOSAL.md) | Architectural proposal for the broader composition framework (forward-looking). |

### Ecosystem

Eutaxis provides composition infrastructure for projects that own domain rules:

- [vitruv](https://github.com/esther-poniatowski/vitruv) — software architecture standards and audit prompts.
- [hermeneia](https://github.com/esther-poniatowski/hermeneia) — writing quality standards and prose audit prompts.

---

## Contributing

Contribution guidelines are described in [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Acknowledgments

### Authors

**Author**: @esther-poniatowski

For academic use, the GitHub "Cite this repository" feature generates citations in various formats. The [citation metadata](CITATION.cff) file is also available.

---

## License

This project is licensed under the terms of the [GNU General Public License v3.0](LICENSE).
