<a id="commands"></a>

# Commands

Cross-agent command compilation: load command definitions, render them for each target agent, and install them into agent-specific surfaces.

<a id="module-eutaxis.commands.loader"></a>

<a id="loader"></a>

## Loader

Discover and parse command sources across discovery layers.

<a id="eutaxis.commands.loader.builtin_dir"></a>

### eutaxis.commands.loader.builtin_dir()

Return the directory holding built-in command sources.

* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

<a id="eutaxis.commands.loader.user_dir"></a>

### eutaxis.commands.loader.user_dir(home=None)

Return the user-level command source directory.

* **Parameters:**
  **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *|* *None*)
* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

<a id="eutaxis.commands.loader.project_dir"></a>

### eutaxis.commands.loader.project_dir(project_root)

Return the project-level command source directory.

* **Parameters:**
  **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

<a id="eutaxis.commands.loader.load_sources"></a>

### eutaxis.commands.loader.load_sources(\*, project_root=None, home=None)

Discover command sources across all layers.

Later layers override earlier ones by `name`. Discovery order is
built-in, user, project.

* **Parameters:**
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *|* *None*)
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *|* *None*)
* **Return type:**
  [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[*CommandSource*](#eutaxis.commands.models.CommandSource)]

<a id="eutaxis.commands.loader.load_from_instruction_config"></a>

### eutaxis.commands.loader.load_from_instruction_config(config_path)

Load Skill sources from an instruction-assembly configuration.

Each `task_modules` entry names a Markdown file whose frontmatter
must satisfy the Skill source schema (`name`, `description`,
`regime`, `failure-mode`, and `required-visibility` when
silent). Missing files or frontmatter raise `CommandRenderError`
with the offending path.

The discovery layer is recorded as `"config"` on each returned
source.

* **Parameters:**
  **config_path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[*CommandSource*](#eutaxis.commands.models.CommandSource)]

<a id="module-eutaxis.commands.registry"></a>

<a id="registry"></a>

## Registry

Persistent record of installed commands.

The registry is a JSON file at `<state_dir>/installed-commands.json`.
It is the source of truth for `uninstall` and `diff` and survives
across CLI invocations.

Robustness: writes are atomic (`os.replace` from a sibling `.tmp`
file) and serialised under a POSIX advisory file lock so concurrent
`eutaxis commands install` invocations cannot lose each other's
records. A corrupted registry surfaces as `RegistryCorruptedError`
with the path; the user can remove the file to rebuild from scratch.

<a id="eutaxis.commands.registry.RegistryCorruptedError"></a>

### *exception* eutaxis.commands.registry.RegistryCorruptedError

Bases: [`CommandError`](#eutaxis.commands.exceptions.CommandError)

Raised when the on-disk registry cannot be decoded as JSON.

<a id="eutaxis.commands.registry.Registry"></a>

### *class* eutaxis.commands.registry.Registry(state_dir)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

State for installed commands.

Each public mutating operation acquires an advisory file lock on a
sibling `.lock` file before reading, mutating, and writing the
JSON state. Writes go to a sibling `.tmp` and are committed with
`os.replace` so a crash between truncate and write cannot leave a
half-written file.

* **Parameters:**
  **state_dir** (*Path*)

<a id="eutaxis.commands.registry.Registry.load"></a>

#### load()

Return all install records currently on disk.

* **Return type:**
  [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[*InstallRecord*](#eutaxis.commands.models.InstallRecord)]

<a id="eutaxis.commands.registry.Registry.upsert"></a>

#### upsert(record)

Insert or replace the record for the same deployment target.

* **Parameters:**
  **record** ([*InstallRecord*](#eutaxis.commands.models.InstallRecord))
* **Return type:**
  None

<a id="eutaxis.commands.registry.Registry.remove"></a>

#### remove(\*, name, adapter, scope, path=None)

Drop the matching record and return it, if any.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **adapter** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **scope** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *|* *None*)
* **Return type:**
  [*InstallRecord*](#eutaxis.commands.models.InstallRecord) | None

<a id="eutaxis.commands.registry.Registry.find"></a>

#### find(\*, name, adapter, scope, path=None)

Return the matching record, if any.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **adapter** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **scope** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *|* *None*)
* **Return type:**
  [*InstallRecord*](#eutaxis.commands.models.InstallRecord) | None

<a id="eutaxis.commands.registry.utcnow_iso"></a>

### eutaxis.commands.registry.utcnow_iso()

Return the current UTC time as an ISO-8601 string.

* **Return type:**
  [str](https://docs.python.org/3/builtins/stdtypes.html#str)

<a id="eutaxis.commands.registry.default_state_dir"></a>

### eutaxis.commands.registry.default_state_dir(home=None)

Return the default user-level state directory.

* **Parameters:**
  **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *|* *None*)
* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

<a id="module-eutaxis.commands.rendering"></a>

<a id="rendering"></a>

## Rendering

Rendering: `CommandSource × AgentAdapter -> RenderedArtifact`.

The renderer writes no file. Its one read of the file system tests whether
the target of a relative link exists.

The renderer assembles a multi-file Agent Skill artifact:

- `SKILL.md` — entrypoint, YAML frontmatter + Markdown body.
- adapter-specific siblings (e.g. `agents/openai.yaml` for Codex).
- `rules/<label>.md` — one file per rule, when the source declares
  `disclosure: progressive` (see [`eutaxis.commands.disclosure`](#module-eutaxis.commands.disclosure)).
- `.eutaxis-owned.json` — sidecar manifest used by the installer to
  detect ownership and drive idempotent updates.

The relative links of `SKILL.md` and of each rule file are rewritten for
the installed location (see [`eutaxis.commands.links`](#module-eutaxis.commands.links)). A relative link
whose target does not exist is kept as written and reported in
`RenderedArtifact.warnings`.

Ownership is tracked **twice** for robustness:

1. `SKILL.md` frontmatter carries an `x-eutaxis-owned` hash key —
   readable without parsing JSON, survives partial sidecar loss.
2. `.eutaxis-owned.json` lists every file the installer owns and its
   per-file hash — survives manual edits to `SKILL.md` frontmatter.

The hash is computed over the rendered body plus the
non-ownership frontmatter dict (canonicalised) plus the sibling files
(sorted by relative path). The marker is injected last, so the hash is
stable regardless of the marker bytes themselves.

<a id="eutaxis.commands.rendering.check_failure_mode"></a>

### eutaxis.commands.rendering.check_failure_mode(source)

Refuse a source whose failure-mode forbids its invocation routes.

The compiler gate from the `failure-mode-as-source-field` ADR:

- `failure-mode: silent` cannot ship as a skill that admits model
  invocation (`"model"` in `invocation`). Model-judgment
  activation gives no visibility guarantee before the first
  irreversible action.
- `failure-mode: silent` with `required-visibility: pre-invocation`
  cannot ship as any skill: the rule must be visible *before*
  deciding which procedure applies, so it routes only to the
  always-on body.

* **Raises:**
  [**FailureModeError**](#eutaxis.commands.exceptions.FailureModeError) – On a forbidden combination, with the source path in the message.
* **Parameters:**
  **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
* **Return type:**
  None

<a id="eutaxis.commands.rendering.render_command"></a>

### eutaxis.commands.rendering.render_command(source, adapter, \*, project_root, home)

Render a command source for one adapter as a multi-file artifact.

* **Parameters:**
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
  * **adapter** (*AgentAdapter*)
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [*RenderedArtifact*](#eutaxis.commands.models.RenderedArtifact)

<a id="module-eutaxis.commands.disclosure"></a>

<a id="progressive-disclosure"></a>

## Progressive Disclosure

Progressive disclosure: split a skill body into an index and rule files.

A source whose frontmatter declares `disclosure: progressive` compiles to a
split skill. Its `SKILL.md` keeps the headings and every line outside a rule
block, and an index replaces each run of consecutive rule blocks. Each index
entry names the label, the first `✓` line of the rule, and a relative link to
`rules/<label>.md`. That file holds the whole rule block.

Therefore, every line of the source body lands in exactly one emitted file:
text outside rules stays in `SKILL.md`, and each rule block moves to its own
file. When a body holds no rule, it is returned unchanged.

The functions of this module are pure. The renderer adds the rule files to the
artifact as sibling files, so the content hash and the ownership sidecar cover
them together with the other files of the artifact.

<a id="eutaxis.commands.disclosure.DISCLOSURE_INLINE"></a>

### eutaxis.commands.disclosure.DISCLOSURE_INLINE *= 'inline'*

the whole module body forms the `SKILL.md` body.

* **Type:**
  Default mode

<a id="eutaxis.commands.disclosure.DISCLOSURE_PROGRESSIVE"></a>

### eutaxis.commands.disclosure.DISCLOSURE_PROGRESSIVE *= 'progressive'*

`SKILL.md` holds an index, each rule holds its own file.

* **Type:**
  Split mode

<a id="eutaxis.commands.disclosure.RULES_DIRNAME"></a>

### eutaxis.commands.disclosure.RULES_DIRNAME *= 'rules'*

Directory of the rule files, relative to the artifact root.

<a id="eutaxis.commands.disclosure.READING_NOTE"></a>

### eutaxis.commands.disclosure.READING_NOTE *= '> Each entry below links to the file of one rule. That file holds the whole rule: its ✓ and ✗ statements and every field, such as the exception, the test and the rationale. Read the file of a rule before applying or citing it.'*

Note emitted once, before the first index of a split `SKILL.md`.

<a id="eutaxis.commands.disclosure.INDEX_ENTRY_PATTERN"></a>

### eutaxis.commands.disclosure.INDEX_ENTRY_PATTERN *= re.compile('^- \\\\[\`(?P<label>[a-z][a-z0-9-]\*)\`\\\\]\\\\(rules/(?P=label)\\\\.md\\\\)')*

Grammar of one index entry, read back by the rule query.

<a id="eutaxis.commands.disclosure.DisclosedBody"></a>

### *class* eutaxis.commands.disclosure.DisclosedBody(entrypoint_body, rule_files)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of splitting one skill body.

* **Parameters:**
  * **entrypoint_body** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **rule_files** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*ArtifactFile*](#eutaxis.commands.models.ArtifactFile) *,*  *...* *]*)

<a id="eutaxis.commands.disclosure.DisclosedBody.entrypoint_body"></a>

#### entrypoint_body *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Body of `SKILL.md`.

<a id="eutaxis.commands.disclosure.DisclosedBody.rule_files"></a>

#### rule_files *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[ArtifactFile](#eutaxis.commands.models.ArtifactFile), ...]*

One file per rule, at `rules/<label>.md`, in source order.

<a id="eutaxis.commands.disclosure.rule_file_path"></a>

### eutaxis.commands.disclosure.rule_file_path(label)

Return the artifact-relative path of the file of one rule.

### Examples

```pycon
>>> rule_file_path("topic-first")
'rules/topic-first.md'
```

* **Parameters:**
  **label** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  [str](https://docs.python.org/3/builtins/stdtypes.html#str)

<a id="eutaxis.commands.disclosure.index_entry"></a>

### eutaxis.commands.disclosure.index_entry(rule)

Return the index entry of one rule.

### Examples

```pycon
>>> from eutaxis.instructions.rules import parse_module
>>> rule = parse_module("**short**:\n\n✓ Keep it short.\n", module="m").rules[0]
>>> index_entry(rule)
'- [`short`](rules/short.md): Keep it short.'
```

* **Parameters:**
  **rule** ([*Rule*](instructions.md#eutaxis.instructions.rules.Rule))
* **Return type:**
  [str](https://docs.python.org/3/builtins/stdtypes.html#str)

<a id="eutaxis.commands.disclosure.disclose"></a>

### eutaxis.commands.disclosure.disclose(body, \*, module)

Split a skill body into an index body and one file per rule.

* **Parameters:**
  * **body** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str)) – Rendered Markdown body of the skill, without frontmatter.
  * **module** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str)) – Name of the skill, used in error messages.
* **Returns:**
  Index body and rule files. A body without rules is returned as the
  index body unchanged, with no rule file.
* **Return type:**
  [DisclosedBody](#eutaxis.commands.disclosure.DisclosedBody)
* **Raises:**
  [**CommandRenderError**](#eutaxis.commands.exceptions.CommandRenderError) – When two rules of the body share a label, since both would be written
      to the same file.

### Examples

```pycon
>>> result = disclose(
...     "# Style\n\nIntro.\n\n**short**:\n\n✓ Keep it short.\n",
...     module="style",
... )
>>> [f.relative_path for f in result.rule_files]
['rules/short.md']
>>> print(result.entrypoint_body.splitlines()[-1])
- [`short`](rules/short.md): Keep it short.
```

<a id="module-eutaxis.commands.links"></a>

<a id="links"></a>

## Links

Rewrite the relative links of a compiled skill for its installed location.

A source module links to sibling modules and files by relative Markdown links,
such as `[the prose authoring workflow](prose-authoring-workflow.md)`. Once compiled, each task
module is installed as its own skill directory, so a link relative to the
source directory resolves nowhere. The renderer therefore rewrites the target
of each relative link in every emitted Markdown file:

- a target that is another source compiled from the same configuration
  becomes the relative path to the `SKILL.md` of that skill, from the
  emitting file: `../<name>/SKILL.md` from `SKILL.md`, and
  `../../<name>/SKILL.md` from `rules/<label>.md`;
- any other target that exists on disk becomes its absolute path;
- a target that names a file of the artifact itself, such as the
  `rules/<label>.md` entry of a split index, stays as written;
- a target that does not exist stays as written, and [`LinkResolver.missing()`](#eutaxis.commands.links.LinkResolver.missing)
  reports it.

The fragment of a target, such as `#^anchor`, is kept. Absolute URLs,
`mailto:` targets and other schemes, absolute paths, pure fragments, and
links inside code spans or fenced code stay untouched. The rewrite covers
inline links, images and link reference definitions.

The rewrite depends only on its inputs, and the existence test is injected,
so that two renders of the same sources produce the same bytes.

<a id="eutaxis.commands.links.ENTRYPOINT_LINK_NAME"></a>

### eutaxis.commands.links.ENTRYPOINT_LINK_NAME *= 'SKILL.md'*

File that a link to a sibling skill points to.

<a id="eutaxis.commands.links.Link"></a>

### *class* eutaxis.commands.links.Link(line_number, start, end, target, wrapped)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One link destination found in a Markdown text.

* **Parameters:**
  * **line_number** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **start** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **end** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **target** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **wrapped** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool))

<a id="eutaxis.commands.links.Link.line_number"></a>

#### line_number *: [int](https://docs.python.org/3/builtins/functions.html#int)*

Line of the link, counted from 1.

<a id="eutaxis.commands.links.Link.start"></a>

#### start *: [int](https://docs.python.org/3/builtins/functions.html#int)*

Offset of the destination in its line, angle brackets included.

<a id="eutaxis.commands.links.Link.end"></a>

#### end *: [int](https://docs.python.org/3/builtins/functions.html#int)*

Offset just past the destination in its line.

<a id="eutaxis.commands.links.Link.target"></a>

#### target *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Destination as written, without angle brackets.

<a id="eutaxis.commands.links.Link.wrapped"></a>

#### wrapped *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Whether the destination is written between angle brackets.

<a id="eutaxis.commands.links.iter_links"></a>

### eutaxis.commands.links.iter_links(text)

Yield the link destinations of `text` outside code.

Lines inside fenced code and characters inside code spans are skipped.

### Examples

```pycon
>>> [link.target for link in iter_links("[a](x.md) `[b](y.md)` ![c](<z w.png>)")]
['x.md', 'z w.png']
```

* **Parameters:**
  **text** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  [*Iterator*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[[*Link*](#eutaxis.commands.links.Link)]

<a id="eutaxis.commands.links.replace_links"></a>

### eutaxis.commands.links.replace_links(text, replace)

Return `text` with each link destination replaced by `replace`.

`replace` receives each [`Link`](#eutaxis.commands.links.Link) and returns the new destination,
without angle brackets, or `None` to keep the destination as written.
A new destination that holds a space, a parenthesis or an angle bracket is
written between angle brackets. Line endings are kept.

### Examples

```pycon
>>> replace_links("[a](x.md#f) [b](y.md)\n", lambda l: "z.md" if l.target == "y.md" else None)
'[a](x.md#f) [b](z.md)\n'
```

* **Parameters:**
  * **text** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **replace** ([*Callable*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable) *[* *[*[*Link*](#eutaxis.commands.links.Link) *]* *,* [*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* *None* *]*)
* **Return type:**
  [str](https://docs.python.org/3/builtins/stdtypes.html#str)

<a id="eutaxis.commands.links.is_relative_target"></a>

### eutaxis.commands.links.is_relative_target(target)

Return whether `target` names a path relative to its document.

### Examples

```pycon
>>> targets = ("a.md", "../b.md#x", "#x", "/a", "https://e.org", "mailto:a@b")
>>> [is_relative_target(target) for target in targets]
[True, True, False, False, False, False]
```

* **Parameters:**
  **target** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  [bool](https://docs.python.org/3/builtins/functions.html#bool)

<a id="eutaxis.commands.links.normalize_path"></a>

### eutaxis.commands.links.normalize_path(path)

Return the absolute, lexically normalized form of `path`.

Symbolic links are not followed, so the result does not depend on the
state of the file system.

* **Parameters:**
  **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

<a id="eutaxis.commands.links.MissingLink"></a>

### *class* eutaxis.commands.links.MissingLink(source_path, line_number, target, resolved)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A relative link of a source whose target does not exist.

* **Parameters:**
  * **source_path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **line_number** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **target** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **resolved** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))

<a id="eutaxis.commands.links.MissingLink.source_path"></a>

#### source_path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

<a id="eutaxis.commands.links.MissingLink.line_number"></a>

#### line_number *: [int](https://docs.python.org/3/builtins/functions.html#int)*

<a id="eutaxis.commands.links.MissingLink.target"></a>

#### target *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.links.MissingLink.resolved"></a>

#### resolved *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

<a id="eutaxis.commands.links.MissingLink.message"></a>

#### *property* message *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Diagnostic with the location of the link in its source.

<a id="eutaxis.commands.links.LinkResolver"></a>

### *class* eutaxis.commands.links.LinkResolver(source_dir, skills=<factory>, exists=<function Path.exists>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Resolve the relative links of one source for its compiled skill.

* **Parameters:**
  * **source_dir** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **skills** ([*Mapping*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) *[*[*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *,* [*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *]*)
  * **exists** ([*Callable*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable) *[* *[*[*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *]* *,* [*bool*](https://docs.python.org/3/builtins/functions.html#bool) *]*)

<a id="eutaxis.commands.links.LinkResolver.source_dir"></a>

#### source_dir *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

Directory against which the relative links of the source resolve.

<a id="eutaxis.commands.links.LinkResolver.skills"></a>

#### skills *: [Mapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Normalized source path of each sibling skill, mapped to its name.

<a id="eutaxis.commands.links.LinkResolver.exists"></a>

#### exists(\*, follow_symlinks=True)

Existence test of a resolved target.

<a id="eutaxis.commands.links.LinkResolver.resolve"></a>

#### resolve(target)

Return the normalized path that a relative `target` names.

* **Parameters:**
  **target** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

<a id="eutaxis.commands.links.LinkResolver.missing"></a>

#### missing(text, \*, source_path, first_line=1)

Return the relative links of `text` that resolve to no file.

* **Parameters:**
  * **text** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str)) – Body of the source, before any split.
  * **source_path** (*Path*) – Source file, quoted in each diagnostic.
  * **first_line** ([*int*](https://docs.python.org/3/builtins/functions.html#int)) – Line of the source file on which `text` starts.
* **Return type:**
  [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[*MissingLink*](#eutaxis.commands.links.MissingLink)]

<a id="eutaxis.commands.links.LinkResolver.rewrite"></a>

#### rewrite(text, \*, emitter, artifact_paths)

Rewrite the relative links of one emitted file.

* **Parameters:**
  * **text** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str)) – Content of the emitted Markdown file.
  * **emitter** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str)) – Path of that file relative to the artifact root, such as
    `"SKILL.md"` or `"rules/topic-first.md"`.
  * **artifact_paths** ([*frozenset*](https://docs.python.org/3/builtins/stdtypes.html#frozenset) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *]*) – Paths of every file of the artifact, relative to its root. A link
    to one of them stays as written.
* **Return type:**
  [str](https://docs.python.org/3/builtins/stdtypes.html#str)

### Examples

```pycon
>>> resolver = LinkResolver(
...     source_dir=Path("/src/tasks"),
...     skills={Path("/src/tasks/style.md"): "style"},
...     exists=lambda path: False,
... )
>>> resolver.rewrite(
...     "[s](style.md#^a) [r](rules/x.md)",
...     emitter="rules/y.md",
...     artifact_paths=frozenset({"rules/x.md"}),
... )
'[s](../../style/SKILL.md#^a) [r](rules/x.md)'
```

<a id="module-eutaxis.commands.templating"></a>

<a id="templating"></a>

## Templating

Tiny, fail-closed `{{ var }}` substitution.

The engine accepts dotted names (`action.template`) and rejects any
identifier not present in the supplied context. It does not implement
conditionals, loops, or filters. Anything beyond bare substitution
should be handled by the caller before invocation.

<a id="eutaxis.commands.templating.render"></a>

### eutaxis.commands.templating.render(template, context)

Substitute `{{ name }}` placeholders against `context`.

* **Parameters:**
  * **template** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str)) – Template string. Placeholders look like `{{ name }}` or
    `{{ ns.name }}`. Whitespace inside the braces is tolerated.
  * **context** ([*dict*](https://docs.python.org/3/builtins/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* *Any* *]*) – Variable context. Dotted names traverse nested mappings or
    attributes.
* **Returns:**
  The rendered string.
* **Return type:**
  [str](https://docs.python.org/3/builtins/stdtypes.html#str)
* **Raises:**
  [**TemplateError**](#eutaxis.commands.exceptions.TemplateError) – If a placeholder references an unknown name.

<a id="module-eutaxis.commands.installer"></a>

<a id="installer"></a>

## Installer

Install, uninstall, and diff rendered command artifacts on the filesystem.

The artifact is an Agent Skill directory (multi-file). Ownership is
detected via two mechanisms in priority order:

1. `.eutaxis-owned.json` sidecar inside the artifact directory — the
   source of truth for the file list and per-file hashes.
2. `x-eutaxis-owned` key inside `SKILL.md` frontmatter — fallback if
   the sidecar is missing (e.g. a user deleted it).

A directory that exists but matches neither check is treated as
user-owned and refused unless `force=True`.

<a id="eutaxis.commands.installer.InstallOutcome"></a>

### *class* eutaxis.commands.installer.InstallOutcome(name, adapter, scope, path, action, warnings=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of one install or uninstall operation.

`path` is the artifact **directory**.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **adapter** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **scope** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **action** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **warnings** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,*  *...* *]*)

<a id="eutaxis.commands.installer.InstallOutcome.name"></a>

#### name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.installer.InstallOutcome.adapter"></a>

#### adapter *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.installer.InstallOutcome.scope"></a>

#### scope *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.installer.InstallOutcome.path"></a>

#### path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

<a id="eutaxis.commands.installer.InstallOutcome.action"></a>

#### action *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.installer.InstallOutcome.warnings"></a>

#### warnings *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ()*

Warnings of the render, such as a link whose target does not exist.

<a id="eutaxis.commands.installer.install_command"></a>

### eutaxis.commands.installer.install_command(source, adapter, \*, scope, project_root, home, registry, force=False)

Render and write one skill artifact to its native location.

* **Parameters:**
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
  * **adapter** (*AgentAdapter*)
  * **scope** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **registry** ([*Registry*](#eutaxis.commands.registry.Registry))
  * **force** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool))
* **Return type:**
  [*InstallOutcome*](#eutaxis.commands.installer.InstallOutcome)

<a id="eutaxis.commands.installer.uninstall_command"></a>

### eutaxis.commands.installer.uninstall_command(\*, name, adapter, scope, project_root, home, registry, force=False)

Remove one installed artifact and drop its registry row.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **adapter** (*AgentAdapter*)
  * **scope** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **registry** ([*Registry*](#eutaxis.commands.registry.Registry))
  * **force** ([*bool*](https://docs.python.org/3/builtins/functions.html#bool))
* **Return type:**
  [*InstallOutcome*](#eutaxis.commands.installer.InstallOutcome)

<a id="eutaxis.commands.installer.diff_command"></a>

### eutaxis.commands.installer.diff_command(source, adapter, \*, scope, project_root, home)

Return rendered artifact, directory, and a unified diff vs disk.

The diff is computed over the `SKILL.md` entrypoint plus all
rendered sibling files (sorted by path). Missing files on disk are
treated as empty. A file that the ownership sidecar on disk lists but
the render no longer produces, such as the file of a deleted rule, is
reported as a removal.

* **Parameters:**
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
  * **adapter** (*AgentAdapter*)
  * **scope** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[*RenderedArtifact*](#eutaxis.commands.models.RenderedArtifact), [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]

<a id="eutaxis.commands.installer.is_eutaxis_owned"></a>

### eutaxis.commands.installer.is_eutaxis_owned(target_dir)

Return whether `target_dir` holds a skill artifact written by eutaxis.

A directory is eutaxis-owned when its ownership sidecar parses, or when
its `SKILL.md` frontmatter carries the `x-eutaxis-owned` marker. A
missing or empty directory is not an artifact and yields `False`.

* **Parameters:**
  **target_dir** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [bool](https://docs.python.org/3/builtins/functions.html#bool)

<a id="module-eutaxis.commands.synchronization"></a>

<a id="synchronization"></a>

## Synchronization

Plan and apply the complete config-registered Skill set.

<a id="eutaxis.commands.synchronization.SkillSyncManifest"></a>

### *class* eutaxis.commands.synchronization.SkillSyncManifest(state_dir, config_path)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Skill names recorded for one configuration, adapter, and scope.

* **Parameters:**
  * **state_dir** (*Path*)
  * **config_path** (*Path*)

<a id="eutaxis.commands.synchronization.SkillSyncManifest.managed_names"></a>

#### managed_names(\*, adapter, scope, project_root)

Return names recorded for one adapter and scope.

* **Parameters:**
  * **adapter** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **scope** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]

<a id="eutaxis.commands.synchronization.SkillSyncManifest.names_managed_by_other_configs"></a>

#### names_managed_by_other_configs(\*, adapter, scope, project_root)

Return names claimed by every other configuration manifest.

* **Parameters:**
  * **adapter** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **scope** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [frozenset](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]

<a id="eutaxis.commands.synchronization.SkillSyncManifest.update"></a>

#### update(\*, scope, project_root, names_by_adapter)

Atomically record the successful result for selected adapters.

* **Parameters:**
  * **scope** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **names_by_adapter** ([*Mapping*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* [*Collection*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Collection) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *]* *]*)
* **Return type:**
  None

<a id="eutaxis.commands.synchronization.SkillSyncManifest.locked"></a>

#### locked()

Serialize plans and writes across configuration manifests.

* **Return type:**
  [*Iterator*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterator)[None]

<a id="eutaxis.commands.synchronization.SkillSyncAction"></a>

### *class* eutaxis.commands.synchronization.SkillSyncAction(action, name, adapter, scope, path, source=None, warnings=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One planned change to an installed Skill.

* **Parameters:**
  * **action** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **adapter** (*AgentAdapter*)
  * **scope** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource) *|* *None*)
  * **warnings** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,*  *...* *]*)

<a id="eutaxis.commands.synchronization.SkillSyncAction.action"></a>

#### action *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.synchronization.SkillSyncAction.name"></a>

#### name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.synchronization.SkillSyncAction.adapter"></a>

#### adapter *: AgentAdapter*

<a id="eutaxis.commands.synchronization.SkillSyncAction.scope"></a>

#### scope *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.synchronization.SkillSyncAction.path"></a>

#### path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

<a id="eutaxis.commands.synchronization.SkillSyncAction.source"></a>

#### source *: [CommandSource](#eutaxis.commands.models.CommandSource) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

<a id="eutaxis.commands.synchronization.SkillSyncAction.warnings"></a>

#### warnings *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ()*

<a id="eutaxis.commands.synchronization.plan_skill_sync"></a>

### eutaxis.commands.synchronization.plan_skill_sync(sources, adapters, \*, scope, project_root, home, managed_names_by_adapter=None, protected_names_by_adapter=None)

Plan installs and removals without modifying installed Skills.

Render every configured source while building the plan. Any populated
target without an Eutaxis ownership marker blocks the complete plan. The
plan considers only names recorded by this configuration. A retired
name enters the plan only while its directory carries an Eutaxis marker.
Skills managed by other configurations cannot enter the removal set.

* **Parameters:**
  * **sources** ([*list*](https://docs.python.org/3/builtins/stdtypes.html#list) *[*[*CommandSource*](#eutaxis.commands.models.CommandSource) *]*)
  * **adapters** ([*list*](https://docs.python.org/3/builtins/stdtypes.html#list) *[**AgentAdapter* *]*)
  * **scope** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **managed_names_by_adapter** ([*Mapping*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* [*Collection*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Collection) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *]* *]*  *|* *None*)
  * **protected_names_by_adapter** ([*Mapping*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* [*Collection*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Collection) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *]* *]*  *|* *None*)
* **Return type:**
  [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[*SkillSyncAction*](#eutaxis.commands.synchronization.SkillSyncAction), …]

<a id="eutaxis.commands.synchronization.apply_skill_sync"></a>

### eutaxis.commands.synchronization.apply_skill_sync(actions, \*, project_root, home, registry)

Apply every planned Skill change and return the resulting states.

* **Parameters:**
  * **actions** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*SkillSyncAction*](#eutaxis.commands.synchronization.SkillSyncAction) *,*  *...* *]*)
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **registry** ([*Registry*](#eutaxis.commands.registry.Registry))
* **Return type:**
  [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[*SkillSyncAction*](#eutaxis.commands.synchronization.SkillSyncAction), …]

<a id="module-eutaxis.commands.skill_budgets"></a>

<a id="loading-budgets"></a>

## Loading Budgets

Measure Skill entrypoints and declared loading units.

<a id="eutaxis.commands.skill_budgets.SkillBudgetMeasurement"></a>

### *class* eutaxis.commands.skill_budgets.SkillBudgetMeasurement(kind, name, adapter, byte_size, byte_budget, files)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One measured Skill entrypoint or loading unit.

* **Parameters:**
  * **kind** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **adapter** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **byte_size** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **byte_budget** ([*int*](https://docs.python.org/3/builtins/functions.html#int) *|* *None*)
  * **files** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,*  *...* *]*)

<a id="eutaxis.commands.skill_budgets.SkillBudgetMeasurement.kind"></a>

#### kind *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.skill_budgets.SkillBudgetMeasurement.name"></a>

#### name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.skill_budgets.SkillBudgetMeasurement.adapter"></a>

#### adapter *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.skill_budgets.SkillBudgetMeasurement.byte_size"></a>

#### byte_size *: [int](https://docs.python.org/3/builtins/functions.html#int)*

<a id="eutaxis.commands.skill_budgets.SkillBudgetMeasurement.byte_budget"></a>

#### byte_budget *: [int](https://docs.python.org/3/builtins/functions.html#int) | [None](https://docs.python.org/3/builtins/constants.html#None)*

<a id="eutaxis.commands.skill_budgets.SkillBudgetMeasurement.files"></a>

#### files *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]*

<a id="eutaxis.commands.skill_budgets.SkillBudgetMeasurement.over_budget"></a>

#### *property* over_budget *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Return whether the measured size exceeds its configured budget.

<a id="eutaxis.commands.skill_budgets.measure_skill_budgets"></a>

### eutaxis.commands.skill_budgets.measure_skill_budgets(config, sources, adapter, \*, project_root, home)

Measure every rendered entrypoint and declared loading unit.

* **Parameters:**
  * **config** ([*InstructionConfig*](instructions.md#eutaxis.instructions.models.InstructionConfig))
  * **sources** ([*list*](https://docs.python.org/3/builtins/stdtypes.html#list) *[*[*CommandSource*](#eutaxis.commands.models.CommandSource) *]*)
  * **adapter** (*AgentAdapter*)
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[*SkillBudgetMeasurement*](#eutaxis.commands.skill_budgets.SkillBudgetMeasurement), …]

<a id="module-eutaxis.commands.models"></a>

<a id="data-models"></a>

## Data Models

Data containers for the commands subsystem.

A "command" is rendered as an **Agent Skill artifact**: a directory whose
canonical entrypoint is `SKILL.md`, optionally accompanied by
agent-specific sibling files (e.g. `agents/openai.yaml` for Codex). The
multi-file artifact model is needed because Codex skills require the
parent directory name to equal the `name` field, and Codex carries UI
metadata / invocation policy / tool dependencies in the sibling
`agents/openai.yaml` file rather than in `SKILL.md` frontmatter.

<a id="eutaxis.commands.models.ActionSpec"></a>

### *class* eutaxis.commands.models.ActionSpec(kind, template)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Optional shell-backed action carried by a command source.

* **Parameters:**
  * **kind** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **template** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))

<a id="eutaxis.commands.models.ActionSpec.kind"></a>

#### kind *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Action kind. Only `"shell"` is supported in v1.

<a id="eutaxis.commands.models.ActionSpec.template"></a>

#### template *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Templated command string with `{{ var }}` placeholders.

<a id="eutaxis.commands.models.TargetsSpec"></a>

### *class* eutaxis.commands.models.TargetsSpec(include=(), exclude=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Per-source allow/deny list of adapter names.

An empty `include` tuple means "all registered adapters".

* **Parameters:**
  * **include** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,*  *...* *]*)
  * **exclude** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,*  *...* *]*)

<a id="eutaxis.commands.models.TargetsSpec.include"></a>

#### include *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ()*

<a id="eutaxis.commands.models.TargetsSpec.exclude"></a>

#### exclude *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ()*

<a id="eutaxis.commands.models.TargetsSpec.admits"></a>

#### admits(adapter_name)

Return whether the lists let the adapter receive the artifact.

### Examples

```pycon
>>> TargetsSpec(exclude=("codex",)).admits("claude")
True
>>> TargetsSpec(include=("codex",)).admits("claude")
False
```

* **Parameters:**
  **adapter_name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  [bool](https://docs.python.org/3/builtins/functions.html#bool)

<a id="eutaxis.commands.models.SiblingSkill"></a>

### *class* eutaxis.commands.models.SiblingSkill(name, targets)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Another source compiled from the same configuration, as a link target.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **targets** ([*TargetsSpec*](#eutaxis.commands.models.TargetsSpec))

<a id="eutaxis.commands.models.SiblingSkill.name"></a>

#### name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Name of the skill, which is also the name of its directory.

<a id="eutaxis.commands.models.SiblingSkill.targets"></a>

#### targets *: [TargetsSpec](#eutaxis.commands.models.TargetsSpec)*

Adapters that receive the skill; a link to it from an adapter that
does not receive it falls back to the absolute source path.

<a id="eutaxis.commands.models.AdapterPassthrough"></a>

### *class* eutaxis.commands.models.AdapterPassthrough(frontmatter=<factory>, files=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Adapter-specific overrides declared in the source frontmatter.

The author may inject extra YAML keys into the rendered `SKILL.md`
frontmatter (`frontmatter`) and extra sibling files (`files`)
alongside the entrypoint.

* **Parameters:**
  * **frontmatter** ([*dict*](https://docs.python.org/3/builtins/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* [*object*](https://docs.python.org/3/builtins/functions.html#object) *]*)
  * **files** ([*dict*](https://docs.python.org/3/builtins/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* [*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *]*)

<a id="eutaxis.commands.models.AdapterPassthrough.frontmatter"></a>

#### frontmatter *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [object](https://docs.python.org/3/builtins/functions.html#object)]*

Extra keys merged into the rendered `SKILL.md` frontmatter.
Values are emitted verbatim by the YAML dumper.

<a id="eutaxis.commands.models.AdapterPassthrough.files"></a>

#### files *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Sibling file contents keyed by POSIX-style relative path
(e.g. `"agents/openai.yaml"`). Templated against the same context
as the body.

<a id="eutaxis.commands.models.CommandSource"></a>

### *class* eutaxis.commands.models.CommandSource(name, description, invocation, failure_mode, scope_default, targets, action, body, required_visibility=None, argument_hint='', adapters=<factory>, overrides=<factory>, disclosure='inline', source_path=PosixPath('.'), body_start_line=1, sibling_skills=<factory>, layer='builtin')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Parsed Markdown command source.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **description** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **invocation** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,*  *...* *]*)
  * **failure_mode** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **scope_default** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **targets** ([*TargetsSpec*](#eutaxis.commands.models.TargetsSpec))
  * **action** ([*ActionSpec*](#eutaxis.commands.models.ActionSpec) *|* *None*)
  * **body** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **required_visibility** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* *None*)
  * **argument_hint** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **adapters** ([*dict*](https://docs.python.org/3/builtins/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* [*AdapterPassthrough*](#eutaxis.commands.models.AdapterPassthrough) *]*)
  * **overrides** ([*dict*](https://docs.python.org/3/builtins/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* [*dict*](https://docs.python.org/3/builtins/stdtypes.html#dict) *]*)
  * **disclosure** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **source_path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **body_start_line** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **sibling_skills** ([*dict*](https://docs.python.org/3/builtins/stdtypes.html#dict) *[*[*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *,* [*SiblingSkill*](#eutaxis.commands.models.SiblingSkill) *]*)
  * **layer** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))

<a id="eutaxis.commands.models.CommandSource.name"></a>

#### name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Slug used for the artifact directory and the invocation symbol.

<a id="eutaxis.commands.models.CommandSource.description"></a>

#### description *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

One-line summary surfaced by `commands list` and the agent's
skill picker.

<a id="eutaxis.commands.models.CommandSource.invocation"></a>

#### invocation *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]*

`"user"` (user
invokes explicitly via `/<name>` on Claude or `$<name>` on
Codex) and `"model"` (the model picks the skill from its
description). At least one route is required. When `"model"` is
absent, Claude emits `disable-model-invocation: true` and Codex
emits `policy.allow_implicit_invocation: false`; when `"model"`
is present, both flags are omitted (the platform defaults permit
both routes).

* **Type:**
  Permitted invocation routes. Allowed members

<a id="eutaxis.commands.models.CommandSource.failure_mode"></a>

#### failure_mode *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Silent-failure classification. `"silent"` if violation produces
irreversible state mutation; `"visible"` if the defect is
reviewable. See [failure-mode-as-source-field] ADR for the author
checklist. The compiler refuses to emit a skill that admits model
invocation (`"model"` in `invocation`) from a `silent` source,
and a skill from a `silent` source whose `required_visibility`
is `pre-invocation`.

<a id="eutaxis.commands.models.CommandSource.scope_default"></a>

#### scope_default *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

`"user"` or `"project"`.

* **Type:**
  Default install scope

<a id="eutaxis.commands.models.CommandSource.targets"></a>

#### targets *: [TargetsSpec](#eutaxis.commands.models.TargetsSpec)*

Adapter allow/deny list.

<a id="eutaxis.commands.models.CommandSource.action"></a>

#### action *: [ActionSpec](#eutaxis.commands.models.ActionSpec) | [None](https://docs.python.org/3/builtins/constants.html#None)*

Optional shell-backed action.

<a id="eutaxis.commands.models.CommandSource.body"></a>

#### body *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Markdown body, with `{{ var }}` placeholders still present.

<a id="eutaxis.commands.models.CommandSource.required_visibility"></a>

#### required_visibility *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)* *= None*

Required for `silent` sources only. `"pre-invocation"` if the
rule must be visible before deciding which procedure applies;
`"pre-action"` if explicit invocation can load the rule before the
first irreversible action. Must be `None` for `visible`
sources.

<a id="eutaxis.commands.models.CommandSource.argument_hint"></a>

#### argument_hint *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= ''*

Optional `argument-hint` value (UX hint, e.g. `"[--all]"`).

<a id="eutaxis.commands.models.CommandSource.adapters"></a>

#### adapters *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [AdapterPassthrough](#eutaxis.commands.models.AdapterPassthrough)]*

Per-adapter frontmatter and sibling files. Keyed by adapter name.

<a id="eutaxis.commands.models.CommandSource.overrides"></a>

#### overrides *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)]*

Per-adapter overrides for first-class fields (only
`action.template` is honored today).

<a id="eutaxis.commands.models.CommandSource.disclosure"></a>

#### disclosure *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'inline'*

Layout of the compiled skill. `"inline"` emits the whole body in
`SKILL.md`; `"progressive"` emits an index of the rules in
`SKILL.md` and one file per rule under `rules/`. See
[`eutaxis.commands.disclosure`](#module-eutaxis.commands.disclosure).

<a id="eutaxis.commands.models.CommandSource.source_path"></a>

#### source_path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)* *= PosixPath('.')*

Path to the source Markdown file on disk.

<a id="eutaxis.commands.models.CommandSource.body_start_line"></a>

#### body_start_line *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 1*

Line of the source file on which `body` starts, used to locate
diagnostics in the authored file.

<a id="eutaxis.commands.models.CommandSource.sibling_skills"></a>

#### sibling_skills *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [SiblingSkill](#eutaxis.commands.models.SiblingSkill)]*

Sources compiled from the same configuration, keyed by normalized
source path. The renderer rewrites a relative link to one of them into a
link to its `SKILL.md`. Empty for a source discovered from a layered
directory.

<a id="eutaxis.commands.models.CommandSource.layer"></a>

#### layer *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'builtin'*

`"builtin"`, `"user"`, `"project"`, or
`"config"` (for sources loaded from an instruction-assembly
configuration rather than a layered directory).

* **Type:**
  Discovery layer

<a id="eutaxis.commands.models.ArtifactFile"></a>

### *class* eutaxis.commands.models.ArtifactFile(relative_path, content)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One file inside a rendered skill artifact directory.

`relative_path` is POSIX-style and relative to the artifact root
(e.g. `"SKILL.md"`, `"agents/openai.yaml"`,
`".eutaxis-owned.json"`).

* **Parameters:**
  * **relative_path** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **content** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))

<a id="eutaxis.commands.models.ArtifactFile.relative_path"></a>

#### relative_path *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.models.ArtifactFile.content"></a>

#### content *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.models.RenderedArtifact"></a>

### *class* eutaxis.commands.models.RenderedArtifact(name, adapter, files, content_hash, warnings=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A command source rendered for one adapter as a multi-file artifact.

Files always include the entrypoint `SKILL.md` (whose frontmatter
carries the `x-eutaxis-owned` hash) and the
`.eutaxis-owned.json` sidecar. Adapter-specific siblings (e.g.
`agents/openai.yaml`) may also be present.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **adapter** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **files** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*ArtifactFile*](#eutaxis.commands.models.ArtifactFile) *,*  *...* *]*)
  * **content_hash** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **warnings** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,*  *...* *]*)

<a id="eutaxis.commands.models.RenderedArtifact.name"></a>

#### name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.models.RenderedArtifact.adapter"></a>

#### adapter *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.models.RenderedArtifact.files"></a>

#### files *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[ArtifactFile](#eutaxis.commands.models.ArtifactFile), ...]*

<a id="eutaxis.commands.models.RenderedArtifact.content_hash"></a>

#### content_hash *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.models.RenderedArtifact.warnings"></a>

#### warnings *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]* *= ()*

Defects found while rendering, such as a relative link whose target
does not exist. They do not enter the content hash.

<a id="eutaxis.commands.models.InstallRecord"></a>

### *class* eutaxis.commands.models.InstallRecord(name, adapter, scope, path, content_hash, installed_at)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One row of the install manifest.

`path` is the artifact **directory**, not a single file.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **adapter** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **scope** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **content_hash** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **installed_at** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))

<a id="eutaxis.commands.models.InstallRecord.name"></a>

#### name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.models.InstallRecord.adapter"></a>

#### adapter *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.models.InstallRecord.scope"></a>

#### scope *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.models.InstallRecord.path"></a>

#### path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

<a id="eutaxis.commands.models.InstallRecord.content_hash"></a>

#### content_hash *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.commands.models.InstallRecord.installed_at"></a>

#### installed_at *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="module-eutaxis.commands.exceptions"></a>

<a id="exceptions"></a>

## Exceptions

Exceptions for the commands subsystem.

<a id="eutaxis.commands.exceptions.CommandError"></a>

### *exception* eutaxis.commands.exceptions.CommandError

Bases: [`Exception`](https://docs.python.org/3/builtins/exceptions.html#Exception)

Base exception for the commands subsystem.

<a id="eutaxis.commands.exceptions.CommandError.exit_code"></a>

#### exit_code *= 1*

<a id="eutaxis.commands.exceptions.CommandNotFoundError"></a>

### *exception* eutaxis.commands.exceptions.CommandNotFoundError

Bases: [`CommandError`](#eutaxis.commands.exceptions.CommandError)

Raised when a referenced command name is unknown.

<a id="eutaxis.commands.exceptions.CommandRenderError"></a>

### *exception* eutaxis.commands.exceptions.CommandRenderError

Bases: [`CommandError`](#eutaxis.commands.exceptions.CommandError)

Raised when a command source cannot be parsed or rendered.

<a id="eutaxis.commands.exceptions.TemplateError"></a>

### *exception* eutaxis.commands.exceptions.TemplateError

Bases: [`CommandError`](#eutaxis.commands.exceptions.CommandError)

Raised when a template references an unknown variable or is malformed.

<a id="eutaxis.commands.exceptions.OwnershipError"></a>

### *exception* eutaxis.commands.exceptions.OwnershipError

Bases: [`CommandError`](#eutaxis.commands.exceptions.CommandError)

Raised when an install/uninstall target is not eutaxis-owned.

<a id="eutaxis.commands.exceptions.OwnershipError.exit_code"></a>

#### exit_code *= 2*

<a id="eutaxis.commands.exceptions.FailureModeError"></a>

### *exception* eutaxis.commands.exceptions.FailureModeError

Bases: [`CommandError`](#eutaxis.commands.exceptions.CommandError)

Raised when a source's failure-mode classification forbids the target regime.

A `failure-mode: silent` source cannot ship as a `model-invoked` skill;
the model-judgment activation gate gives no visibility guarantee before the
first irreversible action. A `silent` source with
`required-visibility: pre-invocation` cannot ship as a `user-invoked`
skill either; it routes only to the always-on body. See the
`failure-mode-as-source-field` ADR.

<a id="eutaxis.commands.exceptions.FailureModeError.exit_code"></a>

#### exit_code *= 3*

<a id="agent-adapters"></a>

## Agent Adapters

Per-agent renderers that translate a `CommandSource` into the file layout and frontmatter expected by each target agent.

<a id="module-eutaxis.commands.adapters.claude"></a>

<a id="claude"></a>

### Claude

Claude Code adapter: compile a command source into a Claude skill.

Targets `~/.claude/skills/<name>/SKILL.md` (user scope) and
`<project>/.claude/skills/<name>/SKILL.md` (project scope).

Invocation translation:

- `"model" not in invocation` -> `disable-model-invocation: true`
  in the rendered frontmatter (documented use case for *task* skills
  with side effects whose timing must be controlled —
  `claude/skills.md`). User invocation via `/<name>` still works.
- `"model" in invocation` -> `disable-model-invocation` is omitted;
  Claude is free to pick the skill from its description, and user
  invocation via `/<name>` continues to work as well.

Claude has no analogue to Codex's sibling `agents/openai.yaml`: all
metadata (including `allowed-tools`, `argument-hint`) is folded
into `SKILL.md` frontmatter.

<a id="eutaxis.commands.adapters.claude.ClaudeCodeAdapter"></a>

### *class* eutaxis.commands.adapters.claude.ClaudeCodeAdapter(name='claude')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Compile a command source into a Claude skill directory.

* **Parameters:**
  **name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))

<a id="eutaxis.commands.adapters.claude.ClaudeCodeAdapter.name"></a>

#### name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'claude'*

<a id="eutaxis.commands.adapters.claude.ClaudeCodeAdapter.supports_scope"></a>

#### supports_scope(scope)

* **Parameters:**
  **scope** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  [bool](https://docs.python.org/3/builtins/functions.html#bool)

<a id="eutaxis.commands.adapters.claude.ClaudeCodeAdapter.artifact_dir"></a>

#### artifact_dir(command_name, scope, \*, home, project_root)

* **Parameters:**
  * **command_name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **scope** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

<a id="eutaxis.commands.adapters.claude.ClaudeCodeAdapter.skills_root"></a>

#### skills_root(scope, \*, home, project_root)

* **Parameters:**
  * **scope** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

<a id="eutaxis.commands.adapters.claude.ClaudeCodeAdapter.skill_frontmatter"></a>

#### skill_frontmatter(source, \*, rendered_body)

* **Parameters:**
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
  * **rendered_body** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [object](https://docs.python.org/3/builtins/functions.html#object)]

<a id="eutaxis.commands.adapters.claude.ClaudeCodeAdapter.sibling_files"></a>

#### sibling_files(source, \*, context)

* **Parameters:**
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
  * **context** ([*dict*](https://docs.python.org/3/builtins/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* [*object*](https://docs.python.org/3/builtins/functions.html#object) *]*)
* **Return type:**
  [*Iterable*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[[*ArtifactFile*](#eutaxis.commands.models.ArtifactFile)]

<a id="module-eutaxis.commands.adapters.codex"></a>

<a id="codex"></a>

### Codex

Codex adapter: compile a command source into a Codex skill.

Targets `$HOME/.agents/skills/<name>/SKILL.md` (user scope) and
`<project>/.agents/skills/<name>/SKILL.md` (project scope). Codex
requires the `name` field in `SKILL.md` to **equal the parent
directory name** (skills-comparison.md), so the installer always
mirrors the source `name` slug as the artifact directory name.

Codex-specific metadata — invocation policy, UI metadata, declared tool
dependencies — lives in the sibling `agents/openai.yaml` file
(codex/skills.md). Invocation translation:

- `"model" not in invocation` -> `policy.allow_implicit_invocation:
  false` in the derived `agents/openai.yaml`. Explicit user
  invocation via `$<name>` still works.
- `"model" in invocation` -> the `policy` block is not derived;
  Codex is free to pick the skill implicitly. Passthrough keys are still
  honoured if the author supplies them.

The `dependencies.tools` block declared via passthrough is *metadata
only, not a permission grant*; sandbox / approval policy still lives in
`~/.codex/config.toml` and is out of scope for the artifact.

The experimental `allowed-tools` field in `SKILL.md` is **not
emitted** by this adapter: the Agent Skills spec marks it experimental
on Codex and Codex documents pre-approval as host configuration, not
artifact metadata (skills-comparison.md:106).

<a id="eutaxis.commands.adapters.codex.CodexAdapter"></a>

### *class* eutaxis.commands.adapters.codex.CodexAdapter(name='codex')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Compile a command source into a Codex skill directory.

* **Parameters:**
  **name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))

<a id="eutaxis.commands.adapters.codex.CodexAdapter.name"></a>

#### name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)* *= 'codex'*

<a id="eutaxis.commands.adapters.codex.CodexAdapter.supports_scope"></a>

#### supports_scope(scope)

* **Parameters:**
  **scope** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  [bool](https://docs.python.org/3/builtins/functions.html#bool)

<a id="eutaxis.commands.adapters.codex.CodexAdapter.artifact_dir"></a>

#### artifact_dir(command_name, scope, \*, home, project_root)

* **Parameters:**
  * **command_name** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **scope** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

<a id="eutaxis.commands.adapters.codex.CodexAdapter.skills_root"></a>

#### skills_root(scope, \*, home, project_root)

* **Parameters:**
  * **scope** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

<a id="eutaxis.commands.adapters.codex.CodexAdapter.skill_frontmatter"></a>

#### skill_frontmatter(source, \*, rendered_body)

* **Parameters:**
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
  * **rendered_body** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [object](https://docs.python.org/3/builtins/functions.html#object)]

<a id="eutaxis.commands.adapters.codex.CodexAdapter.sibling_files"></a>

#### sibling_files(source, \*, context)

* **Parameters:**
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
  * **context** ([*dict*](https://docs.python.org/3/builtins/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* [*object*](https://docs.python.org/3/builtins/functions.html#object) *]*)
* **Return type:**
  [*Iterable*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[[*ArtifactFile*](#eutaxis.commands.models.ArtifactFile)]
