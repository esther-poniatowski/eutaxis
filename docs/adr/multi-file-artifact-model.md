# Multi-file rendered artifact model

## Status

Accepted. Follows from [convergence-on-agent-skills-standard](convergence-on-agent-skills-standard.md): once the framework commits to Agent Skills as the on-demand artifact shape, the unit of compilation is a directory rather than a file.

## Context

An Agent Skill artifact is a directory, not a single file. Codex skills carry UI metadata, invocation policy, and tool-dependency metadata in a sibling `agents/openai.yaml` file rather than in `SKILL.md` frontmatter (`codex/skills.md:79-100`). Claude skills may reference supporting files (scripts, references, examples) alongside `SKILL.md`. The installer also needs to write an on-disk ownership marker that is not part of either agent's recognised file set.

The legacy `RenderedCommand` was a single `content: str` carrying one file's worth of bytes. The `AgentAdapter` Protocol returned a single `Path` (target) and a single string (frontmatter). Neither shape can represent Codex's `agents/openai.yaml`, a hidden ownership sidecar, or any future skill that bundles scripts or templates.

## Decision

Replace the single-file rendered output with a multi-file artifact:

```python
@dataclass(frozen=True)
class ArtifactFile:
    relative_path: str  # POSIX, relative to artifact root
    content: str

@dataclass(frozen=True)
class RenderedArtifact:
    name: str
    adapter: str
    files: tuple[ArtifactFile, ...]
    content_hash: str
```

Every rendered artifact contains at least `SKILL.md` and `.eutaxis-owned.json`. Codex artifacts additionally contain `agents/openai.yaml` when the source declares `regime: user-invoked` or supplies passthrough metadata.

The `AgentAdapter` Protocol is rewritten to:

- `supports_scope(scope) -> bool`
- `artifact_dir(name, scope, *, home, project_root) -> Path` — the directory under which all files of the artifact live.
- `skill_frontmatter(source, *, rendered_body) -> dict[str, object]` — the YAML frontmatter dict for `SKILL.md`, sans the ownership marker.
- `sibling_files(source, *, context) -> Iterable[ArtifactFile]` — the files that accompany `SKILL.md` for this agent.

The renderer assembles the artifact from these adapter calls; body templating, regime mapping, and hash computation stay adapter-neutral inside `rendering.py`.

## Discarded alternatives

- **Keep the legacy `(Path, str)` Protocol** and add a second optional return slot. Rejected because the asymmetry is structural: Codex carries metadata in a sibling file by spec, not in frontmatter. A bolt-on optional slot encodes "Codex is special" everywhere instead of treating multi-file as the general case.
- **Move all rendering logic into the adapter** and have the renderer call a single `adapter.render(source, ...) -> RenderedArtifact`. Rejected because body templating, the regime → flag mapping, hash computation, sidecar emission, and ownership-marker injection are adapter-neutral and belong in one place; pushing them into each adapter would duplicate logic and invite drift between agents.
- **Make the *source* a directory** (`data/commands/clean-memory/SKILL.md` plus per-agent siblings). Rejected because the proposal §3 / §7 source model is one self-describing Markdown file: users add a command by dropping `examine-memory.md` under `~/.eutaxis/commands/`, not by authoring a directory tree. The fan-out belongs in the adapter, not in the source.
- **Emit only `SKILL.md` and rely on the registry for ownership.** Rejected because the registry and the disk drift in realistic scenarios (branch hops, manual cleanup, multi-machine state); the installer needs a disk marker too. See [dual-ownership-marker](dual-ownership-marker.md).

## Rationale

Localising the fan-out inside the adapter preserves the flat, self-describing source layout while letting each adapter emit whatever sibling files its agent actually consumes. The Protocol is now shaped by what an artifact *is* (a directory of files) rather than by the legacy single-file convenience.

## Consequences

- `InstallRecord.path` is now an artifact directory, not a single file. External readers of the registry JSON need updating; in-tree there is no other consumer.
- `commands show` prints multiple `--- <relative-path> ---` blocks instead of one Markdown blob. Any script that parsed the legacy output needs updating.
- The installer handles directory-aware install / uninstall / diff. Idempotent updates compare per-file rendered content against the hash recorded in the on-disk sidecar.
- Adapter-specific files are expressed through [adapter-passthrough-source-schema](adapter-passthrough-source-schema.md); the Protocol carries adapter-derived siblings (e.g. Codex's regime → `agents/openai.yaml`) without bloating the source schema.
