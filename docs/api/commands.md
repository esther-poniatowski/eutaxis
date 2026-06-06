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
  [list](https://docs.python.org/3/library/stdtypes.html#list)[[*CommandSource*](#eutaxis.commands.models.CommandSource)]

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
  [list](https://docs.python.org/3/library/stdtypes.html#list)[[*CommandSource*](#eutaxis.commands.models.CommandSource)]

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

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

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
  [list](https://docs.python.org/3/library/stdtypes.html#list)[[*InstallRecord*](#eutaxis.commands.models.InstallRecord)]

<a id="eutaxis.commands.registry.Registry.upsert"></a>

#### upsert(record)

Insert or replace the record matching (name, adapter, scope).

* **Parameters:**
  **record** ([*InstallRecord*](#eutaxis.commands.models.InstallRecord))
* **Return type:**
  None

<a id="eutaxis.commands.registry.Registry.remove"></a>

#### remove(\*, name, adapter, scope)

Drop the matching record and return it, if any.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **adapter** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **scope** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [*InstallRecord*](#eutaxis.commands.models.InstallRecord) | None

<a id="eutaxis.commands.registry.Registry.find"></a>

#### find(\*, name, adapter, scope)

Return the matching record, if any.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **adapter** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **scope** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [*InstallRecord*](#eutaxis.commands.models.InstallRecord) | None

<a id="eutaxis.commands.registry.utcnow_iso"></a>

### eutaxis.commands.registry.utcnow_iso()

Return the current UTC time as an ISO-8601 string.

* **Return type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

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

Pure rendering: `CommandSource × AgentAdapter -> RenderedArtifact`.

The renderer assembles a multi-file Agent Skill artifact:

- `SKILL.md` — entrypoint, YAML frontmatter + Markdown body.
- adapter-specific siblings (e.g. `agents/openai.yaml` for Codex).
- `.eutaxis-owned.json` — sidecar manifest used by the installer to
  detect ownership and drive idempotent updates.

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
  * **template** ([*str*](https://docs.python.org/3/library/stdtypes.html#str)) – Template string. Placeholders look like `{{ name }}` or
    `{{ ns.name }}`. Whitespace inside the braces is tolerated.
  * **context** ([*dict*](https://docs.python.org/3/library/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,* *Any* *]*) – Variable context. Dotted names traverse nested mappings or
    attributes.
* **Returns:**
  The rendered string.
* **Return type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)
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

### *class* eutaxis.commands.installer.InstallOutcome(name, adapter, scope, path, action)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Result of one install or uninstall operation.

`path` is the artifact **directory**.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **adapter** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **scope** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **action** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

<a id="eutaxis.commands.installer.InstallOutcome.name"></a>

#### name *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.commands.installer.InstallOutcome.adapter"></a>

#### adapter *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.commands.installer.InstallOutcome.scope"></a>

#### scope *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.commands.installer.InstallOutcome.path"></a>

#### path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

<a id="eutaxis.commands.installer.InstallOutcome.action"></a>

#### action *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.commands.installer.install_command"></a>

### eutaxis.commands.installer.install_command(source, adapter, \*, scope, project_root, home, registry, force=False)

Render and write one skill artifact to its native location.

* **Parameters:**
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
  * **adapter** (*AgentAdapter*)
  * **scope** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **registry** ([*Registry*](#eutaxis.commands.registry.Registry))
  * **force** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
* **Return type:**
  [*InstallOutcome*](#eutaxis.commands.installer.InstallOutcome)

<a id="eutaxis.commands.installer.uninstall_command"></a>

### eutaxis.commands.installer.uninstall_command(\*, name, adapter, scope, project_root, home, registry, force=False)

Remove one installed artifact and drop its registry row.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **adapter** (*AgentAdapter*)
  * **scope** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **registry** ([*Registry*](#eutaxis.commands.registry.Registry))
  * **force** ([*bool*](https://docs.python.org/3/library/functions.html#bool))
* **Return type:**
  [*InstallOutcome*](#eutaxis.commands.installer.InstallOutcome)

<a id="eutaxis.commands.installer.diff_command"></a>

### eutaxis.commands.installer.diff_command(source, adapter, \*, scope, project_root, home)

Return rendered artifact, directory, and a unified diff vs disk.

The diff is computed over the `SKILL.md` entrypoint plus all
rendered sibling files (sorted by path). Missing files on disk are
treated as empty.

* **Parameters:**
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
  * **adapter** (*AgentAdapter*)
  * **scope** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[*RenderedArtifact*](#eutaxis.commands.models.RenderedArtifact), [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [str](https://docs.python.org/3/library/stdtypes.html#str)]

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

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Optional shell-backed action carried by a command source.

* **Parameters:**
  * **kind** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **template** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

<a id="eutaxis.commands.models.ActionSpec.kind"></a>

#### kind *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

Action kind. Only `"shell"` is supported in v1.

<a id="eutaxis.commands.models.ActionSpec.template"></a>

#### template *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

Templated command string with `{{ var }}` placeholders.

<a id="eutaxis.commands.models.TargetsSpec"></a>

### *class* eutaxis.commands.models.TargetsSpec(include=(), exclude=())

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Per-source allow/deny list of adapter names.

An empty `include` tuple means "all registered adapters".

* **Parameters:**
  * **include** ([*tuple*](https://docs.python.org/3/library/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,*  *...* *]*)
  * **exclude** ([*tuple*](https://docs.python.org/3/library/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,*  *...* *]*)

<a id="eutaxis.commands.models.TargetsSpec.include"></a>

#### include *: [tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[str](https://docs.python.org/3/library/stdtypes.html#str), ...]* *= ()*

<a id="eutaxis.commands.models.TargetsSpec.exclude"></a>

#### exclude *: [tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[str](https://docs.python.org/3/library/stdtypes.html#str), ...]* *= ()*

<a id="eutaxis.commands.models.AdapterPassthrough"></a>

### *class* eutaxis.commands.models.AdapterPassthrough(frontmatter=<factory>, files=<factory>)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Adapter-specific overrides declared in the source frontmatter.

The author may inject extra YAML keys into the rendered `SKILL.md`
frontmatter (`frontmatter`) and extra sibling files (`files`)
alongside the entrypoint.

* **Parameters:**
  * **frontmatter** ([*dict*](https://docs.python.org/3/library/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,* [*object*](https://docs.python.org/3/library/functions.html#object) *]*)
  * **files** ([*dict*](https://docs.python.org/3/library/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,* [*str*](https://docs.python.org/3/library/stdtypes.html#str) *]*)

<a id="eutaxis.commands.models.AdapterPassthrough.frontmatter"></a>

#### frontmatter *: [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [object](https://docs.python.org/3/library/functions.html#object)]*

Extra keys merged into the rendered `SKILL.md` frontmatter.
Values are emitted verbatim by the YAML dumper.

<a id="eutaxis.commands.models.AdapterPassthrough.files"></a>

#### files *: [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [str](https://docs.python.org/3/library/stdtypes.html#str)]*

Sibling file contents keyed by POSIX-style relative path
(e.g. `"agents/openai.yaml"`). Templated against the same context
as the body.

<a id="eutaxis.commands.models.CommandSource"></a>

### *class* eutaxis.commands.models.CommandSource(name, description, invocation, failure_mode, scope_default, targets, action, body, required_visibility=None, argument_hint='', adapters=<factory>, overrides=<factory>, source_path=PosixPath('.'), layer='builtin')

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Parsed Markdown command source.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **description** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **invocation** ([*tuple*](https://docs.python.org/3/library/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,*  *...* *]*)
  * **failure_mode** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **scope_default** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **targets** ([*TargetsSpec*](#eutaxis.commands.models.TargetsSpec))
  * **action** ([*ActionSpec*](#eutaxis.commands.models.ActionSpec) *|* *None*)
  * **body** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **required_visibility** ([*str*](https://docs.python.org/3/library/stdtypes.html#str) *|* *None*)
  * **argument_hint** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **adapters** ([*dict*](https://docs.python.org/3/library/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,* [*AdapterPassthrough*](#eutaxis.commands.models.AdapterPassthrough) *]*)
  * **overrides** ([*dict*](https://docs.python.org/3/library/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,* [*dict*](https://docs.python.org/3/library/stdtypes.html#dict) *]*)
  * **source_path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **layer** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

<a id="eutaxis.commands.models.CommandSource.name"></a>

#### name *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

Slug used for the artifact directory and the invocation symbol.

<a id="eutaxis.commands.models.CommandSource.description"></a>

#### description *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

One-line summary surfaced by `commands list` and the agent's
skill picker.

<a id="eutaxis.commands.models.CommandSource.invocation"></a>

#### invocation *: [tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[str](https://docs.python.org/3/library/stdtypes.html#str), ...]*

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

#### failure_mode *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

Silent-failure classification. `"silent"` if violation produces
irreversible state mutation; `"visible"` if the defect is
reviewable. See [failure-mode-as-source-field] ADR for the author
checklist. The compiler refuses to emit a skill that admits model
invocation (`"model"` in `invocation`) from a `silent` source,
and a skill from a `silent` source whose `required_visibility`
is `pre-invocation`.

<a id="eutaxis.commands.models.CommandSource.scope_default"></a>

#### scope_default *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

`"user"` or `"project"`.

* **Type:**
  Default install scope

<a id="eutaxis.commands.models.CommandSource.targets"></a>

#### targets *: [TargetsSpec](#eutaxis.commands.models.TargetsSpec)*

Adapter allow/deny list.

<a id="eutaxis.commands.models.CommandSource.action"></a>

#### action *: [ActionSpec](#eutaxis.commands.models.ActionSpec) | [None](https://docs.python.org/3/library/constants.html#None)*

Optional shell-backed action.

<a id="eutaxis.commands.models.CommandSource.body"></a>

#### body *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

Markdown body, with `{{ var }}` placeholders still present.

<a id="eutaxis.commands.models.CommandSource.required_visibility"></a>

#### required_visibility *: [str](https://docs.python.org/3/library/stdtypes.html#str) | [None](https://docs.python.org/3/library/constants.html#None)* *= None*

Required for `silent` sources only. `"pre-invocation"` if the
rule must be visible before deciding which procedure applies;
`"pre-action"` if explicit invocation can load the rule before the
first irreversible action. Must be `None` for `visible`
sources.

<a id="eutaxis.commands.models.CommandSource.argument_hint"></a>

#### argument_hint *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= ''*

Optional `argument-hint` value (UX hint, e.g. `"[--all]"`).

<a id="eutaxis.commands.models.CommandSource.adapters"></a>

#### adapters *: [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [AdapterPassthrough](#eutaxis.commands.models.AdapterPassthrough)]*

Per-adapter frontmatter and sibling files. Keyed by adapter name.

<a id="eutaxis.commands.models.CommandSource.overrides"></a>

#### overrides *: [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [dict](https://docs.python.org/3/library/stdtypes.html#dict)]*

Per-adapter overrides for first-class fields (only
`action.template` is honored today).

<a id="eutaxis.commands.models.CommandSource.source_path"></a>

#### source_path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)* *= PosixPath('.')*

Path to the source Markdown file on disk.

<a id="eutaxis.commands.models.CommandSource.layer"></a>

#### layer *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= 'builtin'*

`"builtin"`, `"user"`, `"project"`, or
`"config"` (for sources loaded from an instruction-assembly
configuration rather than a layered directory).

* **Type:**
  Discovery layer

<a id="eutaxis.commands.models.ArtifactFile"></a>

### *class* eutaxis.commands.models.ArtifactFile(relative_path, content)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

One file inside a rendered skill artifact directory.

`relative_path` is POSIX-style and relative to the artifact root
(e.g. `"SKILL.md"`, `"agents/openai.yaml"`,
`".eutaxis-owned.json"`).

* **Parameters:**
  * **relative_path** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **content** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

<a id="eutaxis.commands.models.ArtifactFile.relative_path"></a>

#### relative_path *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.commands.models.ArtifactFile.content"></a>

#### content *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.commands.models.RenderedArtifact"></a>

### *class* eutaxis.commands.models.RenderedArtifact(name, adapter, files, content_hash)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

A command source rendered for one adapter as a multi-file artifact.

Files always include the entrypoint `SKILL.md` (whose frontmatter
carries the `x-eutaxis-owned` hash) and the
`.eutaxis-owned.json` sidecar. Adapter-specific siblings (e.g.
`agents/openai.yaml`) may also be present.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **adapter** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **files** ([*tuple*](https://docs.python.org/3/library/stdtypes.html#tuple) *[*[*ArtifactFile*](#eutaxis.commands.models.ArtifactFile) *,*  *...* *]*)
  * **content_hash** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

<a id="eutaxis.commands.models.RenderedArtifact.name"></a>

#### name *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.commands.models.RenderedArtifact.adapter"></a>

#### adapter *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.commands.models.RenderedArtifact.files"></a>

#### files *: [tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[ArtifactFile](#eutaxis.commands.models.ArtifactFile), ...]*

<a id="eutaxis.commands.models.RenderedArtifact.content_hash"></a>

#### content_hash *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.commands.models.InstallRecord"></a>

### *class* eutaxis.commands.models.InstallRecord(name, adapter, scope, path, content_hash, installed_at)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

One row of the install manifest.

`path` is the artifact **directory**, not a single file.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **adapter** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **scope** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **content_hash** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **installed_at** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

<a id="eutaxis.commands.models.InstallRecord.name"></a>

#### name *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.commands.models.InstallRecord.adapter"></a>

#### adapter *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.commands.models.InstallRecord.scope"></a>

#### scope *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.commands.models.InstallRecord.path"></a>

#### path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

<a id="eutaxis.commands.models.InstallRecord.content_hash"></a>

#### content_hash *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="eutaxis.commands.models.InstallRecord.installed_at"></a>

#### installed_at *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

<a id="module-eutaxis.commands.exceptions"></a>

<a id="exceptions"></a>

## Exceptions

Exceptions for the commands subsystem.

<a id="eutaxis.commands.exceptions.CommandError"></a>

### *exception* eutaxis.commands.exceptions.CommandError

Bases: [`Exception`](https://docs.python.org/3/library/exceptions.html#Exception)

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

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Compile a command source into a Claude skill directory.

* **Parameters:**
  **name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

<a id="eutaxis.commands.adapters.claude.ClaudeCodeAdapter.name"></a>

#### name *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= 'claude'*

<a id="eutaxis.commands.adapters.claude.ClaudeCodeAdapter.supports_scope"></a>

#### supports_scope(scope)

* **Parameters:**
  **scope** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [bool](https://docs.python.org/3/library/functions.html#bool)

<a id="eutaxis.commands.adapters.claude.ClaudeCodeAdapter.artifact_dir"></a>

#### artifact_dir(command_name, scope, \*, home, project_root)

* **Parameters:**
  * **command_name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **scope** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

<a id="eutaxis.commands.adapters.claude.ClaudeCodeAdapter.skill_frontmatter"></a>

#### skill_frontmatter(source, \*, rendered_body)

* **Parameters:**
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
  * **rendered_body** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [object](https://docs.python.org/3/library/functions.html#object)]

<a id="eutaxis.commands.adapters.claude.ClaudeCodeAdapter.sibling_files"></a>

#### sibling_files(source, \*, context)

* **Parameters:**
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
  * **context** ([*dict*](https://docs.python.org/3/library/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,* [*object*](https://docs.python.org/3/library/functions.html#object) *]*)
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

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Compile a command source into a Codex skill directory.

* **Parameters:**
  **name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

<a id="eutaxis.commands.adapters.codex.CodexAdapter.name"></a>

#### name *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= 'codex'*

<a id="eutaxis.commands.adapters.codex.CodexAdapter.supports_scope"></a>

#### supports_scope(scope)

* **Parameters:**
  **scope** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [bool](https://docs.python.org/3/library/functions.html#bool)

<a id="eutaxis.commands.adapters.codex.CodexAdapter.artifact_dir"></a>

#### artifact_dir(command_name, scope, \*, home, project_root)

* **Parameters:**
  * **command_name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **scope** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

<a id="eutaxis.commands.adapters.codex.CodexAdapter.skill_frontmatter"></a>

#### skill_frontmatter(source, \*, rendered_body)

* **Parameters:**
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
  * **rendered_body** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [object](https://docs.python.org/3/library/functions.html#object)]

<a id="eutaxis.commands.adapters.codex.CodexAdapter.sibling_files"></a>

#### sibling_files(source, \*, context)

* **Parameters:**
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
  * **context** ([*dict*](https://docs.python.org/3/library/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,* [*object*](https://docs.python.org/3/library/functions.html#object) *]*)
* **Return type:**
  [*Iterable*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[[*ArtifactFile*](#eutaxis.commands.models.ArtifactFile)]
