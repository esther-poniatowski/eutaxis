# eutaxis

[![Maintenance](https://img.shields.io/maintenance/yes/2026)]()
[![Python](https://img.shields.io/badge/python-%E2%89%A53.12-blue)](https://www.python.org/)
[![License: GPL](https://img.shields.io/badge/License-GPL--3.0-yellow.svg)](https://opensource.org/licenses/GPL-3.0)

Enforces quality standards for code and writing through reusable, domain-specific rules.

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

Eutaxis is a quality validation framework organized around domains. Each domain
ships a self-contained set of style rules, audit prompts, and AI agent templates.
Two domains are bundled by default:

- **`math`** — rules and audits for mathematics and research writing.
- **`software`** — design standards, architecture audits, and AI agent templates
  for software projects.

The Python tooling layer provides a style linter, an instruction-file generator,
and a workspace scaffolder that all operate against the installed domain data.

### Motivation

Quality enforcement for writing and code review tends to be either too generic
(project-agnostic rules miss domain conventions) or too tightly coupled to a
single project (rules cannot be reused). Eutaxis externalizes quality rules into
domain-specific packages that can be imported by any project requiring consistent
validation.

### Advantages

- **Domain-based organization**: rules, audits, and templates live under
  `data/domains/{domain}/` and can be extended or overridden per project.
- **Dual import mechanism**: usable as a Git submodule for rapid iteration, or as
  a pip/conda package for stable deployment.
- **Overridable style linting**: ships default rules per domain, with per-project
  override support.
- **Instruction-file generation**: assembles agent instruction files (CLAUDE.md,
  AGENTS.md, copilot-instructions.md) from domain sources and project-specific
  configuration.

---

## Features

- [X] **Style linter**: Markdown linter with domain-specific overridable rules.
- [ ] **Instruction generator**: Assemble agent instruction files from domain sources.
- [ ] **Registry validator**: Validate YAML registries against JSON schemas.
- [ ] **Workspace scaffolder**: Initialize domain structure in a target workspace.
- [ ] **Terminology linter**: Check prose against a terminology registry.

---

## Installation

### As a Git submodule (recommended during development)

```bash
git submodule add https://github.com/eresther/eutaxis.git vendor/eutaxis
git submodule update --init --recursive
```

Consuming projects reference domain files directly from `vendor/eutaxis/src/eutaxis/data/`.

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
eutaxis lint --domain math path/to/notes/
eutaxis lint --domain software --config my-overrides.yaml path/to/file.md
```

### Python

```python
import eutaxis

eutaxis.info()
domain = eutaxis.domain_path("math")
```

---

## Usage

### Command Line Interface (CLI)

```sh
# Display version and diagnostics
eutaxis info

# Lint Markdown files against domain rules (with optional overrides)
eutaxis lint --domain <domain> [--config overrides.yaml] <paths...>

# Generate agent instruction files from domain sources (planned)
eutaxis generate --domain <domain> --config agent-instructions.yaml

# Validate registry files against schemas (planned)
eutaxis validate registry/

# Scaffold domain structure into a workspace (planned)
eutaxis init --domain <domain> --target /path/to/workspace
```

### Programmatic Usage

```python
from eutaxis.lint import lint_file, load_config

# Lint with default domain rules
issues = lint_file(Path("my-note.md"), domain="math")

# Lint with project-specific overrides
config = load_config(Path("my-overrides.yaml"))
issues = lint_file(Path("my-note.md"), config=config)
```

---

## Architecture

Eutaxis is a data-heavy package: the primary payload is domain specifications
(Markdown, YAML, JSON), with a thin Python tooling layer for validation, linting,
and assembly.

| Layer | Path | Responsibility |
| --- | --- | --- |
| Data | `data/domains/math/` | Math style rules and audit prompts |
| Data | `data/domains/software/` | Design standards, architecture audits, AI templates |
| Application | `generate` | Instruction-file assembly from domain sources |
| Application | `validate` | Registry validation against JSON schemas |
| Application | `lint` | Style linting with overridable rule configuration |
| Application | `scaffold` | Workspace initialization and domain scaffolding |
| Adapters | `cli` | CLI interface (Typer) |

### Design documentation

The `docs/design/` directory contains design rationale for the validation tooling.
Research knowledge structure and epistemic methods (note types, contracts,
registries, reasoning principles) are documented in
[gnomon](https://github.com/esther-poniatowski/gnomon).

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
