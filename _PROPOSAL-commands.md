# Eutaxis — Proposal: Cross-Agent Commands Subsystem

**Status:** Draft for review
**Date:** 2026-05-21
**Scope:** A general facility for declaring user-invocable commands once and compiling them into the native slash-command / prompt surfaces of each agent, with `clean-memory` as the first built-in command.
**Relation to other work:** Specializes [_PROPOSAL-cross-agent-compiler.md] for the slash-command surface. Inherits P1 (one-way compilation), P3 (activation regime as classification axis), P5 (native precedence), P7 (golden-file review).

---

## 1. Motivation

The immediate driver is `TODO.md:11` — "Implement a functionality to clean memory in both agents." A one-off implementation that hard-codes `clean-memory` into the CLI and writes two slash-command files would solve the symptom and leave the cause: every future user-invocable command (e.g. `examine-memory`, `prune-archive`, `regen-instructions`) would repeat the same scaffolding and force the author to know the divergent slash-command conventions of Claude Code and Codex.

The right unit of work is therefore the surface itself: a *commands* subsystem that lets an author declare a command once and have Eutaxis compile it into both agents' native forms, with built-in commands shipped by Eutaxis and user commands added without touching `.claude/commands/` or `~/.codex/prompts/` directly.

---

## 2. Activation regime — what "command" means here

A *command* in this proposal is a content unit with the following activation regime:

