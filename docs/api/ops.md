<a id="operations"></a>

# Operations

Operational utilities for runtime tasks (memory management, CLI helpers).

<a id="module-eutaxis.ops.memory"></a>

<a id="memory"></a>

## Memory

Delete per-project agent memory directories.

Two agents are supported:

- Claude Code stores per-project memory at
  `~/.claude/projects/<encoded-project>/memory/`. The project slug
  is the absolute project path with `/` replaced by `-` and the
  leading slash mapped to a leading dash.
- Codex stores a single user-level memory directory at
  `~/.codex/memories/`.

The wipe operation removes every regular file under the resolved
directory, leaves the directory structure in place, and refuses to
operate on any path that does not lie under the agent’s allowed root.
A `--backup` mode copies the tree to a sibling
`memory.bak.YYYYMMDD-HHMMSS/` before deletion. `--dry-run` reports
the paths that would be removed without touching the filesystem.

<a id="eutaxis.ops.memory.MemoryWipeResult"></a>

### *class* eutaxis.ops.memory.MemoryWipeResult(removed=<factory>, skipped=<factory>, backup_paths=<factory>, dry_run=False)

Bases: [`object`](https://docs.python.org/3/library/functions.html#object)

Outcome of one wipe call.

* **Parameters:**
  * **removed** ([*list*](https://docs.python.org/3/library/stdtypes.html#list) *[*[*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *]*)
  * **skipped** ([*list*](https://docs.python.org/3/library/stdtypes.html#list) *[*[*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *]*)
  * **backup_paths** ([*list*](https://docs.python.org/3/library/stdtypes.html#list) *[*[*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *]*)
  * **dry_run** ([*bool*](https://docs.python.org/3/library/functions.html#bool))

<a id="eutaxis.ops.memory.MemoryWipeResult.removed"></a>

#### removed *: [list](https://docs.python.org/3/library/stdtypes.html#list)[[Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]*

<a id="eutaxis.ops.memory.MemoryWipeResult.skipped"></a>

#### skipped *: [list](https://docs.python.org/3/library/stdtypes.html#list)[[Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]*

<a id="eutaxis.ops.memory.MemoryWipeResult.backup_paths"></a>

#### backup_paths *: [list](https://docs.python.org/3/library/stdtypes.html#list)[[Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]*

<a id="eutaxis.ops.memory.MemoryWipeResult.dry_run"></a>

#### dry_run *: [bool](https://docs.python.org/3/library/functions.html#bool)* *= False*

<a id="eutaxis.ops.memory.clean_memory"></a>

### eutaxis.ops.memory.clean_memory(\*, agent, project_root=None, wipe_all=False, backup=False, dry_run=False, home=None)

Delete agent memory directories.

* **Parameters:**
  * **agent** ([*str*](https://docs.python.org/3/library/stdtypes.html#str)) – `"claude"`, `"codex"`, or `"all"`.
  * **project_root** (*Path* *,* *optional*) – Project root used to derive the Claude project slug. Defaults to
    the current working directory.
  * **wipe_all** ([*bool*](https://docs.python.org/3/library/functions.html#bool)) – When true *and* `agent` includes `claude`, wipe every Claude
    project memory under `~/.claude/projects/*/memory`. Ignored
    for Codex (its memory is already user-level).
  * **backup** ([*bool*](https://docs.python.org/3/library/functions.html#bool)) – Copy the resolved directory to a timestamped sibling before
    deletion.
  * **dry_run** ([*bool*](https://docs.python.org/3/library/functions.html#bool)) – Resolve and report paths without touching the filesystem.
  * **home** (*Path* *,* *optional*) – Override `$HOME`. Injected by tests; defaults to
    `Path.home()`.
* **Returns:**
  Removed regular file paths, plus any backup directories created.
* **Return type:**
  [MemoryWipeResult](#eutaxis.ops.memory.MemoryWipeResult)
* **Raises:**
  * [**OpsError**](#eutaxis.ops.exceptions.OpsError) – If `agent` is not a supported identifier.
  * [**OutsideAllowedRootError**](#eutaxis.ops.exceptions.OutsideAllowedRootError) – If a resolved target escapes its allowed root.

<a id="eutaxis.ops.memory.encode_project_slug"></a>

### eutaxis.ops.memory.encode_project_slug(project_root)

Encode an absolute project path as a Claude project directory name.

Replaces `/` with `-` and prepends a leading dash so that
`/Users/eresther/oikos` becomes `-Users-eresther-oikos`.

* **Parameters:**
  **project_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path))
* **Return type:**
  [str](https://docs.python.org/3/library/stdtypes.html#str)

<a id="module-eutaxis.ops.exceptions"></a>

<a id="exceptions"></a>

## Exceptions

Exceptions for shell-side operations.

<a id="eutaxis.ops.exceptions.OpsError"></a>

### *exception* eutaxis.ops.exceptions.OpsError

Bases: [`Exception`](https://docs.python.org/3/library/exceptions.html#Exception)

Base exception for operations.

<a id="eutaxis.ops.exceptions.OpsError.exit_code"></a>

#### exit_code *= 1*

<a id="eutaxis.ops.exceptions.OutsideAllowedRootError"></a>

### *exception* eutaxis.ops.exceptions.OutsideAllowedRootError

Bases: [`OpsError`](#eutaxis.ops.exceptions.OpsError)

Raised when a resolved path escapes its declared root.

This is the path-prefix guard that prevents wildcards or symlinks
from causing deletion outside the agent-memory directories.

<a id="eutaxis.ops.exceptions.OutsideAllowedRootError.exit_code"></a>

#### exit_code *= 2*
