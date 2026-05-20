# Project Scaffolding

`eutaxis` owns reusable instruction templates. Projects own their generated or
edited project-specific instructions.

Use `eutaxis init` inside a project repository to create a starter Codex
instruction layout:

```sh
eutaxis init --template codex-project --target .
```

The default template creates:

```text
AGENTS.md
agent-instructions.yaml
docs/instructions/project-overview.md
docs/instructions/repository-layout.md
docs/instructions/tasks/programming.md
```

The command refuses to overwrite existing files unless `--force` is supplied.

Template ownership stays in `eutaxis`; project-specific content should be edited
and maintained in the project repository after scaffolding.
