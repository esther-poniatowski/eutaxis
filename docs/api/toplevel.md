<a id="top-level-entry-points"></a>

# Top-Level Entry Points

User-facing commands invoked from the CLI: generate instruction files, validate configuration, scaffold a new project, and the CLI dispatcher itself.

<a id="module-eutaxis.cli"></a>

<a id="cli"></a>

## CLI

Command-line interface for the `eutaxis` package.

Defines commands available via `python -m eutaxis` or `eutaxis` if
installed as a script. Subcommands:

- `info` — display diagnostic information.
- `generate` — assemble agent instruction files.
- `rule` — print individual rules of instruction modules or skills.
- `validate` — validate prompt family layouts (planned).
- `init` — scaffold prompt composition into a project (planned).

<a id="eutaxis.cli.cli_info"></a>

### eutaxis.cli.cli_info()

Display version and platform diagnostics.

* **Return type:**
  None

<a id="eutaxis.cli.cli_generate"></a>

### eutaxis.cli.cli_generate(config=<typer.models.OptionInfo object>, root=<typer.models.OptionInfo object>, agent=<typer.models.OptionInfo object>, dry_run=<typer.models.OptionInfo object>, plan=<typer.models.OptionInfo object>, ignore_budget=<typer.models.OptionInfo object>)

Assemble agent instruction files from modular prompt sources.

Every label line rejected by the label grammar is reported on standard
error. Under `strict_rule_labels`, such a line fails the command before
any file is written.

* **Parameters:**
  * **config** (*str* *|* *None*)
  * **root** (*str* *|* *None*)
  * **agent** (*str* *|* *None*)
  * **dry_run** (*bool*)
  * **plan** (*bool*)
  * **ignore_budget** (*bool*)
* **Return type:**
  None

<a id="eutaxis.cli.cli_check"></a>

### eutaxis.cli.cli_check(config=<typer.models.OptionInfo object>, root=<typer.models.OptionInfo object>, agent=<typer.models.OptionInfo object>, diff=<typer.models.OptionInfo object>, ignore_budget=<typer.models.OptionInfo object>)

Check whether generated instruction files are up to date.

Rejected label lines are reported as by `generate`, and they fail the
check under `strict_rule_labels`.

* **Parameters:**
  * **config** (*str* *|* *None*)
  * **root** (*str* *|* *None*)
  * **agent** (*str* *|* *None*)
  * **diff** (*bool*)
  * **ignore_budget** (*bool*)
* **Return type:**
  None

<a id="eutaxis.cli.cli_list"></a>

### eutaxis.cli.cli_list(config=<typer.models.OptionInfo object>, root=<typer.models.OptionInfo object>)

List configured instruction outputs and their source counts.

* **Parameters:**
  * **config** (*str* *|* *None*)
  * **root** (*str* *|* *None*)
* **Return type:**
  None

<a id="eutaxis.cli.cli_scan"></a>

### eutaxis.cli.cli_scan(config=<typer.models.OptionInfo object>, root=<typer.models.OptionInfo object>, directory=<typer.models.OptionInfo object>, register=<typer.models.OptionInfo object>)

Report instruction files that drift from the configured registry.

* **Parameters:**
  * **config** (*str* *|* *None*)
  * **root** (*str* *|* *None*)
  * **directory** (*str* *|* *None*)
  * **register** (*bool*)
* **Return type:**
  None

<a id="eutaxis.cli.cli_validate"></a>

### eutaxis.cli.cli_validate(paths=<typer.models.ArgumentInfo object>)

Validate prompt family layouts and configs (planned).

* **Parameters:**
  **paths** (*list* *[**str* *]*)
* **Return type:**
  None

<a id="eutaxis.cli.cli_init"></a>

### eutaxis.cli.cli_init(root=<typer.models.OptionInfo object>, template=<typer.models.OptionInfo object>, force=<typer.models.OptionInfo object>)

Scaffold prompt-composition structure into a project.

* **Parameters:**
  * **root** (*str* *|* *None*)
  * **template** (*str*)
  * **force** (*bool*)
* **Return type:**
  None

<a id="eutaxis.cli.main_callback"></a>

### eutaxis.cli.main_callback(version=<typer.models.OptionInfo object>)

Prompt composition framework.

* **Parameters:**
  **version** (*bool*)
* **Return type:**
  None

<a id="generate"></a>

## Generate

`eutaxis.generate` is a thin backward-compatibility shim that re-exports
the public surface of `eutaxis.instructions`. Only the module’s own
entry point is documented here; the re-exported classes appear under
[Instructions](instructions.md).

<a id="eutaxis.generate.main"></a>

### eutaxis.generate.main(config_path)

Compatibility entry point used by older `eutaxis generate` calls.

* **Parameters:**
  **config_path** (*Path*)
* **Return type:**
  int

<a id="module-eutaxis.validate"></a>

<a id="validate"></a>

## Validate

Prompt validation module.

Will validate prompt family layouts, composition configs, and related
artifacts against eutaxis profile rules.

This module is a stub. Implementation will follow once family profiles
and assembly diagnostics are stabilized.

<a id="eutaxis.validate.validate_prompt_paths"></a>

### eutaxis.validate.validate_prompt_paths(paths)

Validate that the referenced prompt files exist.

* **Parameters:**
  **paths** (*list* *[**Path* *]*) – Prompt-related files or directories to validate.
* **Returns:**
  List of validation error messages. Empty if all paths exist.
* **Return type:**
  list of str

<a id="module-eutaxis.scaffold"></a>

<a id="scaffold"></a>

## Scaffold

Prompt scaffolding helpers.

<a id="eutaxis.scaffold.ScaffoldError"></a>

### *exception* eutaxis.scaffold.ScaffoldError

Bases: `RuntimeError`

Raised when a scaffold operation cannot be completed safely.

Every scaffold error is a usage error (exit status 2): an unknown
template, or an existing file that only `--force` may overwrite.

<a id="eutaxis.scaffold.ScaffoldError.exit_code"></a>

#### exit_code *= 2*

<a id="eutaxis.scaffold.template_root"></a>

### eutaxis.scaffold.template_root()

Return the packaged template root.

* **Return type:**
  *Path*

<a id="eutaxis.scaffold.available_templates"></a>

### eutaxis.scaffold.available_templates()

Return available named scaffold template directories.

* **Return type:**
  list[str]

<a id="eutaxis.scaffold.scaffold_workspace"></a>

### eutaxis.scaffold.scaffold_workspace(target, \*, template='codex-project', force=False)

Scaffold prompt-composition structure into a target project.

Existing files are left untouched unless `force` is true.

* **Parameters:**
  * **target** (*Path*) – Root of the target project.
  * **template** (*str*) – Name of the template directory under `eutaxis/data/templates`.
  * **force** (*bool*) – Overwrite existing files when true.
* **Return type:**
  list[*Path*]