- **User-invoked**, by typing `/<name>` (or the agent's equivalent) inside an agent session.
- **Session-local effect**: the body is injected as a user-turn prompt; the agent then executes it.
- **Optionally backed by a shell operation**: the body may instruct the agent to run a specific Eutaxis CLI subcommand that performs the real work (e.g. `eutaxis clean-memory --agent claude --yes`). The agent is the trigger; Eutaxis (or the user's shell) is the doer.

This regime maps natively to: Claude Code `.claude/commands/<name>.md` (project) or `~/.claude/commands/<name>.md` (user); Codex `.codex/prompts/<name>.md` (project) or `~/.codex/prompts/<name>.md` (user). Both agents accept a Markdown file whose body is fed to the model on invocation. Eutaxis adapts the same source to both.

Commands are distinct from existing Eutaxis artifacts:
- *Instructions* (`AGENTS.md` / `CLAUDE.md`) are always-active context.
- *Skills* are model-invoked.
- *Commands* are user-invoked.

The three regimes are P3-orthogonal and warrant separate subsystems.

---

## 3. Source model

A command is one Markdown file with YAML frontmatter:

```markdown
---
name: clean-memory
description: Delete this agent's memory files for the current project.
agents: [claude, codex]          # subset of supported agents
scope_default: user              # user | project
action:                          # optional shell-backed action
  shell: "eutaxis clean-memory --agent {{ agent }} --yes"
---

# Clean memory

Run the following to wipe my memory files for this project, then confirm
the directory is empty:

```bash
{{ action.shell }}
```

After it completes, summarize what was deleted.
```

- `name` — slug used for the target filename and the invocation.
- `description` — surfaced by `eutaxis commands list` and (optionally) by the agent's command picker.
- `agents` — explicit allow-list. A command may be Claude-only, Codex-only, or both.
- `scope_default` — where the command installs by default (`user` global vs `project` local). Overridable per install.
- `action.shell` — optional. Templated so the same source can render an agent-specific call. Variables: `agent`, `project_root`, `home`.
- **Body** — Markdown shown to the agent on invocation. The body may reference `{{ action.shell }}` and other declared variables; rendering substitutes them per target agent.

The frontmatter / body convention is identical to existing Eutaxis source files, preserving P7 (golden-file review).

---

## 4. Layout

```
src/eutaxis/
├── commands/                       # Python package
│   ├── __init__.py
│   ├── models.py                   # CommandSource, CommandTarget
│   ├── loader.py                   # discovers + parses .md sources
│   ├── compiler.py                 # source → per-agent rendered files
│   ├── installer.py                # writes/removes rendered files in native dirs
│   └── operations/                 # shell-side doers
│       ├── __init__.py
│       └── memory.py               # clean_claude_memory, clean_codex_memory
└── data/
    └── commands/                   # built-in command sources (Markdown)
        └── clean-memory.md
```

Discovery order (later overrides earlier; same precedence as instruction sources):

1. Built-in: `src/eutaxis/data/commands/*.md`
2. User: `~/.eutaxis/commands/*.md`
3. Project: `<project>/.eutaxis/commands/*.md`

A YAML config `agent-commands.yaml` is **not** introduced. Each Markdown source is self-describing via its frontmatter. This matches P3 (declared regime) and avoids the kind of separate manifest that the cross-agent-compiler proposal already noted as redundant when the source can describe itself.

---

## 5. CLI surface

```
eutaxis commands list                          # show all known commands and their targets
eutaxis commands show <name>                   # print the source + per-agent rendered output
eutaxis commands install <name> [--scope user|project] [--agent claude|codex|all] [--force]
eutaxis commands uninstall <name> [--scope user|project] [--agent claude|codex|all]
eutaxis commands diff [<name>]                 # show drift between source and installed files
```

The operation-backing CLI subcommands live alongside, not under, the `commands` namespace, because they are independently invocable from a shell:

```
eutaxis clean-memory --agent {claude|codex|all} [--all] [--project PATH] [--backup] [--dry-run] [--yes]
```

`eutaxis clean-memory` defaults to the current working directory's encoded Claude project; `--all` wipes every project under `~/.claude/projects/*/memory`. Backup is opt-in via `--backup`.

`commands install` is not run automatically. Installation is an explicit, reviewable user action (consistent with P7 and with the existing `generate` / `check` discipline).

---

## 6. The `clean-memory` built-in

Ships as `src/eutaxis/data/commands/clean-memory.md`. Body instructs the agent to:
1. Run `eutaxis clean-memory --agent <self> --yes` (or with `--all` if the user requested it).
2. Report which paths were removed.

Targets:
- Claude Code: deletes `~/.claude/projects/<encoded-project>/memory/` contents (current project by default).
- Codex: deletes contents of `~/.codex/memories/`.

Encoding rule for Claude project path: replace `/` with `-`, leading `/` becomes a leading `-`, matching the observed directory structure (`~/.claude/projects/-Users-eresther-Documents-work-projects-eutaxis/`).

Safety:
- `--yes` required for non-interactive deletion (no implicit destructive default).
- `--backup` writes to a sibling `memory.bak.YYYYMMDD-HHMMSS/` directory before deletion.
- `--dry-run` lists what would be removed without touching the filesystem.

---

## 7. User extensibility

A user adds a new command by dropping `examine-memory.md` into `~/.eutaxis/commands/` (or `<project>/.eutaxis/commands/`) with the same frontmatter shape. `eutaxis commands list` will see it. `eutaxis commands install examine-memory` will deploy it to both agents. The user never edits `.claude/commands/` or `~/.codex/prompts/` directly.

For commands that need a shell-side doer (like `clean-memory`), the user can either:
- Reference an arbitrary shell command in `action.shell` (e.g. `find ~/.claude -name "*.bak" -delete`), or
- Reference an Eutaxis CLI subcommand once one exists.

Built-in operations (`memory.py` and its eventual siblings) are first-party; user commands that need shell work can call arbitrary shell. This matches the cross-agent-compiler proposal's separation between instruction content and capability configuration (P4).

---

## 8. What this proposal defers

- A schema for *non-shell* command actions (HTTP, Python entry points). The current `action.shell` field is sufficient for the immediate use cases and trivially generalizable later.
- A registry of "approved" user commands; commands are flat-file discoverable.
- Interaction with `eutaxis generate` / `check`. Commands are managed via their own `commands` namespace because their lifecycle (install on demand, uninstall on demand) differs from the always-regenerated instruction files.
- `examine-memory` and any other future built-in commands; they will be added as separate Markdown sources once needed.

---

## 9. Implementation order

1. `src/eutaxis/commands/operations/memory.py` and `eutaxis clean-memory` CLI subcommand (the doer). Tests against a temporary fake `HOME`.
2. `src/eutaxis/commands/{models,loader,compiler,installer}.py` and `eutaxis commands {list,show,install,uninstall,diff}`.
3. Built-in `src/eutaxis/data/commands/clean-memory.md`.
4. Mark `TODO.md:11` done and add an entry under "Next steps" for `commands` extension points.

Each step is independently reviewable and leaves the repo in a usable state.

---

## 10. Open questions for review

- **Q1.** Confirm the per-project Claude scope default (`--project .` ⇒ encoded CWD; `--all` wipes everything). The answer "current project only by default" was given; this proposal codifies it.
- **Q2.** Confirm `~/.eutaxis/commands/` as the user-extension location (vs `~/.config/eutaxis/commands/`).
- **Q3.** Confirm that the slash command body invoking `eutaxis clean-memory --yes` (i.e. the agent runs the shell command on the user's behalf) is acceptable, vs. requiring the user to run it manually from a terminal after the slash command prints the line.
- **Q4.** Confirm the proposal should land in three commits (operation, subsystem, built-in) rather than one.
