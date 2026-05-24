# Commands

Cross-agent command compilation: load command definitions, render them for each target agent, and install them into agent-specific surfaces.

## Loader

Discover and parse command sources across discovery layers.

### eutaxis.commands.loader.builtin_dir()

Return the directory holding built-in command sources.

* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### eutaxis.commands.loader.user_dir(home=None)

Return the user-level command source directory.

* **Parameters:**
  **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *|* *None*)
* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### eutaxis.commands.loader.project_dir(project_root)

Return the project-level command source directory.

* **Parameters:**
  **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### eutaxis.commands.loader.load_sources(, project_root=None, home=None)

Discover command sources across all layers.

Later layers override earlier ones by `name`. Discovery order is
built-in, user, project.

* **Parameters:**
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *|* *None*)
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *|* *None*)
* **Return type:**
  [list](https://docs.python.org/3/library/stdtypes.html#list)[[*CommandSource*](#eutaxis.commands.models.CommandSource)]

## Registry

Persistent record of installed commands.

The registry is a JSON file at `<state_dir>/installed-commands.json`.
It is the source of truth for `uninstall` and `diff` and survives
across CLI invocations.

Robustness: writes are atomic (`os.replace` from a sibling `.tmp`
file) and serialised under a POSIX advisory file lock so concurrent
`eutaxis commands install` invocations cannot lose each other’s
records. A corrupted registry surfaces as `RegistryCorruptedError`
with the path; the user can remove the file to rebuild from scratch.

### *exception* eutaxis.commands.registry.RegistryCorruptedError

Bases: [`CommandError`](#eutaxis.commands.exceptions.CommandError)

Raised when the on-disk registry cannot be decoded as JSON.

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

#### load()

Return all install records currently on disk.

* **Return type:**
  [list](https://docs.python.org/3/library/stdtypes.html#list)[[*InstallRecord*](#eutaxis.commands.models.InstallRecord)]

#### upsert(record)

Insert or replace the record matching (name, adapter, scope).

* **Parameters:**
  **record** ([*InstallRecord*](#eutaxis.commands.models.InstallRecord))
* **Return type:**
  None

#### remove(, name, adapter, scope)

Drop the matching record and return it, if any.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **adapter** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **scope** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [*InstallRecord*](#eutaxis.commands.models.InstallRecord) | None

#### find(, name, adapter, scope)

Return the matching record, if any.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **adapter** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **scope** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [*InstallRecord*](#eutaxis.commands.models.InstallRecord) | None

### eutaxis.commands.registry.utcnow_iso()

Return the current UTC time as an ISO-8601 string.

* **Return type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

### eutaxis.commands.registry.default_state_dir(home=None)

Return the default user-level state directory.

* **Parameters:**
  **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *|* *None*)
* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

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

### eutaxis.commands.rendering.render_command(source, adapter, , project_root, home)

Render a command source for one adapter as a multi-file artifact.

* **Parameters:**
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
  * **adapter** (*AgentAdapter*)
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [*RenderedArtifact*](#eutaxis.commands.models.RenderedArtifact)

## Templating

Tiny, fail-closed `{{ var }}` substitution.

The engine accepts dotted names (`action.template`) and rejects any
identifier not present in the supplied context. It does not implement
conditionals, loops, or filters. Anything beyond bare substitution
should be handled by the caller before invocation.

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

#### name *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### adapter *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### scope *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

#### action *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

### eutaxis.commands.installer.install_command(source, adapter, , scope, project_root, home, registry, force=False)

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

### eutaxis.commands.installer.uninstall_command(, name, adapter, scope, project_root, home, registry, force=False)

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

### eutaxis.commands.installer.diff_command(source, adapter, , scope, project_root, home)

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

## Data Models

Data containers for the commands subsystem.

A “command” is rendered as an **Agent Skill artifact**: a directory whose
canonical entrypoint is `SKILL.md`, optionally accompanied by
agent-specific sibling files (e.g. `agents/openai.yaml` for Codex). The
multi-file artifact model is needed because Codex skills require the
parent directory name to equal the `name` field, and Codex carries UI
metadata / invocation policy / tool dependencies in the sibling
`agents/openai.yaml` file rather than in `SKILL.md` frontmatter.

### *class* eutaxis.commands.models.ActionSpec(kind, template)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Optional shell-backed action carried by a command source.

* **Parameters:**
  * **kind** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **template** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

#### kind

Action kind. Only `"shell"` is supported in v1.

* **Type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

#### template

Templated command string with `{{ var }}` placeholders.

* **Type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

#### kind *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### template *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

### *class* eutaxis.commands.models.TargetsSpec(include=(), exclude=())

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Per-source allow/deny list of adapter names.

An empty `include` tuple means “all registered adapters”.

* **Parameters:**
  * **include** ([*tuple*](https://docs.python.org/3/library/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,*  *...* *]*)
  * **exclude** ([*tuple*](https://docs.python.org/3/library/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,*  *...* *]*)

#### include *: [tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[str](https://docs.python.org/3/library/stdtypes.html#str), ...]* *= ()*

#### exclude *: [tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[str](https://docs.python.org/3/library/stdtypes.html#str), ...]* *= ()*

### *class* eutaxis.commands.models.AdapterPassthrough(frontmatter=<factory>, files=<factory>)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Adapter-specific overrides declared in the source frontmatter.

The author may inject extra YAML keys into the rendered `SKILL.md`
frontmatter (`frontmatter`) and extra sibling files (`files`)
alongside the entrypoint.

* **Parameters:**
  * **frontmatter** ([*dict*](https://docs.python.org/3/library/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,* [*object*](https://docs.python.org/3/library/functions.html#object) *]*)
  * **files** ([*dict*](https://docs.python.org/3/library/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,* [*str*](https://docs.python.org/3/library/stdtypes.html#str) *]*)

#### frontmatter

Extra keys merged into the rendered `SKILL.md` frontmatter.
Values are emitted verbatim by the YAML dumper.

* **Type:**
  [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [object](https://docs.python.org/3/library/functions.html#object)]

#### files

Sibling file contents keyed by POSIX-style relative path
(e.g. `"agents/openai.yaml"`). Templated against the same
context as the body.

* **Type:**
  [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [str](https://docs.python.org/3/library/stdtypes.html#str)]

#### frontmatter *: [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [object](https://docs.python.org/3/library/functions.html#object)]*

#### files *: [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [str](https://docs.python.org/3/library/stdtypes.html#str)]*

### *class* eutaxis.commands.models.CommandSource(name, description, regime, scope_default, targets, action, body, argument_hint='', adapters=<factory>, overrides=<factory>, source_path=PosixPath('.'), layer='builtin')

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Parsed Markdown command source.

* **Parameters:**
  * **name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **description** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **regime** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **scope_default** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **targets** ([*TargetsSpec*](#eutaxis.commands.models.TargetsSpec))
  * **action** ([*ActionSpec*](#eutaxis.commands.models.ActionSpec) *|* *None*)
  * **body** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **argument_hint** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **adapters** ([*dict*](https://docs.python.org/3/library/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,* [*AdapterPassthrough*](#eutaxis.commands.models.AdapterPassthrough) *]*)
  * **overrides** ([*dict*](https://docs.python.org/3/library/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,* [*dict*](https://docs.python.org/3/library/stdtypes.html#dict) *]*)
  * **source_path** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **layer** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

#### name

Slug used for the artifact directory and the invocation symbol.

* **Type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

#### description

One-line summary surfaced by `commands list` and the agent’s
skill picker.

* **Type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

#### regime

Activation regime; only `"user-invoked"` is supported in v1.
Maps to `disable-model-invocation: true` on Claude and to
`policy.allow_implicit_invocation: false` on Codex.

* **Type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

#### scope_default

Default install scope: `"user"` or `"project"`.

* **Type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

#### targets

Adapter allow/deny list.

* **Type:**
  [TargetsSpec](#eutaxis.commands.models.TargetsSpec)

#### action

Optional shell-backed action.

* **Type:**
  [ActionSpec](#eutaxis.commands.models.ActionSpec) | None

#### argument_hint

Optional `argument-hint` value (UX hint, e.g. `"[--all]"`).

* **Type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

#### body

Markdown body, with `{{ var }}` placeholders still present.

* **Type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

#### adapters

Per-adapter frontmatter and sibling files. Keyed by adapter
name.

* **Type:**
  [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [AdapterPassthrough](#eutaxis.commands.models.AdapterPassthrough)]

#### overrides

Per-adapter overrides for first-class fields (only
`action.template` is honored today).

* **Type:**
  [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [dict](https://docs.python.org/3/library/stdtypes.html#dict)]

#### source_path

Path to the source Markdown file on disk.

* **Type:**
  Path

#### layer

Discovery layer: `"builtin"`, `"user"`, or `"project"`.

* **Type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

#### name *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### description *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### regime *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### scope_default *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### targets *: [TargetsSpec](#eutaxis.commands.models.TargetsSpec)*

#### action *: [ActionSpec](#eutaxis.commands.models.ActionSpec) | [None](https://docs.python.org/3/library/constants.html#None)*

#### body *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### argument_hint *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= ''*

#### adapters *: [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [AdapterPassthrough](#eutaxis.commands.models.AdapterPassthrough)]*

#### overrides *: [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [dict](https://docs.python.org/3/library/stdtypes.html#dict)]*

#### source_path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)* *= PosixPath('.')*

#### layer *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= 'builtin'*

### *class* eutaxis.commands.models.ArtifactFile(relative_path, content)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

One file inside a rendered skill artifact directory.

`relative_path` is POSIX-style and relative to the artifact root
(e.g. `"SKILL.md"`, `"agents/openai.yaml"`,
`".eutaxis-owned.json"`).

* **Parameters:**
  * **relative_path** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **content** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

#### relative_path *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### content *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

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

#### name *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### adapter *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### files *: [tuple](https://docs.python.org/3/library/stdtypes.html#tuple)[[ArtifactFile](#eutaxis.commands.models.ArtifactFile), ...]*

#### content_hash *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

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

#### name *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### adapter *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### scope *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### path *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)*

#### content_hash *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

#### installed_at *: [str](https://docs.python.org/3/library/stdtypes.html#str)*

## Exceptions

Exceptions for the commands subsystem.

### *exception* eutaxis.commands.exceptions.CommandError

Bases: [`Exception`](https://docs.python.org/3/library/exceptions.html#Exception)

Base exception for the commands subsystem.

#### exit_code *= 1*

### *exception* eutaxis.commands.exceptions.CommandNotFoundError

Bases: [`CommandError`](#eutaxis.commands.exceptions.CommandError)

Raised when a referenced command name is unknown.

### *exception* eutaxis.commands.exceptions.CommandRenderError

Bases: [`CommandError`](#eutaxis.commands.exceptions.CommandError)

Raised when a command source cannot be parsed or rendered.

### *exception* eutaxis.commands.exceptions.TemplateError

Bases: [`CommandError`](#eutaxis.commands.exceptions.CommandError)

Raised when a template references an unknown variable or is malformed.

### *exception* eutaxis.commands.exceptions.OwnershipError

Bases: [`CommandError`](#eutaxis.commands.exceptions.CommandError)

Raised when an install/uninstall target is not eutaxis-owned.

#### exit_code *= 2*

## Agent Adapters

### Claude

Claude Code adapter: compile a command source into a Claude skill.

Targets `~/.claude/skills/<name>/SKILL.md` (user scope) and
`<project>/.claude/skills/<name>/SKILL.md` (project scope). The
`regime: user-invoked` declared in the source maps to
`disable-model-invocation: true` in the rendered frontmatter
(documented use case for *task* skills with side effects whose timing
must be controlled — claude/skills.md).

Claude has no analogue to Codex’s sibling `agents/openai.yaml`: all
metadata (including `allowed-tools`, `argument-hint`) is folded
into `SKILL.md` frontmatter.

### *class* eutaxis.commands.adapters.claude.ClaudeCodeAdapter(name='claude')

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Compile a command source into a Claude skill directory.

* **Parameters:**
  **name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

#### name *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= 'claude'*

#### supports_scope(scope)

* **Parameters:**
  **scope** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [bool](https://docs.python.org/3/library/functions.html#bool)

#### artifact_dir(command_name, scope, , home, project_root)

* **Parameters:**
  * **command_name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **scope** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

#### skill_frontmatter(source, , rendered_body)

* **Parameters:**
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
  * **rendered_body** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [object](https://docs.python.org/3/library/functions.html#object)]

#### sibling_files(source, , context)

* **Parameters:**
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
  * **context** ([*dict*](https://docs.python.org/3/library/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,* [*object*](https://docs.python.org/3/library/functions.html#object) *]*)
* **Return type:**
  [*Iterable*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[[*ArtifactFile*](#eutaxis.commands.models.ArtifactFile)]

### Codex

Codex adapter: compile a command source into a Codex skill.

Targets `$HOME/.agents/skills/<name>/SKILL.md` (user scope) and
`<project>/.agents/skills/<name>/SKILL.md` (project scope). Codex
requires the `name` field in `SKILL.md` to **equal the parent
directory name** (skills-comparison.md), so the installer always
mirrors the source `name` slug as the artifact directory name.

Codex-specific metadata — invocation policy, UI metadata, declared tool
dependencies — lives in the sibling `agents/openai.yaml` file
(codex/skills.md). The `regime: user-invoked` declared in the source
maps to `policy.allow_implicit_invocation: false` in that sibling.
The `dependencies.tools` block declared via passthrough is *metadata
only, not a permission grant*; sandbox / approval policy still lives in
`~/.codex/config.toml` and is out of scope for the artifact.

The experimental `allowed-tools` field in `SKILL.md` is **not
emitted** by this adapter: the Agent Skills spec marks it experimental
on Codex and Codex documents pre-approval as host configuration, not
artifact metadata (skills-comparison.md:106).

### *class* eutaxis.commands.adapters.codex.CodexAdapter(name='codex')

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Compile a command source into a Codex skill directory.

* **Parameters:**
  **name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))

#### name *: [str](https://docs.python.org/3/library/stdtypes.html#str)* *= 'codex'*

#### supports_scope(scope)

* **Parameters:**
  **scope** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [bool](https://docs.python.org/3/library/functions.html#bool)

#### artifact_dir(command_name, scope, , home, project_root)

* **Parameters:**
  * **command_name** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **scope** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
  * **home** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
  * **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

#### skill_frontmatter(source, , rendered_body)

* **Parameters:**
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
  * **rendered_body** ([*str*](https://docs.python.org/3/library/stdtypes.html#str))
* **Return type:**
  [dict](https://docs.python.org/3/library/stdtypes.html#dict)[[str](https://docs.python.org/3/library/stdtypes.html#str), [object](https://docs.python.org/3/library/functions.html#object)]

#### sibling_files(source, , context)

* **Parameters:**
  * **source** ([*CommandSource*](#eutaxis.commands.models.CommandSource))
  * **context** ([*dict*](https://docs.python.org/3/library/stdtypes.html#dict) *[*[*str*](https://docs.python.org/3/library/stdtypes.html#str) *,* [*object*](https://docs.python.org/3/library/functions.html#object) *]*)
* **Return type:**
  [*Iterable*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[[*ArtifactFile*](#eutaxis.commands.models.ArtifactFile)]
