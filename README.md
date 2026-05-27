# eutaxis

[![Conda](https://img.shields.io/badge/conda-eresthanaconda--channel-blue)](docs/guide/installation.md)
[![Maintenance](https://img.shields.io/maintenance/yes/2026)]()
[![Last Commit](https://img.shields.io/github/last-commit/esther-poniatowski/eutaxis)](https://github.com/esther-poniatowski/eutaxis/commits/main)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.12-blue)](https://www.python.org/)
[![License: GPL](https://img.shields.io/badge/License-GPL--3.0-yellow.svg)](https://opensource.org/licenses/GPL-3.0)

Assemble agent instruction files from modular Markdown sources.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Quick Start](#quick-start)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [Acknowledgments](#acknowledgments)
- [License](#license)

## Overview

Eutaxis assembles agent instruction files from one configuration. The same rules reach every supported agent and every project that references them, without manual duplication and without per-agent forks.

### Motivation

Coding-assistant agents read their guidance from on-disk files specific to each platform. Maintaining the same rule sets across several agents and several projects creates duplication, drifts toward inconsistency, and forces every edit to be replayed by hand. Authoring instruction sets as monolithic per-agent files makes review, testing, and reuse harder still.

### Advantages

- **Single source of truth.** Each rule is authored once as a Markdown module. The configuration declares where it appears; the tool propagates the change.
- **Agent-neutral authoring.** Modules describe what the agent must do; the per-agent translation (file path, frontmatter, marker conventions) is handled by adapters.
- **Two activation regimes.** Always-on rules compile into the cumulative instruction file each agent loads on every turn; on-demand rule sets compile into native Agent Skill artifacts loaded only when their description matches the active task.
- **Drift detection.** Configuration, sources, and on-disk targets are kept in sync by explicit drift checks usable in CI.
- **Extensible to new agents.** Support for a new agent reduces to a single adapter registration; the authoring surface does not change.

### Supported agents

| Agent | Cumulative file | Skill directory |
| --- | --- | --- |
| Claude Code | `~/.claude/CLAUDE.md` (global) or `.claude/CLAUDE.md` (project) | `~/.claude/skills/<name>/` (user) or `.claude/skills/<name>/` (project) |
| Codex | `~/.codex/AGENTS.md` (global) or `AGENTS.md` (project) | `~/.agents/skills/<name>/` (user) or `.agents/skills/<name>/` (project) |

Additional agents are added by registering one adapter in `src/eutaxis/commands/adapters/`. See [Architecture decisions](docs/adr/_index.md) for the adapter contract.

---

## Features

- [X] **Instruction assembly** — render modular Markdown sources into one cumulative instruction file per agent.
- [X] **Skill compilation** — compile on-demand rule sets into native Agent Skill artifacts.
- [X] **Drift detection** — compare configuration, sources, and on-disk targets; usable as a CI gate.
- [X] **Registry hygiene** — surface instruction files present on disk but absent from the configuration, and vice versa.
- [X] **Project scaffolding** — initialise a starter instruction layout in a project.
- [X] **Prompt-writing methodology** — reference notes on agent instruction design under `docs/prompt-writing-methods/`.
- [ ] **Prompt composition framework** — planned. Compose prompts from shells, local fragments, and parameterised bundles.
- [ ] **Prompt validator** — planned. Enforce family-profile requirements.
- [ ] **Golden-file output** — planned. Render composed prompts for diff-based review.

---

## Quick Start

A minimal project configuration:

```yaml
# agent-instructions.yaml
common_sources:
  - path: docs/instructions/file-authority.md
  - path: docs/instructions/verification.md

agents:
  - name: codex
    target:
      path: AGENTS.md
```

Render the cumulative file:

```sh
eutaxis generate -c agent-instructions.yaml
```

The full first-time walkthrough — installation, scaffolding, on-demand Skill compilation — lives in [Usage: get started](docs/guide/usage.md).

---

## Documentation

| Guide | Content |
| ----- | ------- |
| [Installation](docs/guide/installation.md) | Prerequisites and source setup. |
| [Concepts](docs/guide/concepts.md) | Mental model behind the configuration: compilation surfaces, source schema, activation regimes. |
| [Usage](docs/guide/usage.md) | Step-by-step workflows from first setup to ongoing maintenance. |
| [CLI Reference](docs/guide/cli-reference.md) | Commands, options, exit codes. |
| [Configuration](docs/guide/configuration.md) | YAML schema and worked examples. |
| [Project Scaffolding](docs/guide/project-scaffolding.md) | Starter templates. |
| [Instruction Assembly API](docs/api/instructions.md) | Python API for embedding generation in another tool. |
| [Proposal](PROPOSAL.md) | Architectural proposal for the broader composition framework. |

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
