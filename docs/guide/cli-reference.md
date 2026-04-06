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

The generator reads the YAML config, resolves all source paths relative to the
config file's parent directory, and writes one output file per enabled agent.
See [Configuration](configuration.md) for the full schema.

Exit codes:

- `0` -- all agent files generated successfully.
- `1` -- configuration file not found.

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

### `init` (stub)

Scaffold a prompt-composition structure into a target project.

```sh
eutaxis init --target <directory>
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--target` | `-t` | `.` | Target workspace directory. |

**Status:** not yet implemented. Prints a notice and exits with code 0.
