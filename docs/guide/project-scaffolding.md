---
tags: []
aliases:
  - Project Scaffolding
index: ""
---

# Project scaffolding

`eutaxis` owns reusable instruction templates. Projects own their generated or edited project-specific instructions.

Use `eutaxis init` inside a project repository to create a starter Codex instruction layout:

```sh
eutaxis init --template codex-project
```

For a project that should synchronize shared instructions across Codex and Claude Code, use:

```sh
eutaxis init --template multi-agent-project
```

The default template creates:

```text
AGENTS.md
eutaxis.yml
docs/instructions/project-overview.md
docs/instructions/repository-layout.md
docs/instructions/tasks/programming.md
```

Every template places `_schema: eutaxis:configuration@2` first in `eutaxis.yml`. The [configuration guide](configuration.md) defines this format identifier.

The scaffold is written to the [root](cli-reference.md#root-and-configuration-file): the folder given with `--root`, or the current folder outside any project that already holds a configuration file. The command refuses to overwrite existing files unless `--force` is supplied.

Template ownership stays in `eutaxis`; project-specific content should be edited and maintained in the project repository after scaffolding.
