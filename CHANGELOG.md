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

### Changed

- README and `docs/guide/usage.md` carry a "Common tasks" entry-point table listing the everyday `eutaxis` commands. `docs/guide/cli-reference.md` documents the `scan` subcommand.
- `clean-memory` built-in source migrated to the new schema: `invocation: [user]`, `failure-mode: silent`, `required-visibility: pre-action` (explicit user invocation loads the skill body before the action runs).
