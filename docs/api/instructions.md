<a id="instructions"></a>

# Instructions

Instruction assembly: load YAML configuration, render per-agent instruction files from Markdown sources, and report drift between rendered content and on-disk files.

<a id="module-eutaxis.instructions.config"></a>

<a id="configuration"></a>

## Configuration

Configuration loading for instruction-file assembly.

<a id="eutaxis.instructions.config.ConfigLoader"></a>

### *class* eutaxis.instructions.config.ConfigLoader(config_path, root=None)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Load and validate instruction assembly configuration.

* **Parameters:**
  * **config_path** (*Path*)
  * **root** (*Path* *|* *None*)

<a id="eutaxis.instructions.config.ConfigLoader.load"></a>

#### load()

Load a YAML configuration file.

* **Return type:**
  [*InstructionConfig*](#eutaxis.instructions.models.InstructionConfig)

<a id="eutaxis.instructions.config.load_config"></a>

### eutaxis.instructions.config.load_config(config_path, root=None)

Load instruction configuration from disk.

* **Parameters:**
  * **config_path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *|* *None*)
* **Return type:**
  [*InstructionConfig*](#eutaxis.instructions.models.InstructionConfig)

<a id="module-eutaxis.instructions.generator"></a>

<a id="generator"></a>

## Generator

Instruction-file generation and stale-output checks.

<a id="eutaxis.instructions.generator.InstructionGenerator"></a>

### *class* eutaxis.instructions.generator.InstructionGenerator(config, assembler=None)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Generate, write and compare instruction outputs.

* **Parameters:**
  * **config** ([*InstructionConfig*](#eutaxis.instructions.models.InstructionConfig))
  * **assembler** ([*MarkdownAssembler*](#eutaxis.instructions.markdown.MarkdownAssembler) *|* *None*)

<a id="eutaxis.instructions.generator.InstructionGenerator.generate_all"></a>

#### generate_all(agent_name=None, enforce_budget=True)

Generate content for enabled outputs.

* **Parameters:**
  * **agent_name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str) *|* *None*)
  * **enforce_budget** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
* **Return type:**
  [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [str](https://docs.python.org/3/library/stdtypes.html#str)]

<a id="eutaxis.instructions.generator.InstructionGenerator.generate_for_agent"></a>

#### generate_for_agent(agent)

Generate content for one output.

* **Parameters:**
  **agent** ([*AgentConfig*](#eutaxis.instructions.models.AgentConfig))
* **Return type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

<a id="eutaxis.instructions.generator.InstructionGenerator.write_all"></a>

#### write_all(agent_name=None, dry_run=False, enforce_budget=True)

Write selected outputs and return their paths.

* **Parameters:**
  * **agent_name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str) *|* *None*)
  * **dry_run** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
  * **enforce_budget** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
* **Return type:**
  [list](https://docs.python.org/3/library/stdtypes.html#list)[[*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]

<a id="eutaxis.instructions.generator.InstructionGenerator.diff_report"></a>

#### diff_report(agent_name=None)

Yield whether each selected output differs from generated content.

* **Parameters:**
  **agent_name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str) *|* *None*)
* **Return type:**
  [*Iterator*](https://docs.python.org/3/library/typing.html#typing.Iterator)[[tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[*AgentConfig*](#eutaxis.instructions.models.AgentConfig), [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [bool](https://docs.python.org/3/library/functions.html#bool)]]

<a id="eutaxis.instructions.generator.InstructionGenerator.unified_diff"></a>

#### unified_diff(agent_name)

Return a unified diff for one output.

* **Parameters:**
  **agent_name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

<a id="eutaxis.instructions.generator.InstructionGenerator.budget_report"></a>

#### budget_report(agent_name=None)

Yield (agent, byte_size, byte_budget) for each selected agent.

* **Parameters:**
  **agent_name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str) *|* *None*)
* **Return type:**
  [*Iterator*](https://docs.python.org/3/library/typing.html#typing.Iterator)[[tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[*AgentConfig*](#eutaxis.instructions.models.AgentConfig), [int](https://docs.python.org/3/library/functions.html#int), [int](https://docs.python.org/3/library/functions.html#int) | None]]

<a id="eutaxis.instructions.generator.InstructionGenerator.render_standalone_rule_index"></a>

#### render_standalone_rule_index()

Return (path, content) for the standalone rule-index file, if any.

* **Return type:**
  [tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [str](https://docs.python.org/3/library/stdtypes.html#str)] | None

<a id="module-eutaxis.instructions.markdown"></a>

<a id="markdown-assembly"></a>

## Markdown Assembly

Markdown transformations used by instruction-file assembly.

<a id="eutaxis.instructions.markdown.parse_frontmatter"></a>

### eutaxis.instructions.markdown.parse_frontmatter(content)

Parse a Markdown file’s YAML frontmatter block.

Returns an empty dict when the file has no frontmatter or when the
frontmatter is empty. Raises `yaml.YAMLError` if the block is malformed.

* **Parameters:**
  **content** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [*Any*](https://docs.python.org/3/library/typing.html#typing.Any)]

<a id="eutaxis.instructions.markdown.MarkdownAssembler"></a>

### *class* eutaxis.instructions.markdown.MarkdownAssembler

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Extract and rewrite Markdown source content.

<a id="eutaxis.instructions.markdown.MarkdownAssembler.heading_pattern"></a>

#### heading_pattern *= re.compile('^(#{1,6})\\\\s+(.+)$')*

<a id="eutaxis.instructions.markdown.MarkdownAssembler.process"></a>

#### process(content, source)

Apply frontmatter stripping, section filtering and heading offsets.

* **Parameters:**
  * **content** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **source** ([*SourceFile*](#eutaxis.instructions.models.SourceFile))
* **Return type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

<a id="eutaxis.instructions.markdown.MarkdownAssembler.strip_frontmatter"></a>

#### strip_frontmatter(content)

Remove top-level YAML frontmatter from Markdown content.

* **Parameters:**
  **content** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

<a id="eutaxis.instructions.markdown.MarkdownAssembler.parse_sections"></a>

#### parse_sections(content)

Parse Markdown into sections.

* **Parameters:**
  **content** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [list](https://docs.python.org/3/library/stdtypes.html#list)[[*Section*](#eutaxis.instructions.models.Section)]

<a id="eutaxis.instructions.markdown.MarkdownAssembler.include_sections"></a>

#### include_sections(content, headings)

Include named sections and their nested subsections.

* **Parameters:**
  * **content** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **headings** ([*tuple*](https://docs.python.org/3/library/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,*  *...* *]*)
* **Return type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

<a id="eutaxis.instructions.markdown.MarkdownAssembler.exclude_sections"></a>

#### exclude_sections(content, headings)

Remove named sections and their nested subsections.

* **Parameters:**
  * **content** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **headings** ([*tuple*](https://docs.python.org/3/library/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,*  *...* *]*)
* **Return type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

<a id="eutaxis.instructions.markdown.MarkdownAssembler.apply_heading_offset"></a>

#### apply_heading_offset(content, offset)

Increase all Markdown heading levels by `offset`.

* **Parameters:**
  * **content** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **offset** ([*int*](https://docs.python.org/3/library/functions.html#int))
* **Return type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

<a id="module-eutaxis.instructions.models"></a>

<a id="data-models"></a>

## Data Models

Data models for instruction-file assembly.

<a id="eutaxis.instructions.models.SourceFile"></a>

### *class* eutaxis.instructions.models.SourceFile(path, sections=(), exclude_sections=(), heading_offset=0, strip_frontmatter=True)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Markdown source file included in one or more instruction outputs.

* **Parameters:**
  * **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **sections** ([*tuple*](https://docs.python.org/3/library/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,*  *...* *]*)
  * **exclude_sections** ([*tuple*](https://docs.python.org/3/library/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,*  *...* *]*)
  * **heading_offset** ([*int*](https://docs.python.org/3/library/functions.html#int))
  * **strip_frontmatter** ([*bool*](https://docs.python.org/3/library/functions.html#bool))

<a id="eutaxis.instructions.models.SourceFile.path"></a>

#### path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

<a id="eutaxis.instructions.models.SourceFile.sections"></a>

#### sections *: [tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[str](https://docs.python.org/3/library/stdtypes.html#str), ...]* *= ()*

<a id="eutaxis.instructions.models.SourceFile.exclude_sections"></a>

#### exclude_sections *: [tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[str](https://docs.python.org/3/library/stdtypes.html#str), ...]* *= ()*

<a id="eutaxis.instructions.models.SourceFile.heading_offset"></a>

#### heading_offset *: [int](https://docs.python.org/3/library/functions.html#int)* *= 0*

<a id="eutaxis.instructions.models.SourceFile.strip_frontmatter"></a>

#### strip_frontmatter *: [bool](https://docs.python.org/3/library/functions.html#bool)* *= True*

<a id="eutaxis.instructions.models.TargetConfig"></a>

### *class* eutaxis.instructions.models.TargetConfig(path, header='', footer='')

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Output file target and surrounding literal content.

* **Parameters:**
  * **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **header** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **footer** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

<a id="eutaxis.instructions.models.TargetConfig.path"></a>

#### path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

<a id="eutaxis.instructions.models.TargetConfig.header"></a>

#### header *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= ''*

<a id="eutaxis.instructions.models.TargetConfig.footer"></a>

#### footer *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= ''*

<a id="eutaxis.instructions.models.TaskModule"></a>

### *class* eutaxis.instructions.models.TaskModule(id, title, path, trigger, description=None)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

A task-specific instruction module compiled to an Agent Skill artifact.

* **Parameters:**
  * **id** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **title** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **trigger** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **description** ([*str*](https://docs.python.org/3/library/stdtypes.html#str) *|* *None*)

<a id="eutaxis.instructions.models.TaskModule.id"></a>

#### id *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.instructions.models.TaskModule.title"></a>

#### title *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.instructions.models.TaskModule.path"></a>

#### path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

<a id="eutaxis.instructions.models.TaskModule.trigger"></a>

#### trigger *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.instructions.models.TaskModule.description"></a>

#### description *: [str](https://docs.python.org/3/library/stdtypes.html#str) | [None](https://docs.python.org/3/library/constants.html#None)* *= None*

<a id="eutaxis.instructions.models.ReferenceDoc"></a>

### *class* eutaxis.instructions.models.ReferenceDoc(id, title, local_path, github_url, trigger, description='')

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

An authoritative external reference doc with a local path and GitHub fallback.

* **Parameters:**
  * **id** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **title** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **local_path** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **github_url** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **trigger** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **description** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

<a id="eutaxis.instructions.models.ReferenceDoc.id"></a>

#### id *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.instructions.models.ReferenceDoc.title"></a>

#### title *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.instructions.models.ReferenceDoc.local_path"></a>

#### local_path *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.instructions.models.ReferenceDoc.github_url"></a>

#### github_url *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.instructions.models.ReferenceDoc.trigger"></a>

#### trigger *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.instructions.models.ReferenceDoc.description"></a>

#### description *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= ''*

<a id="eutaxis.instructions.models.AgentConfig"></a>

### *class* eutaxis.instructions.models.AgentConfig(name, target, sources=<factory>, enabled=True, max_bytes=None)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

One generated instruction output.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **target** ([*TargetConfig*](#eutaxis.instructions.models.TargetConfig))
  * **sources** ([*list*](https://docs.python.org/3/library/stdtypes.html#list) *[*[*SourceFile*](#eutaxis.instructions.models.SourceFile) *]*)
  * **enabled** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
  * **max_bytes** ([*int*](https://docs.python.org/3/library/functions.html#int) *|* *None*)

<a id="eutaxis.instructions.models.AgentConfig.name"></a>

#### name *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.instructions.models.AgentConfig.target"></a>

#### target *: [TargetConfig](#eutaxis.instructions.models.TargetConfig)*

<a id="eutaxis.instructions.models.AgentConfig.sources"></a>

#### sources *: [list](https://docs.python.org/3/library/stdtypes.html#list)[[SourceFile](#eutaxis.instructions.models.SourceFile)]*

<a id="eutaxis.instructions.models.AgentConfig.enabled"></a>

#### enabled *: [bool](https://docs.python.org/3/library/functions.html#bool)* *= True*

<a id="eutaxis.instructions.models.AgentConfig.max_bytes"></a>

#### max_bytes *: [int](https://docs.python.org/3/library/functions.html#int) | [None](https://docs.python.org/3/library/constants.html#None)* *= None*

<a id="eutaxis.instructions.models.InstructionConfig"></a>

### *class* eutaxis.instructions.models.InstructionConfig(root, config_path, agents=<factory>, common_sources=<factory>, task_modules=<factory>, task_modules_heading='Task modules', task_modules_intro='', task_modules_router_enabled=True, reference_docs=<factory>, reference_docs_heading='Reference docs', reference_docs_intro='', rule_index_enabled=False, rule_index_heading='Rule index', rule_index_intro='', rule_index_pointer='', rule_index_target=None, default_max_bytes=None)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Complete instruction assembly configuration.

* **Parameters:**
  * **root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **config_path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **agents** ([*list*](https://docs.python.org/3/library/stdtypes.html#list) *[*[*AgentConfig*](#eutaxis.instructions.models.AgentConfig) *]*)
  * **common_sources** ([*list*](https://docs.python.org/3/library/stdtypes.html#list) *[*[*SourceFile*](#eutaxis.instructions.models.SourceFile) *]*)
  * **task_modules** ([*list*](https://docs.python.org/3/library/stdtypes.html#list) *[*[*TaskModule*](#eutaxis.instructions.models.TaskModule) *]*)
  * **task_modules_heading** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **task_modules_intro** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **task_modules_router_enabled** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
  * **reference_docs** ([*list*](https://docs.python.org/3/library/stdtypes.html#list) *[*[*ReferenceDoc*](#eutaxis.instructions.models.ReferenceDoc) *]*)
  * **reference_docs_heading** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **reference_docs_intro** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **rule_index_enabled** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
  * **rule_index_heading** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **rule_index_intro** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **rule_index_pointer** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **rule_index_target** ([*TargetConfig*](#eutaxis.instructions.models.TargetConfig) *|* *None*)
  * **default_max_bytes** ([*int*](https://docs.python.org/3/library/functions.html#int) *|* *None*)

<a id="eutaxis.instructions.models.InstructionConfig.root"></a>

#### root *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

<a id="eutaxis.instructions.models.InstructionConfig.config_path"></a>

#### config_path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

<a id="eutaxis.instructions.models.InstructionConfig.agents"></a>

#### agents *: [list](https://docs.python.org/3/library/stdtypes.html#list)[[AgentConfig](#eutaxis.instructions.models.AgentConfig)]*

<a id="eutaxis.instructions.models.InstructionConfig.common_sources"></a>

#### common_sources *: [list](https://docs.python.org/3/library/stdtypes.html#list)[[SourceFile](#eutaxis.instructions.models.SourceFile)]*

<a id="eutaxis.instructions.models.InstructionConfig.task_modules"></a>

#### task_modules *: [list](https://docs.python.org/3/library/stdtypes.html#list)[[TaskModule](#eutaxis.instructions.models.TaskModule)]*

<a id="eutaxis.instructions.models.InstructionConfig.task_modules_heading"></a>

#### task_modules_heading *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= 'Task modules'*

<a id="eutaxis.instructions.models.InstructionConfig.task_modules_intro"></a>

#### task_modules_intro *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= ''*

<a id="eutaxis.instructions.models.InstructionConfig.task_modules_router_enabled"></a>

#### task_modules_router_enabled *: [bool](https://docs.python.org/3/library/functions.html#bool)* *= True*

<a id="eutaxis.instructions.models.InstructionConfig.reference_docs"></a>

#### reference_docs *: [list](https://docs.python.org/3/library/stdtypes.html#list)[[ReferenceDoc](#eutaxis.instructions.models.ReferenceDoc)]*

<a id="eutaxis.instructions.models.InstructionConfig.reference_docs_heading"></a>

#### reference_docs_heading *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= 'Reference docs'*

<a id="eutaxis.instructions.models.InstructionConfig.reference_docs_intro"></a>

#### reference_docs_intro *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= ''*

<a id="eutaxis.instructions.models.InstructionConfig.rule_index_enabled"></a>

#### rule_index_enabled *: [bool](https://docs.python.org/3/library/functions.html#bool)* *= False*

<a id="eutaxis.instructions.models.InstructionConfig.rule_index_heading"></a>

#### rule_index_heading *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= 'Rule index'*

<a id="eutaxis.instructions.models.InstructionConfig.rule_index_intro"></a>

#### rule_index_intro *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= ''*

<a id="eutaxis.instructions.models.InstructionConfig.rule_index_pointer"></a>

#### rule_index_pointer *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= ''*

<a id="eutaxis.instructions.models.InstructionConfig.rule_index_target"></a>

#### rule_index_target *: [TargetConfig](#eutaxis.instructions.models.TargetConfig) | [None](https://docs.python.org/3/library/constants.html#None)* *= None*

<a id="eutaxis.instructions.models.InstructionConfig.default_max_bytes"></a>

#### default_max_bytes *: [int](https://docs.python.org/3/library/functions.html#int) | [None](https://docs.python.org/3/library/constants.html#None)* *= None*

<a id="eutaxis.instructions.models.InstructionConfig.budget_for"></a>

#### budget_for(agent)

Return the byte budget that applies to one agent, if any.

* **Parameters:**
  **agent** ([*AgentConfig*](#eutaxis.instructions.models.AgentConfig))
* **Return type:**
  [int](https://docs.python.org/3/library/functions.html#int) | None

<a id="eutaxis.instructions.models.InstructionConfig.enabled_agents"></a>

#### enabled_agents()

Return enabled agent outputs.

* **Return type:**
  [list](https://docs.python.org/3/library/stdtypes.html#list)[[*AgentConfig*](#eutaxis.instructions.models.AgentConfig)]

<a id="eutaxis.instructions.models.InstructionConfig.get_agent"></a>

#### get_agent(name)

Return an agent output by name.

* **Parameters:**
  **name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [*AgentConfig*](#eutaxis.instructions.models.AgentConfig) | None

<a id="eutaxis.instructions.models.InstructionConfig.resolve"></a>

#### resolve(path)

Resolve a config path against the configured root.

* **Parameters:**
  **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

<a id="eutaxis.instructions.models.Section"></a>

### *class* eutaxis.instructions.models.Section(heading, level, content)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

A Markdown section with its heading and full body.

* **Parameters:**
  * **heading** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **level** ([*int*](https://docs.python.org/3/library/functions.html#int))
  * **content** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

<a id="eutaxis.instructions.models.Section.heading"></a>

#### heading *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.instructions.models.Section.level"></a>

#### level *: [int](https://docs.python.org/3/library/functions.html#int)*

<a id="eutaxis.instructions.models.Section.content"></a>

#### content *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="module-eutaxis.instructions.exceptions"></a>

<a id="exceptions"></a>

## Exceptions

Exceptions for instruction-file assembly.

<a id="eutaxis.instructions.exceptions.InstructionError"></a>

### *exception* eutaxis.instructions.exceptions.InstructionError

Bases: [`Exception`](https://docs.python.org/3/library/exceptions.html#Exception)

Base exception for instruction assembly errors.

<a id="eutaxis.instructions.exceptions.InstructionError.exit_code"></a>

#### exit_code *= 1*

<a id="eutaxis.instructions.exceptions.ConfigurationError"></a>

### *exception* eutaxis.instructions.exceptions.ConfigurationError

Bases: [`InstructionError`](#eutaxis.instructions.exceptions.InstructionError)

Raised when an instruction config file is invalid.

<a id="eutaxis.instructions.exceptions.SourceNotFoundError"></a>

### *exception* eutaxis.instructions.exceptions.SourceNotFoundError(path)

Bases: [`InstructionError`](#eutaxis.instructions.exceptions.InstructionError)

Raised when a configured source file does not exist.

* **Parameters:**
  **path** (*Path*)
* **Return type:**
  None

<a id="eutaxis.instructions.exceptions.BudgetExceededError"></a>

### *exception* eutaxis.instructions.exceptions.BudgetExceededError(agent_name, size, limit)

Bases: [`InstructionError`](#eutaxis.instructions.exceptions.InstructionError)

Raised when a rendered output exceeds its configured byte budget.

* **Parameters:**
  * **agent_name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **size** ([*int*](https://docs.python.org/3/library/functions.html#int))
  * **limit** ([*int*](https://docs.python.org/3/library/functions.html#int))
* **Return type:**
  None

<a id="eutaxis.instructions.exceptions.BudgetExceededError.exit_code"></a>

#### exit_code *= 2*
