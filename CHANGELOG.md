# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `task_modules[i].description` falls back to the file's YAML frontmatter when omitted from the config; config-level entries remain optional overrides.
- `eutaxis scan` reports drift between configured instruction files and the files present on disk. The `--register` flag prints a YAML snippet ready to paste into the config. Instruction files with `enabled: false` in their frontmatter are excluded from the unregistered report.

### Changed

- README and `docs/guide/usage.md` carry a "Common tasks" entry-point table listing the everyday `eutaxis` commands. `docs/guide/cli-reference.md` documents the `scan` subcommand.
