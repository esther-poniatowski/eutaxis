# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `task_modules[i].description` falls back to the file's YAML frontmatter when omitted from the config; config-level entries remain optional overrides.
- `eutaxis scan` reports drift between configured instruction files and the files present on disk. The `--register` flag prints a YAML snippet ready to paste into the config. Instruction files with `enabled: false` in their frontmatter are excluded from the unregistered report.
- `failure-mode` and `required-visibility` source fields per the [failure-mode-as-source-field](docs/adr/failure-mode-as-source-field.md) ADR. The renderer refuses to emit a skill that admits model invocation from a silent-failure source, and any skill from a silent-failure source whose `required-visibility` is `pre-invocation`. The gate is unconditional (no `--force` escape).
- `invocation` source field (list of permitted routes: `user`, `model`). Replaces the binary-string `regime` field considered in earlier drafts. Claude emits `disable-model-invocation: true` and Codex emits `policy.allow_implicit_invocation: false` only when `"model"` is absent from `invocation`.
- `eutaxis skills` CLI sub-app (list / show / install / uninstall / diff) compiles instruction files registered in the configuration to Agent Skill artifacts. Discovery is config-driven, as the per-rule-set analogue of `eutaxis commands` (which discovers from layered directories).
- `task_modules_router_enabled` config field (default `true`) suppresses the task-modules pointer section in the cumulative AGENTS.md / CLAUDE.md when set to `false`, while keeping the `task_modules` list available for `eutaxis skills` discovery. Set to `false` when the task modules are compiled to native Agent Skills via `eutaxis skills install` and the pointer section is redundant.
- Public API additions: `FailureModeError`, `check_failure_mode`, `load_from_instruction_config`.
- Configuration-file lookup: without `--config`, every command that reads the configuration file (`generate`, `check`, `list`, `scan`, `rule`, and the `skills` subcommands) reads `config/tools/eutaxis.yml` or `eutaxis.yml` below the root. When both exist, the command stops with an error that names both. Public API addition: `find_config`.
- Root resolution: every command resolves its root from `--root`, then from the environment variable `EUTAXIS_ROOT`, then from the nearest folder above the current one that holds the configuration file, then from the current folder. A command therefore runs from any subfolder of a project. Public API additions: `resolve_root`, `settings_root`, `ROOT_ENV_VAR`.
- `--target-project` on the `skills` subcommands (except `list`) names the project that receives project-scope artifacts and fills `{{ project_root }}`. It defaults to the root, and it lets one configuration file install project-scope Skills into another project.
- `--root` on `eutaxis rule` selects the authored modules of the configuration file found below that root.
- `--dir` on `eutaxis scan` names the folder walked for instruction files.

### Changed

- **Breaking.** The configuration file declares its format in the key `_schema`, written first: `_schema: eutaxis:configuration@1`. Eutaxis compares the whole value with this identifier, and a configuration file without the key or with another value is a configuration error (status `2`) whose message names the value to write. Every configuration file gains the line `_schema: eutaxis:configuration@1` as its first key. The scaffold templates write the key, and the public API exports the identifier as `CONFIG_SCHEMA`.
- README and `docs/guide/usage.md` carry a "Common tasks" entry-point table listing the everyday `eutaxis` commands. `docs/guide/cli-reference.md` documents the `scan` subcommand.
- `clean-memory` built-in source migrated to the new schema: `invocation: [user]`, `failure-mode: silent`, `required-visibility: pre-action` (explicit user invocation loads the skill body before the action runs).
- The project folder of a command is named by the reserved option `--root` (`-r`) on every command: `commands` and `skills` subcommands and `ops clean-memory` (formerly `--project`), and `init` (formerly `--target` / `-t`). The `clean-memory` built-in source passes `--root`.
- `--config` is optional on the `skills` subcommands, which use the configuration-file lookup when it is absent.
- The configuration file is renamed `eutaxis.yml`, read from `config/tools/eutaxis.yml` or `eutaxis.yml`. A project renames its `agent-instructions.yaml` to `eutaxis.yml` and moves it to one of these two places, or passes its path with `--config`. `eutaxis init` scaffolds `eutaxis.yml`, and the template `global-agents/agent-instructions.yaml` becomes `global-agents/eutaxis.yml`.
- The paths written in the configuration file resolve against the root of the command, never against the folder of the file. The key `root` is retired: a configuration file that declares it fails with a configuration error. A project drops the key; a configuration file kept outside the folder of its sources runs from that folder or names it with `--root`; a cross-project install of project-scope Skills passes `--target-project`.
- Exit statuses follow the command-line conventions: `0` on success, `1` when a check or a validation finds a problem, `2` on a usage or configuration error. Budget overruns of `generate` exit with `1` (formerly `2`); configuration errors, missing sources, unknown names, corrupted state files and rule-query errors exit with `2` (formerly `1`); the failure-mode gate exits with `1` (formerly `3`). The errors of the `commands` and `skills` subcommands print a message in place of a traceback.
- `ops clean-memory` asks for a confirmation on a terminal and lists the files first; `--yes` answers the confirmation, and without a terminal and without `--yes` the command stops with status `2` (formerly status `1` on a terminal too). A declined confirmation deletes nothing and exits with status `1` (formerly `0`).
- The `commands` subcommands read the project layer of the resolved root by default (formerly no project layer without `--root`).
- `scan_instructions(config, root=...)` names its walk folder `directory`.
- `init` stops with status `2` (formerly `1`) when an existing file requires `--force`.

### Removed

- The former names of `--root`: `--project` (on `commands`, `skills` and `ops clean-memory`) and `--target` / `-t` (on `init`) are rejected as unknown options.
- The short form `-n` of `generate --dry-run`; the conventions reserve no short form for `--dry-run`.
- The configuration-file name `agent-instructions.yaml` and the settings key `root`.
