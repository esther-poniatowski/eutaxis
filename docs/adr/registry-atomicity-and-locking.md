# Install registry: atomicity and locking

## Status

Accepted.

## Context

The install registry at `<state_dir>/installed-commands.json` is a flat
JSON file written by `eutaxis commands install` and
`eutaxis commands uninstall`. It is the source of truth for `uninstall`
and `diff` across CLI invocations.

The legacy implementation called `path.write_text(...)` directly inside
`upsert` and `remove`. Two realistic failure modes followed:

- **Truncated writes.** A `Ctrl-C` (or process kill, or filesystem
  full) between the truncate and the write left an empty or partial
  file. The next `load()` called `json.loads("")` and raised
  `JSONDecodeError`, which the caller did not catch and which surfaced
  as a generic crash with no actionable message.
- **Lost updates.** Two concurrent installs (`eutaxis commands install
  foo --agent claude` and `eutaxis commands install bar --agent codex`)
  could both call `load()`, both mutate the same snapshot, and both
  call `write_text` — last writer wins, the other's row vanishes.

The adversarial review at `.agent-work/2026-05-22-eutaxis-commands-review.md`
flagged both as Defect 3.

## Decision

Three changes, all confined to `commands/registry.py`:

1. **Atomic writes.** `_write` serialises the records to
   `<path>.tmp`, then calls `os.replace(tmp, path)`. POSIX guarantees
   `os.replace` is atomic when the source and target sit on the same
   filesystem (which is always true here — the temp file is a sibling
   of the registry). A crash between truncate and replace leaves the
   old file intact.
2. **Advisory file lock.** A context manager wraps every read-modify-
   write sequence (`upsert`, `remove`) and acquires `fcntl.LOCK_EX` on
   a sibling `installed-commands.lock`. The lock is advisory but is
   honoured by every code path in the subsystem that mutates the
   registry. Cross-process concurrent installs are now serialised.
3. **Actionable corruption surfacing.** `load()` catches
   `JSONDecodeError` and raises `RegistryCorruptedError` (subclass of
   `CommandError`) whose message names the path and suggests removing
   the file to rebuild. An empty file is treated as an empty list
   (does not raise). A non-list top-level JSON value also raises
   `RegistryCorruptedError`.

## Discarded alternatives

- **Atomic writes without a lock.** Rejected because the last-write-
  wins race still loses records — atomicity covers the truncate-and-
  write failure, not the read-modify-write race.
- **Optimistic concurrency: hash-check-and-retry.** Rejected because
  contention is low and the file is small; a coarse advisory lock is
  simpler than retry loops and produces clearer failure modes.
- **SQLite as backing store.** Rejected as overkill for a flat list of
  install records and because plain JSON is reviewable by hand.
  Locking, atomicity, and durability are not the bottleneck.
- **Silently rebuild from disk on `JSONDecodeError`.** Rejected because
  rebuilding hides the failure mode, may yield wrong results if the
  on-disk state has drifted independently of the registry, and trains
  callers to expect that the registry "fixes itself". Raising is
  louder and forces an explicit recovery.
- **Cross-platform lock library (`filelock`).** Rejected to avoid a
  dependency for a single function the subsystem already needs only
  on POSIX (Claude `~/.claude/`, Codex `~/.agents/` and `~/.codex/`
  paths are POSIX-centric). If Windows support becomes a requirement,
  swap `fcntl.flock` for `msvcrt.locking` or `filelock` in one place.

## Rationale

`os.replace` + `fcntl.flock` is the standard POSIX recipe for atomic,
serialised single-file state. The combination addresses both failure
modes the review identified, costs no new dependency, and stays
reviewable by hand. The error message names the path so a user can
recover by `rm` without inspecting source.

## Consequences

- Windows support of the registry requires changing the lock primitive.
- A stale `.lock` file is harmless (the lock is associated with the
  open file descriptor, not with the file's inode).
- Concurrent installs from independent processes are safe. A
  multiprocessing-pool test exercises the 4-worker case; the lock
  serialises them.
- `RegistryCorruptedError` is exported from `eutaxis.commands` so
  callers that want to distinguish "corrupted" from "missing" can
  catch it specifically.
