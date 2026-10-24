<a id="instructions"></a>

# Instructions

Instruction assembly: load YAML configuration, render per-agent instruction files from Markdown sources, and report drift between rendered content and on-disk files.

<a id="module-eutaxis.instructions.config"></a>

<a id="configuration"></a>

## Configuration

Configuration loading for instruction-file assembly.

<a id="eutaxis.instructions.config.ConfigLoader"></a>

### *class* eutaxis.instructions.config.ConfigLoader(config_path, root=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

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

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Generate, write and compare instruction outputs.

* **Parameters:**
  * **config** ([*InstructionConfig*](#eutaxis.instructions.models.InstructionConfig))
  * **assembler** ([*MarkdownAssembler*](#eutaxis.instructions.markdown.MarkdownAssembler) *|* *None*)

<a id="eutaxis.instructions.generator.InstructionGenerator.generate_all"></a>

#### generate_all(agent_name=None, enforce_budget=True)

Generate content for enabled outputs.

* **Parameters:**
  * **agent_name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* *None*)
  * **enforce_budget** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool))
* **Return type:**
  [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]

<a id="eutaxis.instructions.generator.InstructionGenerator.generate_for_agent"></a>

#### generate_for_agent(agent)

Generate content for one output.

* **Parameters:**
  **agent** ([*AgentConfig*](#eutaxis.instructions.models.AgentConfig))
* **Return type:**
  [str](https://docs.python.org/3/builtins/stdtypes.html#str)

<a id="eutaxis.instructions.generator.InstructionGenerator.write_all"></a>

#### write_all(agent_name=None, dry_run=False, enforce_budget=True)

Write selected outputs and return their paths.

* **Raises:**
  * [**RejectedLabelError**](#eutaxis.instructions.exceptions.RejectedLabelError) – When the configuration sets `strict_rule_labels` and a declared
        module holds a rejected label line. Nothing is written.
  * [**BudgetExceededError**](#eutaxis.instructions.exceptions.BudgetExceededError) – When `enforce_budget` is set and an output exceeds its budget.
* **Parameters:**
  * **agent_name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* *None*)
  * **dry_run** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool))
  * **enforce_budget** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool))
* **Return type:**
  [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]

<a id="eutaxis.instructions.generator.InstructionGenerator.rejected_labels"></a>

#### rejected_labels()

Return the label-shaped lines that the label grammar rejects.

Every module declared by the configuration is parsed whole, as the
rule index scans it: `common_sources`, `task_modules` and the
`sources` of each agent. A rejected line defines no label, so the
rule index, the rule query and progressive disclosure all omit it. A
declared module missing on disk is skipped here; generation reports
it.

* **Return type:**
  [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [*RejectedLabel*](#eutaxis.instructions.rules.RejectedLabel)]]

<a id="eutaxis.instructions.generator.InstructionGenerator.enforce_rule_labels"></a>

#### enforce_rule_labels()

Raise when `strict_rule_labels` is set and a label line is rejected.

* **Raises:**
  [**RejectedLabelError**](#eutaxis.instructions.exceptions.RejectedLabelError) – Listing the location of every rejected line.
* **Return type:**
  None

<a id="eutaxis.instructions.generator.InstructionGenerator.diff_report"></a>

#### diff_report(agent_name=None)

Yield whether each selected output differs from generated content.

* **Parameters:**
  **agent_name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* *None*)
* **Return type:**
  [*Iterator*](https://docs.python.org/3/library/typing.html#typing.Iterator)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[*AgentConfig*](#eutaxis.instructions.models.AgentConfig), [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [bool](https://docs.python.org/3/builtins/functions.html#bool)]]

<a id="eutaxis.instructions.generator.InstructionGenerator.unified_diff"></a>

#### unified_diff(agent_name)

Return a unified diff for one output.

* **Parameters:**
  **agent_name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  [str](https://docs.python.org/3/builtins/stdtypes.html#str)

<a id="eutaxis.instructions.generator.InstructionGenerator.budget_report"></a>

#### budget_report(agent_name=None)

Yield (agent, byte_size, byte_budget) for each selected agent.

* **Parameters:**
  **agent_name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* *None*)
* **Return type:**
  [*Iterator*](https://docs.python.org/3/library/typing.html#typing.Iterator)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[*AgentConfig*](#eutaxis.instructions.models.AgentConfig), [int](https://docs.python.org/3/builtins/functions.html#int), [int](https://docs.python.org/3/builtins/functions.html#int) | None]]

<a id="eutaxis.instructions.generator.InstructionGenerator.instruction_chain_budget_report"></a>

#### instruction_chain_budget_report(agent_name=None)

Yield each selected global-plus-project chain and its byte budget.

* **Parameters:**
  **agent_name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* *None*)
* **Return type:**
  [*Iterator*](https://docs.python.org/3/library/typing.html#typing.Iterator)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[*InstructionChain*](#eutaxis.instructions.models.InstructionChain), [int](https://docs.python.org/3/builtins/functions.html#int), [int](https://docs.python.org/3/builtins/functions.html#int)]]

<a id="eutaxis.instructions.generator.InstructionGenerator.render_standalone_rule_index"></a>

#### render_standalone_rule_index()

Return (path, content) for the standalone rule-index file, if any.

* **Return type:**
  [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [str](https://docs.python.org/3/builtins/stdtypes.html#str)] | None

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
  **content** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [*Any*](https://docs.python.org/3/library/typing.html#typing.Any)]

<a id="eutaxis.instructions.markdown.MarkdownAssembler"></a>

### *class* eutaxis.instructions.markdown.MarkdownAssembler

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Extract and rewrite Markdown source content.

<a id="eutaxis.instructions.markdown.MarkdownAssembler.heading_pattern"></a>

#### heading_pattern *= re.compile('^(#{1,6})\\\\s+(.+)$')*

<a id="eutaxis.instructions.markdown.MarkdownAssembler.process"></a>

#### process(content, source)

Apply frontmatter stripping, section filtering and heading offsets.

* **Parameters:**
  * **content** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **source** ([*SourceFile*](#eutaxis.instructions.models.SourceFile))
* **Return type:**
  [str](https://docs.python.org/3/builtins/stdtypes.html#str)

<a id="eutaxis.instructions.markdown.MarkdownAssembler.strip_frontmatter"></a>

#### strip_frontmatter(content)

Remove top-level YAML frontmatter from Markdown content.

* **Parameters:**
  **content** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  [str](https://docs.python.org/3/builtins/stdtypes.html#str)

<a id="eutaxis.instructions.markdown.MarkdownAssembler.parse_sections"></a>

#### parse_sections(content)

Parse Markdown into sections.

* **Parameters:**
  **content** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[*Section*](#eutaxis.instructions.models.Section)]

<a id="eutaxis.instructions.markdown.MarkdownAssembler.include_sections"></a>

#### include_sections(content, headings)

Include named sections and their nested subsections.

* **Parameters:**
  * **content** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **headings** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,*  *...* *]*)
* **Return type:**
  [str](https://docs.python.org/3/builtins/stdtypes.html#str)

<a id="eutaxis.instructions.markdown.MarkdownAssembler.exclude_sections"></a>

#### exclude_sections(content, headings)

Remove named sections and their nested subsections.

* **Parameters:**
  * **content** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **headings** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,*  *...* *]*)
* **Return type:**
  [str](https://docs.python.org/3/builtins/stdtypes.html#str)

<a id="eutaxis.instructions.markdown.MarkdownAssembler.selected_line_numbers"></a>

#### selected_line_numbers(content, source)

Return the lines of `content` that the section selection keeps.

The selection follows [`process()`](#eutaxis.instructions.markdown.MarkdownAssembler.process): frontmatter stripping, then
`sections`, then `exclude_sections`. Heading offsets and blank-line
trimming change no membership, so they are ignored.

* **Parameters:**
  * **content** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str)) – Full text of the source file, as read from disk.
  * **source** ([*SourceFile*](#eutaxis.instructions.models.SourceFile)) – Source entry whose selection applies.
* **Returns:**
  Line numbers of `content`, counted from 1, that the selection
  keeps; `None` when the entry selects no section, so that every
  line is kept.
* **Return type:**
  [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[int](https://docs.python.org/3/builtins/functions.html#int)] or None

### Examples

```pycon
>>> from pathlib import Path
>>> text = "# A\nkept\n# B\ndropped\n"
>>> source = SourceFile(path=Path("m.md"), sections=("A",))
>>> sorted(MarkdownAssembler().selected_line_numbers(text, source))
[1, 2]
```

<a id="eutaxis.instructions.markdown.MarkdownAssembler.apply_heading_offset"></a>

#### apply_heading_offset(content, offset)

Increase all Markdown heading levels by `offset`.

* **Parameters:**
  * **content** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **offset** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
* **Return type:**
  [str](https://docs.python.org/3/builtins/stdtypes.html#str)

<a id="module-eutaxis.instructions.rules"></a>

<a id="rule-parser"></a>

## Rule Parser

Parse instruction modules into rule records.

An instruction module states each rule under a label line, `**<label>**:`
alone at the start of a line. The rule block runs from its label line to the
nearer of two boundaries: the next label line and the next heading. Inside a
block, three kinds of line open a *part* of the rule:

- a line opening on `✓` opens a valid statement (part key `valid`);
- a line opening on `✗` opens an invalid statement (part key `invalid`);
- a line opening on an italic title, such as `*Why.*`, `*Exception*:` or
  `*Why the tiers.*`, opens a field.

A part runs until the next part opens or the block ends. Text between the
label line and the first part forms the `lead` part.

Field keys are normalized from the italic title by [`field_key()`](#eutaxis.instructions.rules.field_key). A
canonical marker absorbs its plural form and its titled variants, and every
other title is keyed by its slug. The canonical markers are listed in
[`CANONICAL_KEYS`](#eutaxis.instructions.rules.CANONICAL_KEYS).

The parser reads and writes no file. Its input is the text of one module, and
its output is a [`ParsedModule`](#eutaxis.instructions.rules.ParsedModule) holding the ordered blocks, the rule
records and the rejected label-shaped lines of that module. Line numbers start
at 1 on the first line of the text given, frontmatter included.

<a id="eutaxis.instructions.rules.LABEL_PATTERN"></a>

### eutaxis.instructions.rules.LABEL_PATTERN *= re.compile('^\\\\\*\\\\\*([a-z][a-z0-9-]\*)\\\\\*\\\\\*:\\\\s\*$', re.MULTILINE)*

Grammar of a label line. Shared with the rule index of the generator.

<a id="eutaxis.instructions.rules.FENCE_PATTERN"></a>

### eutaxis.instructions.rules.FENCE_PATTERN *= re.compile('^\\\\s\*(\`\`\`|~~~)')*

Opening or closing line of a fenced code block. Shared with the link rewriter.

<a id="eutaxis.instructions.rules.VALID_KEY"></a>

### eutaxis.instructions.rules.VALID_KEY *= 'valid'*

Part key of the `✓` statements.

<a id="eutaxis.instructions.rules.INVALID_KEY"></a>

### eutaxis.instructions.rules.INVALID_KEY *= 'invalid'*

Part key of the `✗` statements.

<a id="eutaxis.instructions.rules.LEAD_KEY"></a>

### eutaxis.instructions.rules.LEAD_KEY *= 'lead'*

Part key of the text between the label line and the first marked part.

<a id="eutaxis.instructions.rules.CANONICAL_KEYS"></a>

### eutaxis.instructions.rules.CANONICAL_KEYS *= ('why', 'exception', 'test', 'key', 'scope', 'note', 'warning', 'relation', 'how-to-apply')*

Field keys that absorb the plural forms and the titled variants of a marker.

<a id="eutaxis.instructions.rules.RulePart"></a>

### *class* eutaxis.instructions.rules.RulePart(key, title, text, start_line, end_line)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One part of a rule: a statement, a field, or the lead text.

* **Parameters:**
  * **key** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **title** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **text** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **start_line** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **end_line** ([*int*](https://docs.python.org/3/builtins/functions.html#int))

<a id="eutaxis.instructions.rules.RulePart.key"></a>

#### key *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

`valid`, `invalid`, `lead`, a canonical field
key, or the slug of a field title.

* **Type:**
  Normalized key

<a id="eutaxis.instructions.rules.RulePart.title"></a>

#### title *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Title as written in the module, without its closing punctuation
(`"Why the tiers"`); `"✓"` or `"✗"` for a statement; empty for the
lead text.

<a id="eutaxis.instructions.rules.RulePart.text"></a>

#### text *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Text of the part, marker line included, trailing blank lines removed.

<a id="eutaxis.instructions.rules.RulePart.start_line"></a>

#### start_line *: [int](https://docs.python.org/3/builtins/functions.html#int)*

First line of the part in the parsed text.

<a id="eutaxis.instructions.rules.RulePart.end_line"></a>

#### end_line *: [int](https://docs.python.org/3/builtins/functions.html#int)*

Last line of the part in the parsed text.

<a id="eutaxis.instructions.rules.Rule"></a>

### *class* eutaxis.instructions.rules.Rule(label, module, heading_path, parts, text, start_line, end_line)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One labelled rule of an instruction module.

* **Parameters:**
  * **label** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **module** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **heading_path** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,*  *...* *]*)
  * **parts** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*RulePart*](#eutaxis.instructions.rules.RulePart) *,*  *...* *]*)
  * **text** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **start_line** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **end_line** ([*int*](https://docs.python.org/3/builtins/functions.html#int))

<a id="eutaxis.instructions.rules.Rule.label"></a>

#### label *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Label of the rule, as written on its label line.

<a id="eutaxis.instructions.rules.Rule.module"></a>

#### module *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Name of the module that holds the rule.

<a id="eutaxis.instructions.rules.Rule.heading_path"></a>

#### heading_path *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]*

Texts of the headings enclosing the rule, outermost first.

<a id="eutaxis.instructions.rules.Rule.parts"></a>

#### parts *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[RulePart](#eutaxis.instructions.rules.RulePart), ...]*

Parts of the rule, in source order.

<a id="eutaxis.instructions.rules.Rule.text"></a>

#### text *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Raw text of the block, label line included.

<a id="eutaxis.instructions.rules.Rule.start_line"></a>

#### start_line *: [int](https://docs.python.org/3/builtins/functions.html#int)*

First line of the block in the parsed text.

<a id="eutaxis.instructions.rules.Rule.end_line"></a>

#### end_line *: [int](https://docs.python.org/3/builtins/functions.html#int)*

Last line of the block in the parsed text.

<a id="eutaxis.instructions.rules.Rule.valid"></a>

#### *property* valid *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]*

Texts of the `✓` statements.

<a id="eutaxis.instructions.rules.Rule.invalid"></a>

#### *property* invalid *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]*

Texts of the `✗` statements.

<a id="eutaxis.instructions.rules.Rule.fields"></a>

#### *property* fields *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[RulePart](#eutaxis.instructions.rules.RulePart), ...]]*

Fields of the rule, grouped by normalized key in source order.

<a id="eutaxis.instructions.rules.Rule.part_keys"></a>

#### *property* part_keys *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]*

Distinct part keys of the rule, in order of first occurrence.

<a id="eutaxis.instructions.rules.Rule.parts_for"></a>

#### parts_for(key)

Return every part whose key equals `key`, in source order.

* **Parameters:**
  **key** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[*RulePart*](#eutaxis.instructions.rules.RulePart), …]

<a id="eutaxis.instructions.rules.Rule.summary"></a>

#### *property* summary *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

First line of the first `✓` statement, without its marker.

A rule without a `✓` statement is summarized by the first line of
its first part. A rule without any part yields an empty string.

<a id="eutaxis.instructions.rules.RejectedLabel"></a>

### *class* eutaxis.instructions.rules.RejectedLabel(module, line_number, line, token, reason)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A line shaped as a label line whose token violates the label grammar.

A rejected line still ends the preceding rule block, so its text is not
attributed to the rule above it.

* **Parameters:**
  * **module** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **line_number** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **line** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **token** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **reason** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))

<a id="eutaxis.instructions.rules.RejectedLabel.module"></a>

#### module *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Name of the module that holds the line.

<a id="eutaxis.instructions.rules.RejectedLabel.line_number"></a>

#### line_number *: [int](https://docs.python.org/3/builtins/functions.html#int)*

Line number in the parsed text.

<a id="eutaxis.instructions.rules.RejectedLabel.line"></a>

#### line *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

The line as written.

<a id="eutaxis.instructions.rules.RejectedLabel.token"></a>

#### token *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Text between the bold markers.

<a id="eutaxis.instructions.rules.RejectedLabel.reason"></a>

#### reason *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Part of the grammar that the token violates.

<a id="eutaxis.instructions.rules.RejectedLabel.message"></a>

#### *property* message *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Diagnostic naming the line and the violated part of the grammar.

### Examples

```pycon
>>> parse_module("**3d-plots**:\n", module="m").rejected[0].message
"rejected label line '**3d-plots**:': a label must start with a lowercase letter"
```

<a id="eutaxis.instructions.rules.HeadingBlock"></a>

### *class* eutaxis.instructions.rules.HeadingBlock(level, text, line, start_line)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A Markdown heading outside fenced code.

* **Parameters:**
  * **level** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **text** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **line** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **start_line** ([*int*](https://docs.python.org/3/builtins/functions.html#int))

<a id="eutaxis.instructions.rules.HeadingBlock.level"></a>

#### level *: [int](https://docs.python.org/3/builtins/functions.html#int)*

<a id="eutaxis.instructions.rules.HeadingBlock.text"></a>

#### text *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.instructions.rules.HeadingBlock.line"></a>

#### line *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.instructions.rules.HeadingBlock.start_line"></a>

#### start_line *: [int](https://docs.python.org/3/builtins/functions.html#int)*

<a id="eutaxis.instructions.rules.TextBlock"></a>

### *class* eutaxis.instructions.rules.TextBlock(lines, start_line)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A run of lines that belongs to no rule block.

* **Parameters:**
  * **lines** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,*  *...* *]*)
  * **start_line** ([*int*](https://docs.python.org/3/builtins/functions.html#int))

<a id="eutaxis.instructions.rules.TextBlock.lines"></a>

#### lines *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]*

<a id="eutaxis.instructions.rules.TextBlock.start_line"></a>

#### start_line *: [int](https://docs.python.org/3/builtins/functions.html#int)*

<a id="eutaxis.instructions.rules.RuleBlock"></a>

### *class* eutaxis.instructions.rules.RuleBlock(rule)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The block of one rule.

* **Parameters:**
  **rule** ([*Rule*](#eutaxis.instructions.rules.Rule))

<a id="eutaxis.instructions.rules.RuleBlock.rule"></a>

#### rule *: [Rule](#eutaxis.instructions.rules.Rule)*

<a id="eutaxis.instructions.rules.Block"></a>

### eutaxis.instructions.rules.Block *= eutaxis.instructions.rules.HeadingBlock | eutaxis.instructions.rules.TextBlock | eutaxis.instructions.rules.RuleBlock*

One structural block of a module.

<a id="eutaxis.instructions.rules.ParsedModule"></a>

### *class* eutaxis.instructions.rules.ParsedModule(name, blocks, rejected)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Structure of one instruction module.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **blocks** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*HeadingBlock*](#eutaxis.instructions.rules.HeadingBlock) *|* [*TextBlock*](#eutaxis.instructions.rules.TextBlock) *|* [*RuleBlock*](#eutaxis.instructions.rules.RuleBlock) *,*  *...* *]*)
  * **rejected** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*RejectedLabel*](#eutaxis.instructions.rules.RejectedLabel) *,*  *...* *]*)

<a id="eutaxis.instructions.rules.ParsedModule.name"></a>

#### name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Name of the module.

<a id="eutaxis.instructions.rules.ParsedModule.blocks"></a>

#### blocks *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[HeadingBlock](#eutaxis.instructions.rules.HeadingBlock) | [TextBlock](#eutaxis.instructions.rules.TextBlock) | [RuleBlock](#eutaxis.instructions.rules.RuleBlock), ...]*

Headings, rule blocks and remaining text, in source order. The
frontmatter is excluded.

<a id="eutaxis.instructions.rules.ParsedModule.rejected"></a>

#### rejected *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[RejectedLabel](#eutaxis.instructions.rules.RejectedLabel), ...]*

Label-shaped lines that violate the label grammar.

<a id="eutaxis.instructions.rules.ParsedModule.rules"></a>

#### *property* rules *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Rule](#eutaxis.instructions.rules.Rule), ...]*

Rule records of the module, in source order.

<a id="eutaxis.instructions.rules.ParsedModule.rule"></a>

#### rule(label)

Return the first rule labelled `label`, if any.

* **Parameters:**
  **label** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  [*Rule*](#eutaxis.instructions.rules.Rule) | None

<a id="eutaxis.instructions.rules.field_key"></a>

### eutaxis.instructions.rules.field_key(title)

Normalize the title of a field into its part key.

A title whose words read `how to apply` maps to `how-to-apply`. A
title whose first word is a canonical marker, in singular or plural
form, maps to that marker, so titled variants share the key of their
marker. Every other title maps to the slug of its words.

* **Parameters:**
  **title** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str)) – Field title, with or without closing punctuation.
* **Returns:**
  Normalized key.
* **Return type:**
  [str](https://docs.python.org/3/builtins/stdtypes.html#str)

### Examples

```pycon
>>> field_key("Why the tiers")
'why'
>>> field_key("Exceptions")
'exception'
>>> field_key("How to apply")
'how-to-apply'
>>> field_key("Relation to the neighbouring rules")
'relation'
>>> field_key("Precedence among the three enumeration rules")
'precedence-among-the-three-enumeration-rules'
```

<a id="eutaxis.instructions.rules.parse_module"></a>

### eutaxis.instructions.rules.parse_module(text, \*, module)

Parse the text of one instruction module.

* **Parameters:**
  * **text** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str)) – Full text of the module, with or without YAML frontmatter.
  * **module** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str)) – Name recorded on every rule and rejected line.
* **Returns:**
  Blocks, rules and rejected label lines of the module.
* **Return type:**
  [ParsedModule](#eutaxis.instructions.rules.ParsedModule)

### Examples

```pycon
>>> parsed = parse_module(
...     "# Style\n\n**short-sentences**:\n\n✓ Keep sentences short.\n\n"
...     "*Exception.* Quoted text.\n",
...     module="style",
... )
>>> rule = parsed.rule("short-sentences")
>>> rule.heading_path, rule.part_keys
(('Style',), ('valid', 'exception'))
>>> rule.parts_for("exception")[0].text
'*Exception.* Quoted text.'
>>> rule.start_line, rule.end_line
(3, 7)
```

<a id="module-eutaxis.instructions.models"></a>

<a id="data-models"></a>

## Data Models

Data models for instruction-file assembly.

<a id="eutaxis.instructions.models.SourceFile"></a>

### *class* eutaxis.instructions.models.SourceFile(path, sections=(), exclude_sections=(), heading_offset=0, strip_frontmatter=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Markdown source file included in one or more instruction outputs.

* **Parameters:**
  * **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **sections** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,*  *...* *]*)
  * **exclude_sections** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,*  *...* *]*)
  * **heading_offset** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **strip_frontmatter** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool))

<a id="eutaxis.instructions.models.SourceFile.path"></a>

#### path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

<a id="eutaxis.instructions.models.SourceFile.sections"></a>

#### sections *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ()*

<a id="eutaxis.instructions.models.SourceFile.exclude_sections"></a>

#### exclude_sections *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ()*

<a id="eutaxis.instructions.models.SourceFile.heading_offset"></a>

#### heading_offset *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 0*

<a id="eutaxis.instructions.models.SourceFile.strip_frontmatter"></a>

#### strip_frontmatter *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= True*

<a id="eutaxis.instructions.models.TargetConfig"></a>

### *class* eutaxis.instructions.models.TargetConfig(path, header='', footer='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Output file target and surrounding literal content.

* **Parameters:**
  * **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **header** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **footer** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))

<a id="eutaxis.instructions.models.TargetConfig.path"></a>

#### path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

<a id="eutaxis.instructions.models.TargetConfig.header"></a>

#### header *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= ''*

<a id="eutaxis.instructions.models.TargetConfig.footer"></a>

#### footer *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= ''*

<a id="eutaxis.instructions.models.TaskModule"></a>

### *class* eutaxis.instructions.models.TaskModule(id, title, path, trigger, description=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A task-specific instruction module compiled to an Agent Skill artifact.

* **Parameters:**
  * **id** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **title** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **trigger** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **description** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* *None*)

<a id="eutaxis.instructions.models.TaskModule.id"></a>

#### id *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.instructions.models.TaskModule.title"></a>

#### title *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.instructions.models.TaskModule.path"></a>

#### path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

<a id="eutaxis.instructions.models.TaskModule.trigger"></a>

#### trigger *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.instructions.models.TaskModule.description"></a>

#### description *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

<a id="eutaxis.instructions.models.SkillLoadingMember"></a>

### *class* eutaxis.instructions.models.SkillLoadingMember(module, rules=(), include_entrypoint=True)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One Skill and the files selected from it for a loading unit.

* **Parameters:**
  * **module** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **rules** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,*  *...* *]*)
  * **include_entrypoint** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool))

<a id="eutaxis.instructions.models.SkillLoadingMember.module"></a>

#### module *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.instructions.models.SkillLoadingMember.rules"></a>

#### rules *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ()*

<a id="eutaxis.instructions.models.SkillLoadingMember.include_entrypoint"></a>

#### include_entrypoint *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= True*

<a id="eutaxis.instructions.models.SkillLoadingUnit"></a>

### *class* eutaxis.instructions.models.SkillLoadingUnit(name, max_bytes, members=(), includes=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A finite, budgeted set of Skill files loaded for one task.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **max_bytes** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **members** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*SkillLoadingMember*](#eutaxis.instructions.models.SkillLoadingMember) *,*  *...* *]*)
  * **includes** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,*  *...* *]*)

<a id="eutaxis.instructions.models.SkillLoadingUnit.name"></a>

#### name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.instructions.models.SkillLoadingUnit.max_bytes"></a>

#### max_bytes *: [int](https://docs.python.org/3/builtins/functions.html#int)*

<a id="eutaxis.instructions.models.SkillLoadingUnit.members"></a>

#### members *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[SkillLoadingMember](#eutaxis.instructions.models.SkillLoadingMember), ...]* *= ()*

<a id="eutaxis.instructions.models.SkillLoadingUnit.includes"></a>

#### includes *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ()*

<a id="eutaxis.instructions.models.InstructionChain"></a>

### *class* eutaxis.instructions.models.InstructionChain(name, agent, sources, max_bytes)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A generated global output and its project-level instruction files.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **agent** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **sources** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *,*  *...* *]*)
  * **max_bytes** ([*int*](https://docs.python.org/3/builtins/functions.html#int))

<a id="eutaxis.instructions.models.InstructionChain.name"></a>

#### name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.instructions.models.InstructionChain.agent"></a>

#### agent *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.instructions.models.InstructionChain.sources"></a>

#### sources *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path), ...]*

<a id="eutaxis.instructions.models.InstructionChain.max_bytes"></a>

#### max_bytes *: [int](https://docs.python.org/3/builtins/functions.html#int)*

<a id="eutaxis.instructions.models.ReferenceDoc"></a>

### *class* eutaxis.instructions.models.ReferenceDoc(id, title, local_path, github_url, trigger, description='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

An authoritative external reference doc with a local path and GitHub fallback.

* **Parameters:**
  * **id** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **title** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **local_path** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **github_url** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **trigger** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **description** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))

<a id="eutaxis.instructions.models.ReferenceDoc.id"></a>

#### id *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.instructions.models.ReferenceDoc.title"></a>

#### title *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.instructions.models.ReferenceDoc.local_path"></a>

#### local_path *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.instructions.models.ReferenceDoc.github_url"></a>

#### github_url *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.instructions.models.ReferenceDoc.trigger"></a>

#### trigger *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.instructions.models.ReferenceDoc.description"></a>

#### description *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= ''*

<a id="eutaxis.instructions.models.AgentConfig"></a>

### *class* eutaxis.instructions.models.AgentConfig(name, target, sources=<factory>, enabled=True, max_bytes=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One generated instruction output.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **target** ([*TargetConfig*](#eutaxis.instructions.models.TargetConfig))
  * **sources** ([*list*](https://docs.python.org/3/builtins/stdtypes.html#list) *[*[*SourceFile*](#eutaxis.instructions.models.SourceFile) *]*)
  * **enabled** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool))
  * **max_bytes** ([*int*](https://docs.python.org/3/builtins/functions.html#int) *|* *None*)

<a id="eutaxis.instructions.models.AgentConfig.name"></a>

#### name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.instructions.models.AgentConfig.target"></a>

#### target *: [TargetConfig](#eutaxis.instructions.models.TargetConfig)*

<a id="eutaxis.instructions.models.AgentConfig.sources"></a>

#### sources *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[SourceFile](#eutaxis.instructions.models.SourceFile)]*

<a id="eutaxis.instructions.models.AgentConfig.enabled"></a>

#### enabled *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= True*

<a id="eutaxis.instructions.models.AgentConfig.max_bytes"></a>

#### max_bytes *: [int](https://docs.python.org/3/builtins/functions.html#int) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

<a id="eutaxis.instructions.models.InstructionConfig"></a>

### *class* eutaxis.instructions.models.InstructionConfig(root, config_path, agents=<factory>, common_sources=<factory>, task_modules=<factory>, task_modules_heading='Task modules', task_modules_intro='', task_modules_router_enabled=True, skill_entrypoint_max_bytes=None, skill_loading_units=<factory>, instruction_chains=<factory>, reference_docs=<factory>, reference_docs_heading='Reference docs', reference_docs_intro='', rule_index_enabled=False, rule_index_heading='Rule index', rule_index_intro='', rule_index_pointer='', rule_index_target=None, default_max_bytes=None, strict_rule_labels=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Complete instruction assembly configuration.

* **Parameters:**
  * **root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **config_path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **agents** ([*list*](https://docs.python.org/3/builtins/stdtypes.html#list) *[*[*AgentConfig*](#eutaxis.instructions.models.AgentConfig) *]*)
  * **common_sources** ([*list*](https://docs.python.org/3/builtins/stdtypes.html#list) *[*[*SourceFile*](#eutaxis.instructions.models.SourceFile) *]*)
  * **task_modules** ([*list*](https://docs.python.org/3/builtins/stdtypes.html#list) *[*[*TaskModule*](#eutaxis.instructions.models.TaskModule) *]*)
  * **task_modules_heading** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **task_modules_intro** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **task_modules_router_enabled** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool))
  * **skill_entrypoint_max_bytes** ([*int*](https://docs.python.org/3/builtins/functions.html#int) *|* *None*)
  * **skill_loading_units** ([*list*](https://docs.python.org/3/builtins/stdtypes.html#list) *[*[*SkillLoadingUnit*](#eutaxis.instructions.models.SkillLoadingUnit) *]*)
  * **instruction_chains** ([*list*](https://docs.python.org/3/builtins/stdtypes.html#list) *[*[*InstructionChain*](#eutaxis.instructions.models.InstructionChain) *]*)
  * **reference_docs** ([*list*](https://docs.python.org/3/builtins/stdtypes.html#list) *[*[*ReferenceDoc*](#eutaxis.instructions.models.ReferenceDoc) *]*)
  * **reference_docs_heading** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **reference_docs_intro** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **rule_index_enabled** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool))
  * **rule_index_heading** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **rule_index_intro** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **rule_index_pointer** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **rule_index_target** ([*TargetConfig*](#eutaxis.instructions.models.TargetConfig) *|* *None*)
  * **default_max_bytes** ([*int*](https://docs.python.org/3/builtins/functions.html#int) *|* *None*)
  * **strict_rule_labels** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool))

<a id="eutaxis.instructions.models.InstructionConfig.root"></a>

#### root *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

<a id="eutaxis.instructions.models.InstructionConfig.config_path"></a>

#### config_path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

<a id="eutaxis.instructions.models.InstructionConfig.agents"></a>

#### agents *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[AgentConfig](#eutaxis.instructions.models.AgentConfig)]*

<a id="eutaxis.instructions.models.InstructionConfig.common_sources"></a>

#### common_sources *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[SourceFile](#eutaxis.instructions.models.SourceFile)]*

<a id="eutaxis.instructions.models.InstructionConfig.task_modules"></a>

#### task_modules *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[TaskModule](#eutaxis.instructions.models.TaskModule)]*

<a id="eutaxis.instructions.models.InstructionConfig.task_modules_heading"></a>

#### task_modules_heading *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'Task modules'*

<a id="eutaxis.instructions.models.InstructionConfig.task_modules_intro"></a>

#### task_modules_intro *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= ''*

<a id="eutaxis.instructions.models.InstructionConfig.task_modules_router_enabled"></a>

#### task_modules_router_enabled *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= True*

<a id="eutaxis.instructions.models.InstructionConfig.skill_entrypoint_max_bytes"></a>

#### skill_entrypoint_max_bytes *: [int](https://docs.python.org/3/builtins/functions.html#int) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

<a id="eutaxis.instructions.models.InstructionConfig.skill_loading_units"></a>

#### skill_loading_units *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[SkillLoadingUnit](#eutaxis.instructions.models.SkillLoadingUnit)]*

<a id="eutaxis.instructions.models.InstructionConfig.instruction_chains"></a>

#### instruction_chains *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[InstructionChain](#eutaxis.instructions.models.InstructionChain)]*

<a id="eutaxis.instructions.models.InstructionConfig.reference_docs"></a>

#### reference_docs *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[ReferenceDoc](#eutaxis.instructions.models.ReferenceDoc)]*

<a id="eutaxis.instructions.models.InstructionConfig.reference_docs_heading"></a>

#### reference_docs_heading *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'Reference docs'*

<a id="eutaxis.instructions.models.InstructionConfig.reference_docs_intro"></a>

#### reference_docs_intro *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= ''*

<a id="eutaxis.instructions.models.InstructionConfig.rule_index_enabled"></a>

#### rule_index_enabled *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= False*

<a id="eutaxis.instructions.models.InstructionConfig.rule_index_heading"></a>

#### rule_index_heading *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'Rule index'*

<a id="eutaxis.instructions.models.InstructionConfig.rule_index_intro"></a>

#### rule_index_intro *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= ''*

<a id="eutaxis.instructions.models.InstructionConfig.rule_index_pointer"></a>

#### rule_index_pointer *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= ''*

<a id="eutaxis.instructions.models.InstructionConfig.rule_index_target"></a>

#### rule_index_target *: [TargetConfig](#eutaxis.instructions.models.TargetConfig) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

<a id="eutaxis.instructions.models.InstructionConfig.default_max_bytes"></a>

#### default_max_bytes *: [int](https://docs.python.org/3/builtins/functions.html#int) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

<a id="eutaxis.instructions.models.InstructionConfig.strict_rule_labels"></a>

#### strict_rule_labels *: [bool](https://docs.python.org/3/builtins/functions.html#bool)* *= False*

<a id="eutaxis.instructions.models.InstructionConfig.budget_for"></a>

#### budget_for(agent)

Return the byte budget that applies to one agent, if any.

* **Parameters:**
  **agent** ([*AgentConfig*](#eutaxis.instructions.models.AgentConfig))
* **Return type:**
  [int](https://docs.python.org/3/builtins/functions.html#int) | None

<a id="eutaxis.instructions.models.InstructionConfig.enabled_agents"></a>

#### enabled_agents()

Return enabled agent outputs.

* **Return type:**
  [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[*AgentConfig*](#eutaxis.instructions.models.AgentConfig)]

<a id="eutaxis.instructions.models.InstructionConfig.get_agent"></a>

#### get_agent(name)

Return an agent output by name.

* **Parameters:**
  **name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
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

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A Markdown section with its heading and full body.

* **Parameters:**
  * **heading** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **level** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **content** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))

<a id="eutaxis.instructions.models.Section.heading"></a>

#### heading *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.instructions.models.Section.level"></a>

#### level *: [int](https://docs.python.org/3/builtins/functions.html#int)*

<a id="eutaxis.instructions.models.Section.content"></a>

#### content *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="module-eutaxis.instructions.exceptions"></a>

<a id="exceptions"></a>

## Exceptions

Exceptions for instruction-file assembly.

<a id="eutaxis.instructions.exceptions.InstructionError"></a>

### *exception* eutaxis.instructions.exceptions.InstructionError

Bases: [`Exception`](https://docs.python.org/3/builtins/exceptions.html#Exception)

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

<a id="eutaxis.instructions.exceptions.RejectedLabelError"></a>

### *exception* eutaxis.instructions.exceptions.RejectedLabelError(locations)

Bases: [`InstructionError`](#eutaxis.instructions.exceptions.InstructionError)

Raised under `strict_rule_labels` when a module holds a rejected label line.

* **Parameters:**
  **locations** ([*list*](https://docs.python.org/3/builtins/stdtypes.html#list) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *]*)
* **Return type:**
  None

<a id="eutaxis.instructions.exceptions.BudgetExceededError"></a>

### *exception* eutaxis.instructions.exceptions.BudgetExceededError(agent_name, size, limit)

Bases: [`InstructionError`](#eutaxis.instructions.exceptions.InstructionError)

Raised when a rendered output exceeds its configured byte budget.

* **Parameters:**
  * **agent_name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **size** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **limit** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
* **Return type:**
  None

<a id="eutaxis.instructions.exceptions.BudgetExceededError.exit_code"></a>

#### exit_code *= 2*

<a id="eutaxis.instructions.exceptions.InstructionChainBudgetExceededError"></a>

### *exception* eutaxis.instructions.exceptions.InstructionChainBudgetExceededError(chain_name, size, limit)

Bases: [`InstructionError`](#eutaxis.instructions.exceptions.InstructionError)

Raised when a global-plus-project instruction chain exceeds its budget.

* **Parameters:**
  * **chain_name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **size** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **limit** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
* **Return type:**
  None

<a id="eutaxis.instructions.exceptions.InstructionChainBudgetExceededError.exit_code"></a>

#### exit_code *= 2*
