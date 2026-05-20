# CLI Reference

## Global Options

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

The generator reads the YAML config, resolves all source paths relative to the
configured root, and writes one output file per enabled agent. See
[Configuration](configuration.md) for the full schema.

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

Exit code `0` means all selected outputs are current. Exit code `1` means at
least one output differs from the generated content.

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

The command copies tracked starter files from the selected template into the
target directory. Existing files are not overwritten unless `--force` is passed.
