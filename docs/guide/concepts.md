---
tags: []
aliases:
  - Core Concepts
index: ""
---

# Concepts

Eutaxis solves one problem: a set of modular Markdown rule sets must reach several agent target files (Codex `AGENTS.md`, Claude Code `CLAUDE.md`, per-skill directories under `~/.claude/skills/`, `~/.agents/skills/`) without manual duplication. The tool reads one YAML configuration and writes every target. This page introduces the mental model the configuration encodes.

## Two compilation surfaces

The configuration drives two distinct compilation paths, each suited to a different activation regime built into Claude Code and Codex:

| Surface | Target | Activation | Eutaxis command |
| --- | --- | --- | --- |
| **Cumulative instruction file** | `AGENTS.md`, `CLAUDE.md` (project-local or global) | Loaded into the agent's context on every turn. Every line is always present. | `eutaxis generate` |
| **On-demand Skill artifact** | `~/.claude/skills/<name>/`, `~/.agents/skills/<name>/` | Loaded only when the skill description matches the active task (model-invoked) or when the user invokes the skill explicitly (user-invoked). | `eutaxis skills install` |

The cumulative surface carries rules that must hold unconditionally — file authority, environment safety, verification policy. The Skill surface carries task-specific rule sets — prose style, mathematical exposition, git workflow conventions. The same configuration drives both: `common_sources` feeds the cumulative file, `task_modules` feeds the Skill compiler.

## Source modules

A **source module** is a Markdown file containing reusable guidance. Source modules live in any directory the configuration references; a typical layout groups them by audience:

```text
docs/instructions/
  globals/
    file-authority.md
    environment-safety.md
    verification.md
  tasks/
    prose-writing-style.md
    mathematical-exposition.md
    git-workflows.md
```

