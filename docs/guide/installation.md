---
tags: []
aliases:
  - Installation
index: ""
---

# Installation

## Prerequisites

- Python >= 3.12
- conda (recommended) or pip

## Using pip

The package installs directly from the GitHub repository:

```sh
pip install git+https://github.com/esther-poniatowski/eutaxis.git
```

## From source

1. Clone the repository:

   ```sh
   git clone https://github.com/esther-poniatowski/eutaxis.git
   ```

2. Create a dedicated environment and install:

   ```sh
   cd eutaxis
   conda env create -f environment.yml
   conda activate eutaxis
   pip install -e ".[dev]"
   ```

## Next steps

After installation, read [Concepts](concepts.md) for the mental model behind the configuration, then [Usage: get started](usage.md) for the first-time walkthrough.
