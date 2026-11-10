---
tags: []
aliases:
  - Instruction Assembly API
index: ""
---

# Instruction assembly API

The instruction assembly API is exposed from `eutaxis.instructions`.

## Public imports

```python
from pathlib import Path

from eutaxis.instructions import InstructionGenerator, load_config

config = load_config(Path("eutaxis.yml"))
generator = InstructionGenerator(config)
generator.write_all()
```

## Configuration loading

`load_config(config_path, root=None)` loads a YAML instruction config and returns an `InstructionConfig`. The relative source and target paths of the file resolve against `root`. Without `root`, they resolve against the root implied by the place of the file, returned by `settings_root(config_path)`: the folder that holds `config/` for a file in `config/tools/`, and the folder of the file otherwise.

```python
from pathlib import Path

from eutaxis.instructions import load_config

config = load_config(Path("config/tools/eutaxis.yml"))
```

A settings file kept outside the folder against which its paths resolve takes that folder as `root`:

```python
config = load_config(
    Path("generated/global.yml"),
    root=Path("~/agent-config").expanduser(),
)
```

The command line resolves the root with `resolve_root` and finds the settings file below it with `find_config`, as described in [Root and settings file](cli-reference.md#root-and-settings-file).

## Generation

`InstructionGenerator` renders, writes, and compares instruction outputs.

```python
from eutaxis.instructions import InstructionGenerator

generator = InstructionGenerator(config)

content_by_agent = generator.generate_all()
paths = generator.write_all()
```

Generate or write only one configured output:

```python
content = generator.generate_all(agent_name="codex")
paths = generator.write_all(agent_name="codex")
```

## Stale output checks

`diff_report()` compares generated content to files currently on disk:

```python
for agent, path, differs in generator.diff_report():
    print(agent.name, path, differs)
```

`unified_diff(agent_name)` returns a unified diff for one output:

```python
print(generator.unified_diff("codex"))
```

## Markdown assembly

`MarkdownAssembler` applies source-level transformations:

- YAML frontmatter stripping;
- named section inclusion;
- named section exclusion;
- heading-level offsets.

```python
from pathlib import Path

from eutaxis.instructions import MarkdownAssembler, SourceFile

assembler = MarkdownAssembler()
source = SourceFile(
    path=Path("docs/instructions/style.md"),
    sections=("Hard Rules",),
    heading_offset=1,
)
content = assembler.process(markdown_text, source)
```

## Data models

The main dataclasses are:

| Class | Purpose |
| ----- | ------- |
| `SourceFile` | One Markdown source and its section-processing options. |
| `TargetConfig` | One output path plus optional header and footer. |
| `AgentConfig` | One generated output and its agent-specific sources. |
| `InstructionConfig` | Complete config with root, common sources and agents. |
| `Section` | Parsed Markdown heading block. |

## Errors

All instruction assembly errors inherit from `InstructionError`.

| Error | Raised when |
| ----- | ----------- |
| `ConfigurationError` | The YAML config is missing, is ambiguous, is missing required fields, has invalid types, or declares the retired key `root`. |
| `SourceNotFoundError` | A configured source file does not exist. |
| `BudgetExceededError` | A generated target exceeds its byte budget. |
| `InstructionChainBudgetExceededError` | A cumulative instruction chain exceeds its byte budget. |
| `RejectedLabelError` | A label line violates the label grammar under `strict_rule_labels`. |

Each error carries the exit status of the CLI in its attribute `exit_code`: `2` for `ConfigurationError` and `SourceNotFoundError`, and `1` for the three validation errors.
