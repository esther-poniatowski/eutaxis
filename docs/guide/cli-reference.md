---
tags: []
aliases:
  - CLI Reference
index: ""
---

# CLI reference

## Global options

| Flag | Short | Effect |
|------|-------|--------|
| `--version` | `-v` | Print the package version and exit. |
| `--help` | | Print top-level help and exit. |

## Commands

### `info`

Print version and platform diagnostics.

```sh
eutaxis info
```

Takes no arguments or options.

---

### `generate`

Assemble agent instruction files from modular prompt sources.

```sh
eutaxis generate -c <config-file>
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--config` | `-c` | `agent-instructions.yaml` | Path to the generation configuration file. |
| `--root` | `-r` | config parent or config `root` | Root used to resolve relative source and target paths. |
| `--agent` | `-a` | all enabled agents | Generate only one configured agent output. |
| `--dry-run` | `-n` | `false` | Show output targets without writing files. |

The generator reads the YAML config, resolves all source paths relative to the configured root, and writes one output file per enabled agent. See [Configuration](configuration.md) for the full schema.

Exit codes:

- `0` -- all agent files generated successfully.
- `1` -- configuration, source loading or generation failed.

---

### `check`

Check whether generated instruction files match the current source modules.

```sh
eutaxis check -c <config-file>
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--config` | `-c` | `agent-instructions.yaml` | Path to the generation configuration file. |
| `--root` | `-r` | config parent or config `root` | Root used to resolve relative source and target paths. |
| `--agent` | `-a` | all enabled agents | Check only one configured agent output. |
| `--diff` | | `false` | Print unified diffs for stale outputs. |

Exit code `0` means all selected outputs are current. Exit code `1` means at least one output differs from the generated content.

---

### `list`

List configured outputs, source files, and resolved targets.

```sh
eutaxis list -c <config-file>
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--config` | `-c` | `agent-instructions.yaml` | Path to the generation configuration file. |
| `--root` | `-r` | config parent or config `root` | Root used to resolve relative source and target paths. |

---

### `scan`

Compare instruction files on disk against the files the config registers.

```sh
eutaxis scan -c <config-file>
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--config` | `-c` | `agent-instructions.yaml` | Path to the generation configuration file. |
| `--root` | `-r` | parent directories of registered files | Override the directory walked for instruction files. |
| `--register` | | `false` | Print a YAML snippet registering any unregistered files. |

The command emits three groups: registered-and-present, unregistered-and-present, and registered-but-missing. Files whose frontmatter sets `enabled: false` are excluded from the unregistered report. `--register` prints a paste-ready snippet to stdout; the on-disk config is never rewritten.

Exit codes:

- `0` -- no drift: every registered file is present and every present file is registered (or opted out).
- `1` -- drift detected, or a discovered file has malformed frontmatter.

---

### `skills`

Compile config-registered instruction files to Agent Skill artifacts. The per-rule-set analogue of `commands`, which discovers sources from layered directories. Discovery is config-driven: every Markdown file listed under `task_modules` is a Skill candidate, provided its frontmatter satisfies the source schema (`name`, `description`, `invocation`, `failure-mode`, and `required-visibility` when silent).

```sh
eutaxis skills list -c <config-file>
eutaxis skills show <name> -c <config-file> [--agent claude|codex]
eutaxis skills install <name|all> -c <config-file> [--agent <agent>] [--scope user|project]
eutaxis skills uninstall <name> -c <config-file> [--agent <agent>] [--scope user|project]
eutaxis skills diff [<name>] -c <config-file>
```

| Subcommand | Use it to |
|------------|-----------|
| `list` | List Skill sources registered in the configuration, with regime and failure-mode tags. |
| `show` | Render and print one Skill artifact for one adapter, without writing to disk. |
| `install` | Install one Skill artifact (by name) or all artifacts (`all`) into the selected adapter and scope. |
| `uninstall` | Remove one installed Skill artifact from the selected adapter and scope. |
| `diff` | Show drift between rendered output and installed artifacts. |

The failure-mode gate ([failure-mode-as-source-field](../adr/failure-mode-as-source-field.md)) applies at render time: the renderer refuses to emit a `model-invoked` artifact from a silent-failure source and a `user-invoked` artifact whose `required-visibility` is `pre-invocation`. There is no `--force` escape for these checks.

---

### `validate` (stub)

Validate prompt family layouts and configuration files.

```sh
eutaxis validate <paths...>
```

| Argument | Description |
|----------|-------------|
| `paths` | One or more files or directories to validate. |

**Status:** not yet implemented. Prints a notice and exits with code 0.

---

### `init`

Scaffold a prompt-composition structure into a target project.

```sh
eutaxis init --template codex-project --target <directory>
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--target` | `-t` | `.` | Target workspace directory. |
| `--template` | | `codex-project` | Template directory under `eutaxis/data/templates`. |
| `--force` | | `false` | Overwrite existing scaffold files. |

The command copies tracked starter files from the selected template into the target directory. Existing files are not overwritten unless `--force` is passed.
