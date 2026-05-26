# Instruction assembly API

The instruction assembly API is exposed from `eutaxis.instructions`.

## Public imports

```python
from pathlib import Path

from eutaxis.instructions import InstructionGenerator, load_config

config = load_config(Path("agent-instructions.yaml"))
generator = InstructionGenerator(config)
generator.write_all()
```

## Configuration loading

`load_config(config_path, root=None)` loads a YAML instruction config and returns an `InstructionConfig`.

```python
from pathlib import Path

from eutaxis.instructions import load_config

config = load_config(Path("agent-instructions.yaml"))
```

Pass `root` to override the config root used for relative source and target paths:

```python
config = load_config(
    Path("global-agent-instructions.yaml"),
    root=Path("~/agent-config").expanduser(),
)
```

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
| `ConfigurationError` | The YAML config is missing required fields or has invalid types. |
| `SourceNotFoundError` | A configured source file does not exist. |

The CLI reports these errors and exits with code `1`.
