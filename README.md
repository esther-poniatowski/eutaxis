# eutaxis

[![Maintenance](https://img.shields.io/maintenance/yes/2026)]()
[![Python](https://img.shields.io/badge/python-%E2%89%A53.12-blue)](https://www.python.org/)
[![License: GPL](https://img.shields.io/badge/License-GPL--3.0-yellow.svg)](https://opensource.org/licenses/GPL-3.0)

Governance toolkit that enforces quality standards in AI-assisted research writing.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
- [Architecture](#architecture)
- [Contributing](#contributing)
- [License](#license)

## Overview

Eutaxis provides a reusable governance framework for AI-assisted research writing. It ships
modular specifications (decision rules, note-type definitions, contract templates, audit
checklists, workflow definitions) alongside validation tooling and a style linter, so that
any project requiring structured AI generative tasks can import a consistent quality system.

### Motivation

AI agents producing research notes tend to drift in scope, accumulate loosely related material,
and optimize visible sophistication over inferential usefulness. Eutaxis addresses this by
externalizing governance into explicit, machine-readable specifications that constrain the
agent's inferential behavior before, during, and after note generation.

### Advantages

- **Modular governance**: decision rules, contracts, audits, and workflows are separate files
  that can be selectively imported or overridden per project.
- **Dual import mechanism**: usable as a Git submodule for rapid iteration, or as a pip/conda
  package for stable deployment.
- **Overridable style linting**: ships default rules derived from mathematical writing best
  practices, with per-project override support.
- **Instruction-file generation**: assembles agent instruction files (CLAUDE.md, AGENTS.md,
  copilot-instructions.md) from modular governance sources and project-specific configuration.
- **Registry validation**: validates machine-readable project state (reasoning graphs, open
  questions, terminology, dependencies) against JSON schemas.

---

## Features

- [X] **Style linter**: Markdown linter for math-heavy research notes with overridable rules.
- [ ] **Instruction generator**: Assemble agent instruction files from governance sources.
- [ ] **Registry validator**: Validate YAML registries against JSON schemas.
- [ ] **Workspace scaffolder**: Initialize governance structure in a target workspace.
- [ ] **Terminology linter**: Check prose against a terminology registry.

---

## Installation

### As a Git submodule (recommended during development)

```bash
git submodule add https://github.com/eresther/eutaxis.git vendor/eutaxis
git submodule update --init --recursive
```

Consuming projects reference governance files directly from `vendor/eutaxis/src/eutaxis/data/`.

### Using pip

```bash
pip install git+https://github.com/eresther/eutaxis.git
```

### From source

1. Clone the repository:

      ```bash
      git clone https://github.com/eresther/eutaxis.git
      ```

2. Create a dedicated virtual environment and install:

      ```bash
      cd eutaxis
      conda env create -f environment.yml
      conda activate eutaxis
      pip install -e ".[dev]"
      ```

---

## Quick Start

### CLI

```sh
eutaxis --help
eutaxis info
```

### Style linting

```sh
eutaxis lint path/to/notes/
eutaxis lint --config my-overrides.yaml path/to/file.md
```

### Python

```python
import eutaxis

eutaxis.info()
```

---

## Usage

### Command Line Interface (CLI)

```sh
# Display version and diagnostics
eutaxis info

# Lint Markdown files against style rules (with optional overrides)
eutaxis lint [--config overrides.yaml] <paths...>

# Generate agent instruction files from governance sources (planned)
eutaxis generate --config agent-instructions.yaml

# Validate registry files against schemas (planned)
eutaxis validate registry/

# Scaffold governance structure into a workspace (planned)
eutaxis init --target /path/to/workspace
```

### Programmatic Usage

```python
from eutaxis.lint import lint_file, load_config

# Lint with default rules
issues = lint_file(Path("my-note.md"))

# Lint with project-specific overrides
config = load_config(Path("my-overrides.yaml"))
issues = lint_file(Path("my-note.md"), config=config)
```

---

## Architecture

Eutaxis is a data-heavy package: the primary payload is governance specifications (Markdown,
YAML, JSON), with a thin Python tooling layer for validation, linting, and assembly.

| Layer | Modules | Responsibility |
| ----- | ------- | -------------- |
| Data | `data/governance/` | Decision rules, note specs, contracts, audits, workflows, schemas |
| Data | `data/registries/` | Registry templates |
| Data | `data/templates/` | Workspace scaffolding templates |
| Application | `generate` | Instruction-file assembly from governance sources |
| Application | `validate` | Registry validation against JSON schemas |
| Application | `lint` | Style linting with overridable rule configuration |
| Application | `scaffold` | Workspace initialization and governance scaffolding |
| Adapters | `cli` | CLI interface (Typer) |

### Design documentation

The `docs/design/` directory contains the design rationale and specification documents for
the governance system. These are not loaded by agents at runtime — they inform the design
of the governance files themselves.

---

## Contributing

Please refer to the [contribution guidelines](CONTRIBUTING.md).

---

## Acknowledgments

### Authors & Contributors

**Author**: @eresther

For academic use, please cite using the GitHub "Cite this repository" feature to
generate a citation in various formats.

Alternatively, refer to the [citation metadata](CITATION.cff).

---

## License

This project is licensed under the terms of the [GNU General Public License v3.0](LICENSE).
