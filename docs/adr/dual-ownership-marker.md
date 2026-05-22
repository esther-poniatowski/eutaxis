# Dual ownership marker: sidecar plus frontmatter key

## Status

Accepted.

## Context

The installer must decide whether an existing artifact directory at the
target path is eutaxis-owned before overwriting or removing its files.
The legacy single-file artifact used an HTML comment on the first line
of the rendered Markdown file as the ownership marker. That mechanism
does not survive the move to multi-file artifacts: some sibling files
are not Markdown (e.g. `agents/openai.yaml`), and the comment lives
inside `SKILL.md`, which the agent itself may rewrite during a session
(`claude/skills.md:43` notes that edits take effect within the session).

The realistic failure modes the marker has to survive:

- The user deletes the on-disk marker by hand, or a directory-wide
  cleanup script prunes hidden files.
- The user reformats `SKILL.md` (YAML reflow, frontmatter rewrite) and
  silently strips an extension key.
- The agent rewrites `SKILL.md` during a session in a way that drops
  unknown keys.
- The registry and the disk drift (branch hops, manual cleanup,
  multiple machines sharing a registry path).

A single marker leaves one of these failure modes uncovered.

## Decision

Track ownership **twice**, with the sidecar as the canonical source of
truth and the frontmatter key as a fallback.

1. **`.eutaxis-owned.json`** — sidecar inside the artifact directory.
   Carries `{schema_version, name, adapter, content_hash, files: [{path, sha256}]}`.
   Lists every file the installer owns; drives uninstall.
2. **`x-eutaxis-owned: <hash>`** — extension key inside the rendered
   `SKILL.md` frontmatter. The `x-` prefix signals a vendor extension;
   both agents tolerate unknown frontmatter keys in practice.

Both carry the **same canonical hash**, computed over the frontmatter
dict (minus the marker key), the rendered body, and the sorted sibling
files. The hash is injected after computation, so the marker bytes
never participate in the hash they identify (no chicken-and-egg
problem).

The installer recognises a directory as eutaxis-owned when **either**
marker is present. The sidecar is checked first: if present, its file
list is the source of truth for uninstall and update. If the sidecar
is missing but the frontmatter marker survives, the directory is
treated as ours and updates proceed (uninstall would have to remove
only `SKILL.md` since the sibling list is unknown — acceptable as a
recovery path; the renderer rewrites the full set on next install).

A directory that contains files but matches neither check is refused
as user-owned unless `--force` is passed.

## Discarded alternatives

- **Sidecar only.** Rejected because a user-run formatter or `rm
  .eutaxis-*` would silently strip the marker and the installer would
  refuse to re-install its own output.
- **Frontmatter marker only.** Rejected because the marker cannot
  enumerate sibling files; uninstall would have to glob the directory
  (risky) or rely on the registry alone (loses safety on drift). Also
  fragile to agent rewrites of `SKILL.md`.
- **Registry only, no on-disk marker.** Rejected because the registry
  and the disk drift in realistic scenarios. Without a disk marker the
  installer cannot distinguish "we installed this here and lost the
  record" from "the user wrote this by hand", and must conservatively
  refuse both.
- **HTML comment above the frontmatter** (carry-over from the legacy
  design). Rejected because `SKILL.md` frontmatter must start at line
  one; a comment above breaks YAML parsing on both agents.
- **Marker carried in a reserved key of the registry record** (no disk
  marker at all). Same failure mode as registry-only.

## Rationale

The two markers are cheap to maintain and protect against orthogonal
failure modes. Either alone leaves a realistic gap. The sidecar is
listed first because it carries the per-file inventory uninstall needs;
the frontmatter key is the recovery channel when the sidecar is gone.

## Consequences

- The renderer computes the hash in two passes: build the frontmatter
  dict without the marker, hash, then inject the marker and re-emit.
- The installer's ownership check has two short-circuit branches; tests
  exercise both (sidecar present, sidecar deleted but marker survives).
- A directory containing only `.eutaxis-owned.json` and no `SKILL.md`
  is recognised as ours (acceptable: the sidecar is canonical, and the
  installer rewrites the full set on update).
- The `x-eutaxis-owned` key sits inside frontmatter that agents parse.
  Both Claude and Codex are documented to tolerate unknown keys; if a
  future stricter validator rejects it, we would switch to a comment
  trailer or move the marker entirely to the sidecar.