Module files stay small enough to review independently. A broad file may still be used as a source by selecting named heading sections (see [Source selection](#source-selection) below).

### Source selection

Each source entry in the configuration controls which part of a Markdown file appears in the output:

- include the full file;
- include only named heading sections;
- exclude named heading sections;
- strip YAML frontmatter;
- shift heading levels with `heading_offset`.

Section selection matches heading text exactly and includes the heading plus every nested subsection until the next heading at the same or higher level. Configuration syntax is documented in [Configuration: source entries](configuration.md).

## Configuration shape

The configuration carries four top-level lists, each tied to one role:

```yaml
root: .                    # optional; resolves relative paths
common_sources: [ ... ]    # feeds the cumulative file (always-on)
task_modules:  [ ... ]     # feeds the Skill compiler (on-demand)
agents:        [ ... ]     # one entry per cumulative-file target
```

- **`root`** anchors relative paths. When absent, the configuration file's parent directory is used. The CLI flag `--root` overrides both.
- **`common_sources`** lists Markdown source modules included in every cumulative-file output. Source entries follow the schema above.
- **`task_modules`** lists Markdown source modules eligible for compilation as Skill artifacts. Each entry names the source file and declares enough metadata for the Skill compiler to resolve it.
- **`agents`** lists the cumulative-file targets. Each agent entry declares its output path, optional header and footer, and optional per-agent extra sources.

A minimal configuration that exercises both surfaces:

```yaml
common_sources:
  - path: docs/instructions/globals/file-authority.md
  - path: docs/instructions/globals/verification.md

task_modules:
  - id: prose-writing-style
    title: Prose writing style
    path: docs/instructions/tasks/prose-writing-style.md
    trigger: when drafting or revising documentation, articles, or long-form prose

agents:
  - name: codex
    target:
      path: AGENTS.md
  - name: claude
    target:
      path: .claude/CLAUDE.md
```

Running `eutaxis generate -c agent-instructions.yaml` against this configuration writes the two cumulative files. Running `eutaxis skills install all -c agent-instructions.yaml` compiles the prose-writing-style module to a Skill on every registered adapter, provided the module's frontmatter declares the source schema below.

## Source schema for task_modules

Every Markdown file listed under `task_modules` must declare four frontmatter fields. The compiler refuses to emit a Skill from a file that omits any required field; the failure is loud, not silent.

| Field | Required | Allowed values | Role |
| --- | --- | --- | --- |
| `name` | yes | slug (lowercase, hyphen-separated) | Skill directory name and frontmatter identifier. |
| `description` | yes | one-line string | Description surfaced to the agent's skill picker. Determines model-invocation activation. |
| `invocation` | yes | non-empty list of `user`, `model` | Permitted invocation routes (see [Activation regimes](#activation-regimes) below). |
| `failure-mode` | yes | `silent`, `visible` | Silent-failure classification per the [failure-mode-as-source-field](../adr/failure-mode-as-source-field.md) ADR. |
| `required-visibility` | required when `failure-mode: silent`; forbidden otherwise | `pre-invocation`, `pre-action` | Distinguishes rules that must be visible before the model decides which procedure applies from rules that must be visible before the first irreversible action. |

Example frontmatter for a Skill-eligible source module:

```markdown
---
name: prose-writing-style
description: How to write expository prose — documentation, articles, long-form text.
invocation: [model, user]
failure-mode: visible
---

# Prose writing style

...
```

### Activation regimes

The `invocation` list determines which native activation flags the compiler emits on each adapter:

| `invocation` value | Claude `SKILL.md` frontmatter | Codex `agents/openai.yaml` |
| --- | --- | --- |
| `[user]` | `disable-model-invocation: true` | `policy.allow_implicit_invocation: false` |
| `[user, model]` (or `[model, user]`) | omitted | omitted |

When `model` is absent from `invocation`, the agent cannot pick the skill from its description; explicit user invocation via `/<name>` (Claude) or `$<name>` (Codex) still works. When `model` is present, both routes are available.

### Failure-mode gate

The compiler refuses two placements:

- A source with `failure-mode: silent` cannot ship as a Skill that admits model invocation (`"model"` in `invocation`). The model-judgment activation gate provides no visibility guarantee before the first irreversible action.
- A source with `failure-mode: silent` and `required-visibility: pre-invocation` cannot ship as any Skill. The rule must be visible *before* the agent decides which procedure applies; only the always-on cumulative file provides that guarantee.

Both refusals raise a typed error naming the source path and the violated rule. There is no `--force` escape. The full rationale is recorded in the [failure-mode-as-source-field](../adr/failure-mode-as-source-field.md) ADR; the upstream activation-regime model is in [silent-failure-rules-as-always-on](../adr/silent-failure-rules-as-always-on.md).

## Project-level and global use

The same machinery powers two deployment patterns, distinguished by where `root` points and where the targets sit:

- **Project-level.** The configuration file lives at the project root; relative paths resolve against the project tree; targets are project-local (`AGENTS.md`, `.claude/CLAUDE.md`). Each project owns its own agent instruction files. This is the pattern produced by `eutaxis init`.
- **Global.** The configuration file lives outside any single project (typically under a personal configuration repository); `root` points at that repository; targets are absolute paths (`~/.codex/AGENTS.md`, `~/.claude/CLAUDE.md`). One configuration writes the instruction files every project inherits.

Both patterns share the same `task_modules` mechanism: Skill artifacts always land under `~/.claude/skills/` and `~/.agents/skills/` (or the project-local equivalents when `--scope project` is passed to `eutaxis skills install`).

## Lifecycle

A typical maintenance loop touches three commands:

1. **Edit a source module.** Modify the Markdown content under `docs/instructions/` (or wherever the configuration's `root` points).
2. **Regenerate.** Run `eutaxis generate -c <config>` for cumulative-file edits, or `eutaxis skills install all -c <config>` for `task_modules` edits, or both.
3. **Verify.** Run `eutaxis check -c <config>` and `eutaxis skills diff -c <config>` in CI or locally to detect drift between the rendered output and the on-disk targets.

Generated cumulative files carry a header comment marking them as generated; manual edits are reverted on the next `generate`. Installed Skill directories carry a dual ownership marker (`x-eutaxis-owned` frontmatter key plus `.eutaxis-owned.json` sidecar); manual edits inside a Skill directory are detected as drift and overwritten on the next `skills install`. See the [dual-ownership-marker](../adr/dual-ownership-marker.md) ADR for the marker design.

## Compatibility layer

The public Python API lives under `eutaxis.instructions` (configuration loading, Markdown transformations, generation, exceptions). The older `eutaxis.generate` module remains available as a thin facade for scripts and tests that imported the first implementation. New code calls `eutaxis.instructions` directly.
