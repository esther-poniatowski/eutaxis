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

## Root and configuration file

Every command that works on a project resolves one root folder. The configuration file is looked up below the root, and the relative paths written in the configuration file resolve against the root. The root is the first answer in this order:

1. the root option `--root` (`-r`);
2. the environment variable `EUTAXIS_ROOT`, when it is set and not empty;
3. the nearest folder, from the current folder upward, that holds `config/tools/eutaxis.yml` or `eutaxis.yml`;
4. the current folder.

The ancestor search of step 3 lets a command run from any subfolder of a project. The environment variable serves editors and continuous integration without a change of command.

The configuration file is named `eutaxis.yml`. Without the configuration option `--config` (`-c`), a command reads `config/tools/eutaxis.yml` or `eutaxis.yml` below the root. The command stops with an error that names both files when both exist, and with an error that names both places when neither exists: Eutaxis declares every source and every output in the configuration file, so it has no built-in defaults.

A path given on the command line, including the value of `--config`, is relative to the current folder. A path written in the configuration file is relative to the root, so the file moves between the root and `config/tools/` without an edit. A configuration file that declares the retired key `root` is a configuration error. A configuration file whose key `_schema` is absent or unsupported is a configuration error too, and the message names the current value; see [Configuration: format identifier](configuration.md#format-identifier).

## Exit statuses

Every command exits with one of three statuses:

- `0` -- the command succeeded, and its check, if any, found no problem;
- `1` -- a check or a validation found a problem: an outdated output, a drifted artifact, an exceeded budget, a rejected label under `strict_rule_labels`, or a source that the [failure-mode gate](../adr/failure-mode-as-source-field.md) rejects;
- `2` -- a usage or configuration error prevented the command from running as asked: an unknown option or name, an invalid or missing configuration file, a configuration file without the identifier `eutaxis:configuration@2`, a declared source that is missing or malformed, a corrupted state file, a file that only `--force` may replace, or a missing confirmation.

## Files and confirmations

A command overwrites the files that it derives, such as a generated instruction file or an Eutaxis-owned Skill directory. A command replaces or deletes a file that it cannot regenerate, such as an edited scaffold file or a Skill directory without an Eutaxis ownership marker, only under the force option `--force`.

A command that deletes files outside its outputs, such as `ops clean-memory`, lists the files and asks for a confirmation on a terminal. The confirmation option `--yes` answers the confirmation in advance. Without a terminal and without `--yes`, the command stops with status `2`.

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
eutaxis generate [-c <config-file>] [--root <folder>]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--config` | `-c` | [lookup below the root](#root-and-configuration-file) | Configuration file. |
| `--root` | `-r` | [resolved root](#root-and-configuration-file) | Folder below which the configuration file is looked up and against which its paths resolve. |
| `--agent` | `-a` | all enabled agents | Generate only one configured agent output. |
| `--dry-run` | | `false` | Show output targets without writing files. |
| `--plan` | | `false` | With `--dry-run`, report structured selections, cumulative-file drift and budgets. |
| `--ignore-budget` | | `false` | Skip generated-target and cumulative-chain budget failures. |

The generator reads the configuration file, resolves all source paths relative to the root, and writes one output file per enabled agent. See [Configuration](configuration.md) for the full schema.

The command `eutaxis generate --dry-run --plan` reports the planned state of each target. For a changed target, it reports added and removed line counts without printing the complete generated file. The report also gives every generated-target and cumulative-chain byte budget. For each declaration source used by a selected output, it first reports the module, composition manifest, artifact mechanism, scope, target, candidate digest and ordered final-effective record identifiers. The same candidate bytes produce the target plan. The last line is `[COMMAND  ] complete`; a failed plan writes `[COMMAND  ] failed` to standard error and does not report a certified selection for the failed resolution.

A label line that violates the [label grammar](concepts.md#rule-blocks) defines no rule, so the rule index omits that line. Each such line of a declared module is reported on standard error, with its file, its line and the violated part of the grammar. Under the configuration key `strict_rule_labels: true`, a rejected line fails the command before any file is written.

Exit statuses:

- `0` -- all agent files were generated, or, under `--dry-run`, would be generated.
- `1` -- a generated target or cumulative instruction chain exceeds its budget, a label line is rejected under `strict_rule_labels`, or a configured declaration corpus or semantic resolution is invalid.
- `2` -- the configuration file, context or a declared source cannot be read or used.

---

### `check`

Check whether generated instruction files match the current source modules.

```sh
eutaxis check [-c <config-file>] [--root <folder>]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--config` | `-c` | [lookup below the root](#root-and-configuration-file) | Configuration file. |
| `--root` | `-r` | [resolved root](#root-and-configuration-file) | Folder below which the configuration file is looked up and against which its paths resolve. |
| `--agent` | `-a` | all enabled agents | Check only one configured agent output. |
| `--diff` | | `false` | Print unified diffs for stale outputs. |
| `--ignore-budget` | | `false` | Report budget overruns without making them fail the check. |

For each declaration source used by a selected output, the command reports the same candidate digest and ordered final-effective records as `generate --dry-run --plan`. The `--agent` filter restricts both output rows and declaration sources. The last line records command completion independently of the check verdict: stale or over-budget outputs still end with `[COMMAND  ] complete` and exit with status `1`, because the comparison completed. A resolution or operational failure writes `[COMMAND  ] failed` and emits no certified selection for the failed resolution.

Exit status `0` means all selected outputs are current and within budget. Without an agent filter, the selected outputs include the standalone rule index. Exit status `1` means that an output differs from its generated content, exceeds a configured budget, fails strict label validation, or has an invalid configured declaration resolution. Status `2` means configuration, context, source access or another operation prevented the check from completing. The command reports rejected label lines in the same form as `generate`.

---

### `list`

List configured outputs, source files, and resolved targets.

```sh
eutaxis list [-c <config-file>] [--root <folder>]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--config` | `-c` | [lookup below the root](#root-and-configuration-file) | Configuration file. |
| `--root` | `-r` | [resolved root](#root-and-configuration-file) | Folder below which the configuration file is looked up and against which its paths resolve. |

---

### `scan`

Compare instruction files on disk against the files the config registers.

```sh
eutaxis scan [-c <config-file>] [--root <folder>] [--dir <folder>]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--config` | `-c` | [lookup below the root](#root-and-configuration-file) | Configuration file. |
| `--root` | `-r` | [resolved root](#root-and-configuration-file) | Folder below which the configuration file is looked up and against which its paths resolve. |
| `--dir` | | folders of the registered files | Folder walked for instruction files. |
| `--register` | | `false` | Print a YAML snippet registering any unregistered files. |

The command emits three groups: registered-and-present, unregistered-and-present, and registered-but-missing. Files whose frontmatter sets `enabled: false` are excluded from the unregistered report. `--register` prints a paste-ready snippet to stdout; the on-disk config is never rewritten.

Exit statuses:

- `0` -- no drift: every registered file is present and every present file is registered (or opted out).
- `1` -- drift detected, or a discovered file has malformed frontmatter.

---

### `skills`

The configuration registers instruction files. The `skills` command compiles them into Agent Skill artifacts. ^skills-command

Markdown files under `task_modules` are candidate sources. Their frontmatter must satisfy the source schema. Sources with a silent failure mode must also declare `required-visibility`.

```sh
eutaxis skills list [-c <config-file>] [--root <folder>]
eutaxis skills show <name> [-c <config-file>] [--root <folder>] [--target-project <folder>] [--agent claude|codex]
eutaxis skills install <name|all> [-c <config-file>] [--root <folder>] [--target-project <folder>] [--agent <agent>] [--scope user|project]
eutaxis skills uninstall <name> [-c <config-file>] [--root <folder>] [--target-project <folder>] [--agent <agent>] [--scope user|project]
eutaxis skills diff [<name>] [-c <config-file>] [--root <folder>] [--target-project <folder>]
eutaxis skills sync [-c <config-file>] [--root <folder>] [--target-project <folder>] [--agent <agent>] [--scope user|project] [--apply]
eutaxis skills budget [-c <config-file>] [--root <folder>] [--target-project <folder>] [--agent claude|codex]
eutaxis skills loading-unit list [-c <config-file>] [--root <folder>] [--target-project <folder>] [--agent claude|codex]
eutaxis skills loading-unit show <name> [-c <config-file>] [--root <folder>] [--target-project <folder>] [--agent claude|codex]
```

Two folders govern a `skills` subcommand. The [root](#root-and-configuration-file) holds the configuration file and the Skill sources, whose paths resolve against it. The target project receives the project-scope artifacts, and its path is the value substituted for `{{ project_root }}`. The target project is the root, unless the target-project option `--target-project` names another folder. One configuration file can therefore install project-scope Skills into several projects.

| Subcommand | Use it to |
|------------|-----------|
| `list` | List Skill sources registered in the configuration, with invocation routes and failure-mode tags. |
| `show` | Render and print one Skill artifact for one adapter, without writing to disk. |
| `install` | Install one Skill artifact (by name) or all artifacts (`all`) into the selected adapter and scope. |
| `uninstall` | Remove one installed Skill artifact from the selected adapter and scope. |
| `diff` | Show drift between rendered output and installed artifacts. |
| `sync` | Preview or apply the complete configured Skill set and remove retired artifacts recorded for this configuration. |
| `budget` | Measure every rendered entrypoint and declared loading unit against its configured byte limit. |
| `loading-unit list` | List each loading unit with its measured size and publication owner. |
| `loading-unit show` | Report one loading unit's exact files, generated manifests and closure digest. |

The failure-mode gate ([failure-mode-as-source-field](../adr/failure-mode-as-source-field.md)) applies at render time: the renderer refuses to emit a `model-invoked` artifact from a silent-failure source and a `user-invoked` artifact whose `required-visibility` is `pre-invocation`. There is no `--force` escape for these checks.

A source whose frontmatter declares `disclosure: progressive` compiles to a [split Skill](concepts.md#progressive-disclosure): an index in `SKILL.md` and one file per rule under `rules/`. The commands `show`, `install` and `diff` handle the rule files together with the other files of the artifact.

The `publish_to` field generates support files inside the owner Skill. The owner entrypoint links the published route manifests. Then, each route manifest links its ordered batch manifests. The same manifest links the deduplicated file closure. The closure digest covers the selected content files after Eutaxis removes generated ownership-marker values. A separate owner-artifact hash covers the generated index and manifests.

The compiler rewrites the relative links of each emitted file, as described in [Links between modules](concepts.md#links-between-modules). The commands `show`, `install` and `diff` report on standard error each relative link whose target does not exist, with the source file and the line of the link.

The `sync` command previews changes unless the caller passes `--apply`. During preview, the command renders every configured artifact. The preview rejects populated targets that lack an Eutaxis ownership marker.

With `--apply`, the command:

- installs every configured Skill first;
- protects every name recorded by another configuration;
- removes a marked artifact only when this configuration's preceding record contained its name;
- records the resulting set for the configuration, adapter, and deployment target after all writes and removals succeed;
- leaves every unmarked directory unchanged.

The first successful sync writes the configuration record. For project scope, Eutaxis records the resolved target project. Therefore, one configuration can manage each project independently. The configuration record does not include artifacts installed by other configurations. A corrupted install registry or sync manifest blocks the plan before any write. The Skill directories, install registry and sync manifest form one failure-atomic set. If any write fails, Eutaxis restores every directory. Eutaxis also restores the two state files. Correct the cause and run the same command again.

Exit statuses of `diff`:

- `0` -- every artifact matches its render.
- `1` -- at least one artifact differs from its render: a file is outdated, edited by hand or missing, or a file of a deleted rule remains on disk.

Exit statuses of `budget` and `loading-unit`:

- `0` -- every entrypoint and loading unit exists and fits within its limit.
- `1` -- a limit is exceeded.
- `2` -- a loading unit names an unknown module or rule, or a source cannot be rendered.

---

### `rule`
^rule-command

Print one rule of an instruction module, or one part of that rule, without reading the whole module. Each rule spans one [rule block](concepts.md#rule-blocks), and each part is one statement or field of that block.

```sh
eutaxis rule show <label> [--part <key>] [--module <name>] [-c <config-file>] [--root <folder>]
eutaxis rule show <label> [--part <key>] [--module <name>] [--skills-dir <dir> | --agent <agent>]
eutaxis rule list [--module <name> | --loading-unit <name>] [-c <config-file>] [--root <folder>]
eutaxis rule list [--module <name> | --loading-unit <name>] [--skills-dir <dir> | --agent <agent>]
```

| Subcommand | Use it to |
|------------|-----------|
| `show` | Print one rule, or the parts selected by `--part`, after a location line: heading path, file and line range. |
| `list` | Print the label, the module and the first ✓ line of every rule. A label-shaped line is reported on standard error when its label violates the grammar. |

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--part` | `-p` | whole rule | Key of the part to print, from the part keys listed below. |
| `--module` | `-m` | all modules | Module or Skill that holds the rule. Required when several modules define the label. |
| `--loading-unit` | | none | Loading unit whose authored modules supply the list. Requires `--config` and cannot be combined with another source or module filter. |
| `--config` | `-c` | none | Configuration file whose modules are read: `common_sources`, agent `sources` and `task_modules`. A source entry that selects sections contributes only the rules inside those sections. |
| `--root` | `-r` | [resolved root](#root-and-configuration-file) with `--config` | Folder below which the configuration file is looked up and against which its paths resolve. Given alone, it selects the authored modules of that configuration file. |
| `--skills-dir` | | none | Directory whose eutaxis-owned Skills are read. |
| `--agent` | `-a` | `claude` | Adapter whose user-scope skill directory is read when none of `--config`, `--root` and `--skills-dir` is given. |

The part keys select the statements, the lead or the fields of a rule:

- `valid` and `invalid` select the ✓ and the ✗ statements, and `lead` selects the text before the first statement;
- `why` selects every field whose title opens on "Why", such as `*Why.*` or `*Why the tiers.*`;
- `exception` selects `*Exception.*`, `*Exceptions.*` and `*Exception*:`, and `note` selects `*Note.*` and `*Notes.*`;
- `how-to-apply` selects `*How to apply.*`;
- `test`, `key`, `scope`, `warning` and `relation` each select the field of that name, its plural, and any title opening on that word, such as `*Relation to the neighbouring rules.*`;
- the slug of any other title selects that field, as `precedence-among-the-three-enumeration-rules` selects `*Precedence among the three enumeration rules.*`.

The default source is the deployed Skills, so the query runs from any working directory. Always-on modules compile into the cumulative instruction file, so their rules are absent from the Skills and are read with `--config` or `--root`.

The query below prints the exception clause of one rule from the authored modules:

```sh
eutaxis rule show warnings-have-a-zero-baseline --part exception --root .
```

```text
verification > Verification > warnings-have-a-zero-baseline [exception] (<root>/instructions/global/verification.md:32-35)

*Exception.* Two constructions keep a non-zero count without failing:
...
```

Exit statuses:

- `0` -- the rule, the part or the listing was printed.
- `2` -- the label is unknown or ambiguous, the rule lacks the part, or the source cannot be read. The message lists the close labels, the modules or the parts of the rule.

---

### `declarations`

The `declarations` command validates, locks and resolves canonical declaration corpora.

| Subcommand | Use it to |
|------------|-----------|
| `check` | Validate a manifest-defined corpus and write a Static Analysis Results Interchange Format (SARIF) report. |
| `lock` | Generate, compare or create a canonical acquisition lock. |
| `explain` | Resolve a composition manifest and write canonical JavaScript Object Notation (JSON) that explains the result. |

The `explain` subcommand requires an acquisition manifest, its matching lock and the identifier of a composition manifest. The manifest and lock paths resolve from the current folder and must remain inside the selected root. The context option `--context` may be repeated. Each occurrence supplies a typed facet as `KEY=JSON_VALUE`. Therefore, quotation marks remain necessary around a JSON string value.

```sh
eutaxis declarations explain \
  --manifest declarations/acquisition.yaml \
  --lock declarations/acquisition.lock.json \
  --manifest-id oikos/global-agent-instructions \
  --context context.available=true \
  --context 'task.kind="programming"'
```

The output and exit status distinguish four outcomes:

- Status `0` writes a query packet whose completion field is `complete`.
- Status `1` writes a distinct diagnostic whose completion field is `failed`. The diagnostic contains the failure code, portable source coordinates and every resolver event produced before the failure.
- Status `2` reports invalid command input.
- Status `3` reports an unavailable acquisition boundary, invalidated authority, cleanup failure or output failure.

---

### `validate` (stub)

Validate prompt family layouts and configuration files.

```sh
eutaxis validate <paths...>
```

| Argument | Description |
|----------|-------------|
| `paths` | One or more files or directories to validate. |

**Status:** not yet implemented. Prints a notice and exits with status 0.

---

### `init`

Scaffold a prompt-composition structure into a target project.

```sh
eutaxis init --template codex-project --root <folder>
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--root` | `-r` | [resolved root](#root-and-configuration-file) | Project folder that receives the scaffold. |
| `--template` | | `codex-project` | Template directory under `eutaxis/data/templates`. |
| `--force` | | `false` | Overwrite existing scaffold files. |

The command copies tracked starter files from the selected template into the root, including the configuration file `eutaxis.yml`, whose first key is `_schema: eutaxis:configuration@2`. A scaffold file may hold edits, so an existing file is overwritten only under `--force`; without it, the command stops with status `2` and names the file.

---

### `ops clean-memory`

Delete the agent memory files of a project.

```sh
eutaxis ops clean-memory --agent claude|codex|all [--root <folder>] [--all] [--backup] [--dry-run] [--yes]
```

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--agent` | `-a` | required | Agent whose memory is deleted. |
| `--root` | `-r` | [resolved root](#root-and-configuration-file) | Project whose agent memory is deleted. |
| `--all` | | `false` | Delete the memory of every Claude project. |
| `--backup` | | `false` | Copy each memory folder to a timestamped sibling first. |
| `--dry-run` | | `false` | List the files without deleting them. |
| `--yes` | | `false` | Answer the confirmation in advance. |

The memory files lie outside the outputs of Eutaxis, so the command lists them and [asks for a confirmation](#files-and-confirmations) on a terminal. A script or an agent passes `--yes`.
