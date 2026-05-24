# Top-Level Entry Points

User-facing commands invoked from the CLI: generate instruction files, validate configuration, scaffold a new project, and the CLI dispatcher itself.

## CLI

Command-line interface for the eutaxis package.

Defines commands available via python -m eutaxis or eutaxis if installed as a script.

### Commands

info : Display diagnostic information.
generate : Assemble agent instruction files.
validate : Validate prompt family layouts (planned).
init : Scaffold prompt composition into a project (planned).

### eutaxis.cli.cli_info()

Display version and platform diagnostics.

* **Return type:**
  None

### eutaxis.cli.cli_generate(config=<typer.models.OptionInfo object>, root=<typer.models.OptionInfo object>, agent=<typer.models.OptionInfo object>, dry_run=<typer.models.OptionInfo object>, ignore_budget=<typer.models.OptionInfo object>)

Assemble agent instruction files from modular prompt sources.

* **Parameters:**
  * **config** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **root** ([*str*](https://docs.python.org/3/library/stdtypes.html#str) *|* *None*)
  * **agent** ([*str*](https://docs.python.org/3/library/stdtypes.html#str) *|* *None*)
  * **dry_run** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
  * **ignore_budget** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
* **Return type:**
  None

### eutaxis.cli.cli_check(config=<typer.models.OptionInfo object>, root=<typer.models.OptionInfo object>, agent=<typer.models.OptionInfo object>, diff=<typer.models.OptionInfo object>, ignore_budget=<typer.models.OptionInfo object>)

Check whether generated instruction files are up to date.

* **Parameters:**
  * **config** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **root** ([*str*](https://docs.python.org/3/library/stdtypes.html#str) *|* *None*)
  * **agent** ([*str*](https://docs.python.org/3/library/stdtypes.html#str) *|* *None*)
  * **diff** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
  * **ignore_budget** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
* **Return type:**
  None

### eutaxis.cli.cli_list(config=<typer.models.OptionInfo object>, root=<typer.models.OptionInfo object>)

List configured instruction outputs and their source counts.

* **Parameters:**
  * **config** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **root** ([*str*](https://docs.python.org/3/library/stdtypes.html#str) *|* *None*)
* **Return type:**
  None

### eutaxis.cli.cli_validate(paths=<typer.models.ArgumentInfo object>)

Validate prompt family layouts and configs (planned).

* **Parameters:**
  **paths** ([*list*](https://docs.python.org/3/library/stdtypes.html#list) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *]*)
* **Return type:**
  None

### eutaxis.cli.cli_init(target=<typer.models.OptionInfo object>, template=<typer.models.OptionInfo object>, force=<typer.models.OptionInfo object>)

Scaffold prompt-composition structure into a project.

* **Parameters:**
  * **target** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **template** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **force** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
* **Return type:**
  None

### eutaxis.cli.main_callback(version=<typer.models.OptionInfo object>)

Prompt composition framework.

* **Parameters:**
  **version** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
* **Return type:**
  None

## Generate

Compatibility interface for instruction-file generation.

New code should import from `eutaxis.instructions`. This module preserves the
initial `eutaxis.generate` API used by existing tests, scripts, and project
configs.

### *class* eutaxis.generate.AgentConfig(name, target, sources=<factory>, enabled=True, max_bytes=None)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

One generated instruction output.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **target** ([*TargetConfig*](instructions.md#eutaxis.instructions.models.TargetConfig))
  * **sources** ([*list*](https://docs.python.org/3/library/stdtypes.html#list) *[*[*SourceFile*](instructions.md#eutaxis.instructions.models.SourceFile) *]*)
  * **enabled** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
  * **max_bytes** ([*int*](https://docs.python.org/3/library/functions.html#int) *|* *None*)

#### enabled *: [bool](https://docs.python.org/3/library/functions.html#bool)* *= True*

#### max_bytes *: [int](https://docs.python.org/3/library/functions.html#int) | [None](https://docs.python.org/3/library/constants.html#None)* *= None*

#### name *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### target *: [TargetConfig](instructions.md#eutaxis.instructions.models.TargetConfig)*

#### sources *: [list](https://docs.python.org/3/library/stdtypes.html#list)[[SourceFile](instructions.md#eutaxis.instructions.models.SourceFile)]*

### *exception* eutaxis.generate.BudgetExceededError(agent_name, size, limit)

Bases: [`InstructionError`](instructions.md#eutaxis.instructions.exceptions.InstructionError)

Raised when a rendered output exceeds its configured byte budget.

* **Parameters:**
  * **agent_name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **size** ([*int*](https://docs.python.org/3/library/functions.html#int))
  * **limit** ([*int*](https://docs.python.org/3/library/functions.html#int))
* **Return type:**
  None

#### exit_code *= 2*

### *class* eutaxis.generate.ConfigLoader(config_path, root=None)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Load and validate instruction assembly configuration.

* **Parameters:**
  * **config_path** (*Path*)
  * **root** (*Path* *|* *None*)

#### load()

Load a YAML configuration file.

* **Return type:**
  [*InstructionConfig*](instructions.md#eutaxis.instructions.models.InstructionConfig)

### *exception* eutaxis.generate.ConfigurationError

Bases: [`InstructionError`](instructions.md#eutaxis.instructions.exceptions.InstructionError)

Raised when an instruction config file is invalid.

### *class* eutaxis.generate.InstructionConfig(root, config_path, agents=<factory>, common_sources=<factory>, task_modules=<factory>, task_modules_heading='Task modules', task_modules_intro='', reference_docs=<factory>, reference_docs_heading='Reference docs', reference_docs_intro='', rule_index_enabled=False, rule_index_heading='Rule index', rule_index_intro='', default_max_bytes=None)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Complete instruction assembly configuration.

* **Parameters:**
  * **root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **config_path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **agents** ([*list*](https://docs.python.org/3/library/stdtypes.html#list) *[*[*AgentConfig*](instructions.md#eutaxis.instructions.models.AgentConfig) *]*)
  * **common_sources** ([*list*](https://docs.python.org/3/library/stdtypes.html#list) *[*[*SourceFile*](instructions.md#eutaxis.instructions.models.SourceFile) *]*)
  * **task_modules** ([*list*](https://docs.python.org/3/library/stdtypes.html#list) *[*[*TaskModule*](instructions.md#eutaxis.instructions.models.TaskModule) *]*)
  * **task_modules_heading** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **task_modules_intro** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **reference_docs** ([*list*](https://docs.python.org/3/library/stdtypes.html#list) *[*[*ReferenceDoc*](instructions.md#eutaxis.instructions.models.ReferenceDoc) *]*)
  * **reference_docs_heading** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **reference_docs_intro** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **rule_index_enabled** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
  * **rule_index_heading** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **rule_index_intro** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **default_max_bytes** ([*int*](https://docs.python.org/3/library/functions.html#int) *|* *None*)

#### budget_for(agent)

Return the byte budget that applies to one agent, if any.

* **Parameters:**
  **agent** ([*AgentConfig*](instructions.md#eutaxis.instructions.models.AgentConfig))
* **Return type:**
  [int](https://docs.python.org/3/library/functions.html#int) | None

#### default_max_bytes *: [int](https://docs.python.org/3/library/functions.html#int) | [None](https://docs.python.org/3/library/constants.html#None)* *= None*

#### enabled_agents()

Return enabled agent outputs.

* **Return type:**
  [list](https://docs.python.org/3/library/stdtypes.html#list)[[*AgentConfig*](instructions.md#eutaxis.instructions.models.AgentConfig)]

#### get_agent(name)

Return an agent output by name.

* **Parameters:**
  **name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [*AgentConfig*](instructions.md#eutaxis.instructions.models.AgentConfig) | None

#### reference_docs_heading *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= 'Reference docs'*

#### reference_docs_intro *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= ''*

#### resolve(path)

Resolve a config path against the configured root.

* **Parameters:**
  **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

#### rule_index_enabled *: [bool](https://docs.python.org/3/library/functions.html#bool)* *= False*

#### rule_index_heading *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= 'Rule index'*

#### rule_index_intro *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= ''*

#### task_modules_heading *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= 'Task modules'*

#### task_modules_intro *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= ''*

#### root *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

#### config_path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

#### agents *: [list](https://docs.python.org/3/library/stdtypes.html#list)[[AgentConfig](instructions.md#eutaxis.instructions.models.AgentConfig)]*

#### common_sources *: [list](https://docs.python.org/3/library/stdtypes.html#list)[[SourceFile](instructions.md#eutaxis.instructions.models.SourceFile)]*

#### task_modules *: [list](https://docs.python.org/3/library/stdtypes.html#list)[[TaskModule](instructions.md#eutaxis.instructions.models.TaskModule)]*

#### reference_docs *: [list](https://docs.python.org/3/library/stdtypes.html#list)[[ReferenceDoc](instructions.md#eutaxis.instructions.models.ReferenceDoc)]*

### *exception* eutaxis.generate.InstructionError

Bases: [`Exception`](https://docs.python.org/3/library/exceptions.html#Exception)

Base exception for instruction assembly errors.

#### exit_code *= 1*

### *class* eutaxis.generate.InstructionGenerator(config, assembler=None)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Generate, write and compare instruction outputs.

* **Parameters:**
  * **config** ([*InstructionConfig*](#eutaxis.generate.InstructionConfig))
  * **assembler** ([*MarkdownAssembler*](#eutaxis.generate.MarkdownAssembler) *|* *None*)

#### budget_report(agent_name=None)

Yield (agent, byte_size, byte_budget) for each selected agent.

* **Parameters:**
  **agent_name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str) *|* *None*)
* **Return type:**
  [*Iterator*](https://docs.python.org/3/library/typing.html#typing.Iterator)[[tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[*AgentConfig*](instructions.md#eutaxis.instructions.models.AgentConfig), [int](https://docs.python.org/3/library/functions.html#int), [int](https://docs.python.org/3/library/functions.html#int) | None]]

#### diff_report(agent_name=None)

Yield whether each selected output differs from generated content.

* **Parameters:**
  **agent_name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str) *|* *None*)
* **Return type:**
  [*Iterator*](https://docs.python.org/3/library/typing.html#typing.Iterator)[[tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[*AgentConfig*](instructions.md#eutaxis.instructions.models.AgentConfig), [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [bool](https://docs.python.org/3/library/functions.html#bool)]]

#### generate_all(agent_name=None, enforce_budget=True)

Generate content for enabled outputs.

* **Parameters:**
  * **agent_name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str) *|* *None*)
  * **enforce_budget** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
* **Return type:**
  [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [str](https://docs.python.org/3/library/stdtypes.html#str)]

#### generate_for_agent(agent)

Generate content for one output.

* **Parameters:**
  **agent** ([*AgentConfig*](instructions.md#eutaxis.instructions.models.AgentConfig))
* **Return type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

#### unified_diff(agent_name)

Return a unified diff for one output.

* **Parameters:**
  **agent_name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

#### write_all(agent_name=None, dry_run=False, enforce_budget=True)

Write selected outputs and return their paths.

* **Parameters:**
  * **agent_name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str) *|* *None*)
  * **dry_run** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
  * **enforce_budget** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
* **Return type:**
  [list](https://docs.python.org/3/library/stdtypes.html#list)[[*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]

### *class* eutaxis.generate.MarkdownAssembler

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Extract and rewrite Markdown source content.

#### apply_heading_offset(content, offset)

Increase all Markdown heading levels by `offset`.

* **Parameters:**
  * **content** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **offset** ([*int*](https://docs.python.org/3/library/functions.html#int))
* **Return type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

#### exclude_sections(content, headings)

Remove named sections and their nested subsections.

* **Parameters:**
  * **content** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **headings** ([*tuple*](https://docs.python.org/3/library/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,*  *...* *]*)
* **Return type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

#### heading_pattern *= re.compile('^(#{1,6})\\\\s+(.+)$')*

#### include_sections(content, headings)

Include named sections and their nested subsections.

* **Parameters:**
  * **content** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **headings** ([*tuple*](https://docs.python.org/3/library/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,*  *...* *]*)
* **Return type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

#### parse_sections(content)

Parse Markdown into sections.

* **Parameters:**
  **content** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [list](https://docs.python.org/3/library/stdtypes.html#list)[[*Section*](instructions.md#eutaxis.instructions.models.Section)]

#### process(content, source)

Apply frontmatter stripping, section filtering and heading offsets.

* **Parameters:**
  * **content** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **source** ([*SourceFile*](instructions.md#eutaxis.instructions.models.SourceFile))
* **Return type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

#### strip_frontmatter(content)

Remove top-level YAML frontmatter from Markdown content.

* **Parameters:**
  **content** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

### *class* eutaxis.generate.ReferenceDoc(id, title, local_path, github_url, trigger, description='')

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

An authoritative external reference doc with a local path and GitHub fallback.

* **Parameters:**
  * **id** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **title** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **local_path** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **github_url** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **trigger** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **description** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

#### description *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= ''*

#### id *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### title *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### local_path *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### github_url *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### trigger *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

### *class* eutaxis.generate.Section(heading, level, content)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

A Markdown section with its heading and full body.

* **Parameters:**
  * **heading** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **level** ([*int*](https://docs.python.org/3/library/functions.html#int))
  * **content** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

#### heading *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### level *: [int](https://docs.python.org/3/library/functions.html#int)*

#### content *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

### *class* eutaxis.generate.SourceFile(path, sections=(), exclude_sections=(), heading_offset=0, strip_frontmatter=True)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Markdown source file included in one or more instruction outputs.

* **Parameters:**
  * **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **sections** ([*tuple*](https://docs.python.org/3/library/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,*  *...* *]*)
  * **exclude_sections** ([*tuple*](https://docs.python.org/3/library/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,*  *...* *]*)
  * **heading_offset** ([*int*](https://docs.python.org/3/library/functions.html#int))
  * **strip_frontmatter** ([*bool*](https://docs.python.org/3/library/functions.html#bool))

#### exclude_sections *: [tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[str](https://docs.python.org/3/library/stdtypes.html#str), ...]* *= ()*

#### heading_offset *: [int](https://docs.python.org/3/library/functions.html#int)* *= 0*

#### sections *: [tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[str](https://docs.python.org/3/library/stdtypes.html#str), ...]* *= ()*

#### strip_frontmatter *: [bool](https://docs.python.org/3/library/functions.html#bool)* *= True*

#### path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

### *exception* eutaxis.generate.SourceNotFoundError(path)

Bases: [`InstructionError`](instructions.md#eutaxis.instructions.exceptions.InstructionError)

Raised when a configured source file does not exist.

* **Parameters:**
  **path** (*Path*)
* **Return type:**
  None

### *class* eutaxis.generate.TargetConfig(path, header='', footer='')

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Output file target and surrounding literal content.

* **Parameters:**
  * **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **header** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **footer** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

#### footer *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= ''*

#### header *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= ''*

#### path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

### *class* eutaxis.generate.TaskModule(id, title, path, trigger, description='')

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

A task-specific instruction module referenced by the router section.

* **Parameters:**
  * **id** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **title** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **trigger** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **description** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

#### description *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= ''*

#### id *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### title *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

#### trigger *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

### eutaxis.generate.load_config(config_path, root=None)

Load instruction configuration from disk.

* **Parameters:**
  * **config_path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *|* *None*)
* **Return type:**
  [*InstructionConfig*](instructions.md#eutaxis.instructions.models.InstructionConfig)

### eutaxis.generate.main(config_path)

Compatibility entry point used by older `eutaxis generate` calls.

* **Parameters:**
  **config_path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [int](https://docs.python.org/3/library/functions.html#int)

## Validate

Prompt validation module.

Will validate prompt family layouts, composition configs, and related
artifacts against eutaxis profile rules.

This module is a stub. Implementation will follow once family profiles
and assembly diagnostics are stabilized.

### eutaxis.validate.validate_prompt_paths(paths)

Validate that the referenced prompt files exist.

* **Parameters:**
  **paths** ([*list*](https://docs.python.org/3/library/stdtypes.html#list) *[**Path* *]*) – Prompt-related files or directories to validate.
* **Returns:**
  List of validation error messages. Empty if all paths exist.
* **Return type:**
  [list](https://docs.python.org/3/library/stdtypes.html#list) of [str](https://docs.python.org/3/library/stdtypes.html#str)

## Scaffold

Prompt scaffolding helpers.

### *exception* eutaxis.scaffold.ScaffoldError

Bases: [`RuntimeError`](https://docs.python.org/3/library/exceptions.html#RuntimeError)

Raised when a scaffold operation cannot be completed safely.

### eutaxis.scaffold.template_root()

Return the packaged template root.

* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### eutaxis.scaffold.available_templates()

Return available named scaffold template directories.

* **Return type:**
  [list](https://docs.python.org/3/library/stdtypes.html#list)[[str](https://docs.python.org/3/library/stdtypes.html#str)]

### eutaxis.scaffold.scaffold_workspace(target, , template='codex-project', force=False)

Scaffold prompt-composition structure into a target project.

Existing files are left untouched unless `force` is true.

* **Parameters:**
  * **target** (*Path*) – Root of the target project.
  * **template** ([*str*](https://docs.python.org/3/library/stdtypes.html#str)) – Name of the template directory under `eutaxis/data/templates`.
  * **force** ([*bool*](https://docs.python.org/3/library/functions.html#bool)) – Overwrite existing files when true.
* **Return type:**
  [list](https://docs.python.org/3/library/stdtypes.html#list)[[*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]
