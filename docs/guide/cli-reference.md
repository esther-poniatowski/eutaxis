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

A label line that violates the [label grammar](concepts.md#rule-blocks) defines no rule, so the rule index omits that line. Each such line of a declared module is reported on standard error, with its file, its line and the violated part of the grammar. Under the configuration key `strict_rule_labels: true`, a rejected line fails the command before any file is written.

Exit codes:

- `0` -- all agent files generated successfully.
- `1` -- configuration, source loading or generation failed, or a label line is rejected under `strict_rule_labels`.

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

Exit code `0` means all selected outputs are current. Exit code `1` means at least one output differs from the generated content. Rejected label lines are reported in the same form as by `generate`. Under the configuration key `strict_rule_labels: true`, they also fail the check.

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
| `list` | List Skill sources registered in the configuration, with invocation routes and failure-mode tags. |
| `show` | Render and print one Skill artifact for one adapter, without writing to disk. |
| `install` | Install one Skill artifact (by name) or all artifacts (`all`) into the selected adapter and scope. |
| `uninstall` | Remove one installed Skill artifact from the selected adapter and scope. |
| `diff` | Show drift between rendered output and installed artifacts. |

The failure-mode gate ([failure-mode-as-source-field](../adr/failure-mode-as-source-field.md)) applies at render time: the renderer refuses to emit a `model-invoked` artifact from a silent-failure source and a `user-invoked` artifact whose `required-visibility` is `pre-invocation`. There is no `--force` escape for these checks.

A source whose frontmatter declares `disclosure: progressive` compiles to a [split Skill](concepts.md#progressive-disclosure): an index in `SKILL.md` and one file per rule under `rules/`. The commands `show`, `install` and `diff` handle the rule files together with the other files of the artifact.

The compiler rewrites the relative links of each emitted file, as described in [Links between modules](concepts.md#links-between-modules). The commands `show`, `install` and `diff` report on standard error each relative link whose target does not exist, with the source file and the line of the link.

Exit codes of `diff`:

- `0` -- every artifact matches its render.
- `1` -- at least one artifact differs from its render: a file is outdated, edited by hand or missing, or a file of a deleted rule remains on disk.

---

### `rule`

Print one rule of an instruction module, or one part of that rule, without reading the whole module. Each rule spans one [rule block](concepts.md#rule-blocks), and each part is one statement or field of that block.

```sh
eutaxis rule show <label> [--part <key>] [--module <name>] [-c <config-file> | --skills-dir <dir> | --agent <agent>]
eutaxis rule list [--module <name>] [-c <config-file> | --skills-dir <dir> | --agent <agent>]
```

| Subcommand | Use it to |
|------------|-----------|
| `show` | Print one rule, or the parts selected by `--part`, after a location line: heading path, file and line range. |
| `list` | Print the label, the module and the first ✓ line of every rule. A label-shaped line is reported on standard error when its label violates the grammar. |

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--part` | `-p` | whole rule | Key of the part to print, from the part keys listed below. |
| `--module` | `-m` | all modules | Module or Skill that holds the rule. Required when several modules define the label. |
| `--config` | `-c` | none | Configuration whose modules are read: `common_sources`, agent `sources` and `task_modules`. A source entry that selects sections contributes only the rules inside those sections. |
| `--skills-dir` | | none | Directory whose eutaxis-owned Skills are read. |
| `--agent` | `-a` | `claude` | Adapter whose user-scope skill directory is read when neither `--config` nor `--skills-dir` is given. |

The part keys select the statements, the lead or the fields of a rule:

- `valid` and `invalid` select the ✓ and the ✗ statements, and `lead` selects the text before the first statement;
- `why` selects every field whose title opens on "Why", such as `*Why.*` or `*Why the tiers.*`;
- `exception` selects `*Exception.*`, `*Exceptions.*` and `*Exception*:`, and `note` selects `*Note.*` and `*Notes.*`;
- `how-to-apply` selects `*How to apply.*`;
- `test`, `key`, `scope`, `warning` and `relation` each select the field of that name, its plural, and any title opening on that word, such as `*Relation to the neighbouring rules.*`;
- the slug of any other title selects that field, as `precedence-among-the-three-enumeration-rules` selects `*Precedence among the three enumeration rules.*`.

The default source is the deployed Skills, so the query runs from any working directory. Always-on modules compile into the cumulative instruction file, so their rules are absent from the Skills and are read with `--config`.

The query below prints the exception clause of one rule from the authored modules:

```sh
eutaxis rule show warnings-have-a-zero-baseline --part exception -c agent-instructions.yaml
```

```text
verification > Verification > warnings-have-a-zero-baseline [exception] (<root>/instructions/global/verification.md:32-35)

*Exception.* Two constructions keep a non-zero count without failing:
...
```

Exit codes:

- `0` -- the rule, the part or the listing was printed.
- `1` -- the label is unknown or ambiguous, the rule lacks the part, or the source cannot be read. The message lists the close labels, the modules or the parts of the rule.

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
