---
tags:
  - index
aliases:
  - Eutaxis
index: ""
---

# Eutaxis

Eutaxis assembles agent instruction files from modular Markdown sources. A single YAML configuration drives two compilation surfaces — the cumulative instruction file each agent loads on every turn, and the on-demand Agent Skill artifacts loaded when a skill description matches the active task. The list of currently supported agents is recorded in the [Supported agents](../README.md#supported-agents) table.

## Start here

The user guide is sequenced for a first read in this order:

1. [Installation](guide/installation.md) — prerequisites and source-install instructions.
2. [Concepts](guide/concepts.md) — the mental model behind the configuration (compilation surfaces, source schema, activation regimes). Read this before the Usage guide.
3. [Usage](guide/usage.md) — step-by-step workflows from first setup to ongoing maintenance.
4. [CLI Reference](guide/cli-reference.md) — commands, options, exit codes.

## Supplementary navigation

### User guide

- [Configuration](guide/configuration.md) — YAML schema reference.
- [Project scaffolding](guide/project-scaffolding.md) — starter templates.
- [Instruction assembly API](guide/instructions-api.md) — Python API for embedding generation in another tool.

### Reference

- [API reference](api/index.md) — auto-generated module documentation.
- [Design documentation — methods](internals/_index.md) — internal design notes.

### Architecture

- [Architecture decisions](adr/_index.md) — accepted design decisions, with rationale and discarded alternatives.
- [Open questions](open-questions/_index.md) — design questions the ADR set does not yet resolve.

### Prompt-writing methods

- [Prompt-writing methods](prompt-writing-methods/_index.md) — methodology reference for authoring instruction modules.
