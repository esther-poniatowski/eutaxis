# eutaxis

[![Maintenance](https://img.shields.io/maintenance/yes/2026)](https://github.com/esther-poniatowski/eutaxis)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.12-blue)](https://www.python.org/)
[![License: GPL](https://img.shields.io/badge/License-GPL--3.0-yellow.svg)](https://opensource.org/licenses/GPL-3.0)

Builds structured agent prompts from reusable fragments.

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

Eutaxis composes, renders, and validates structured agent prompts. Domain rules
stay in the projects that own them; eutaxis provides the composition workflow,
reusable templates, and prompt-authoring methodology.

### Motivation

High-quality agent prompts share recurring structure: role definitions, evidence
standards, report contracts, scope guards, and output formats. Without composition
tooling, authors either duplicate that structure across prompt sets or maintain
large monolithic files that are hard to review, test, and revise.

### Advantages

- **Prompt families** — prompts are grouped into families that share authoring
  workflows, methodology patterns, output contracts, and testing strategies.
- **Shell-first composition** — each prompt owns an explicit top-level shell that
  determines final ordering, bridging text, and prompt-level coherence.
- **Parameterized bundles** — shared methodology structure is single-source;
  domain-specific content is injected through template variables.
- **Profile-based validation** — family profiles distinguish hard assembly
  requirements from advisory guidance.
- **Golden-file review** — composed prompts render into reviewable output, enabling
  diff-based iteration and behavioral testing.

---

## Features

- [ ] **Prompt composer**: Assemble prompts from shells, local fragments, and
  parameterized bundles via Jinja2 rendering.
- [X] **Agent instruction assembly**: Generate global and project-local
  instruction files from modular Markdown sources and YAML configuration.
- [ ] **Prompt validator**: Enforce family profile requirements (required files,
  required tags, length warnings).
- [ ] **Golden-file output**: Render composed prompts for diff-based review.
- [X] **Prompt-writing methodology**: Ships `docs/prompt-writing-methods/_index.md`, the
  foundational reference for agent instruction design.
- [ ] **Workspace scaffolder**: Initialize prompt-composition structure in a target
  project.

---

## Quick Start

```sh
eutaxis generate -c agent-instructions.yaml
```

Check whether generated instruction files are current:

```sh
eutaxis check -c agent-instructions.yaml
```

The same generator can target project-local files such as `AGENTS.md` and
global files such as `/Users/eresther/.codex/AGENTS.md` by setting `root` and
absolute target paths in the config.

Instruction assembly lives under `eutaxis.instructions`: configuration loading,
Markdown transformations, generation, and exceptions are separate modules. The
older `eutaxis.generate` import path remains as a compatibility facade.

---

## Documentation

| Guide | Content |
| ----- | ------- |
| [Installation](docs/guide/installation.md) | Prerequisites and source setup |
| [Usage](docs/guide/usage.md) | Instruction generation workflows |
| [CLI Reference](docs/guide/cli-reference.md) | Commands and options |
| [Configuration](docs/guide/configuration.md) | YAML schema and examples |
| [Concepts](docs/guide/concepts.md) | Sources, outputs, project and global generation |
| [Instruction Assembly API](docs/api/instructions.md) | Python API for config loading, generation and checks |
| [Proposal](PROPOSAL.md) | Architectural proposal for the composition framework |

### Ecosystem

Eutaxis provides composition infrastructure for projects that own domain rules:

- [vitruv](https://github.com/esther-poniatowski/vitruv) — software architecture
  standards and audit prompts.
- [hermeneia](https://github.com/esther-poniatowski/hermeneia) — writing quality
  standards and prose audit prompts.

---

## Contributing

Contribution guidelines are described in [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Acknowledgments

### Authors

**Author**: @esther-poniatowski

For academic use, the GitHub "Cite this repository" feature generates citations in
various formats. The [citation metadata](CITATION.cff) file is also available.

---

## License

This project is licensed under the terms of the
[GNU General Public License v3.0](LICENSE).
