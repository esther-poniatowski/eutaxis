# eutaxis

[![Maintenance](https://img.shields.io/maintenance/yes/2026)](https://github.com/esther-poniatowski/eutaxis)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.12-blue)](https://www.python.org/)
[![License: GPL](https://img.shields.io/badge/License-GPL--3.0-yellow.svg)](https://opensource.org/licenses/GPL-3.0)

Builds structured agent prompts from reusable fragments.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

## Overview

Eutaxis composes, renders, and checks structured agent prompts. Domain rules
stay in the projects that own them; eutaxis only provides the composition
workflow, reusable templates, and prompt-authoring method.

### Motivation

High-quality agent prompts share recurring structure: role definitions,
evidence standards, report contracts, scope guards, and output formats. Without
composition tooling, authors either duplicate that structure across prompt sets
or keep it in large files that are hard to review, test, and revise.

Eutaxis makes the composed prompt the primary design artifact. Shared
structure can stay single-source through reusable bundles, while each prompt
still keeps explicit control over ordering and local transitions.

### Advantages

- **Prompt families**: prompts are grouped into families that share
  authoring workflows, methodology patterns, output contracts, and testing
  strategies.
- **Shell-first composition**: each prompt owns an explicit top-level shell
  that determines final ordering, bridging text, and prompt-level coherence.
- **Parameterized bundles**: shared methodology structure is single-source;
  domain-specific content is injected through template variables.
- **Profile-based validation**: family profiles distinguish hard assembly
  requirements from advisory guidance, with no over-prescribed schemas.
- **Golden-file review**: composed prompts are rendered into reviewable
  output, enabling diff-based iteration and behavioral testing.

---

## Features

- [ ] **Prompt composer**: assemble prompts from shells, local fragments, and
  parameterized bundles via Jinja2 rendering.
- [ ] **Prompt validator**: enforce family profile requirements (required files,
  required tags, length warnings).
- [ ] **Golden-file output**: render composed prompts for diff-based review.
- [X] **Prompt-writing methodology**: ships `docs/prompt-writing-methods.md`,
  the foundational reference for agent instruction design.
- [ ] **Workspace scaffolder**: initialize prompt-composition structure in a target
  project.

---

## Installation

### Using pip

```bash
pip install git+https://github.com/esther-poniatowski/eutaxis.git
```

### From source

1. Clone the repository:

      ```bash
      git clone https://github.com/esther-poniatowski/eutaxis.git
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
eutaxis generate -c agent-instructions.yaml
```

### Python

```python
import eutaxis

eutaxis.info()
```

---

## Documentation

- [Prompt-Writing Methodology](docs/prompt-writing-methods.md) — foundational
  reference for agent instruction design.
- [Proposal](PROPOSAL.md) — architectural proposal for the prompt composition
  framework.

### Ecosystem

Eutaxis provides composition infrastructure for projects that own domain rules:

- [vitruv](https://github.com/esther-poniatowski/vitruv) — software
  architecture standards and audit prompts.
- [hermeneia](https://github.com/esther-poniatowski/hermeneia) — writing
  quality standards and prose audit prompts.

---

## Contributing

Please refer to the [contribution guidelines](CONTRIBUTING.md).

---

## Acknowledgments

### Authors & Contributors

**Author**: @esther-poniatowski

For academic use, please cite using the GitHub "Cite this repository" feature
to generate a citation in various formats.

Alternatively, refer to the [citation metadata](CITATION.cff).

---

## License

This project is licensed under the terms of the [GNU General Public License v3.0](LICENSE).
