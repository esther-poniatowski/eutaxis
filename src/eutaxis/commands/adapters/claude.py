"""Claude Code adapter: compile a command source into a Claude skill.

Targets ``~/.claude/skills/<name>/SKILL.md`` (user scope) and
``<project>/.claude/skills/<name>/SKILL.md`` (project scope).

Invocation translation:

- ``"model" not in invocation`` -> ``disable-model-invocation: true``
  in the rendered frontmatter (documented use case for *task* skills
  with side effects whose timing must be controlled —
  ``claude/skills.md``). User invocation via ``/<name>`` still works.
- ``"model" in invocation`` -> ``disable-model-invocation`` is omitted;
  Claude is free to pick the skill from its description, and user
  invocation via ``/<name>`` continues to work as well.

Claude has no analogue to Codex's sibling ``agents/openai.yaml``: all
metadata (including ``allowed-tools``, ``argument-hint``) is folded
into ``SKILL.md`` frontmatter.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ..exceptions import CommandError
from ..models import ArtifactFile, CommandSource


@dataclass(frozen=True)
class ClaudeCodeAdapter:
    """Compile a command source into a Claude skill directory."""

    name: str = "claude"

    def supports_scope(self, scope: str) -> bool:
        return scope in {"user", "project"}

    def artifact_dir(
        self, command_name: str, scope: str, *, home: Path, project_root: Path
    ) -> Path:
        if scope == "user":
            return home / ".claude" / "skills" / command_name
        if scope == "project":
            return project_root / ".claude" / "skills" / command_name
        raise CommandError(f"Unknown scope: {scope!r}")

    def skill_frontmatter(
        self, source: CommandSource, *, rendered_body: str
    ) -> dict[str, object]:
        del rendered_body  # Claude frontmatter is body-independent.
        front: dict[str, object] = {
            "name": source.name,
            "description": source.description,
        }
        if "model" not in source.invocation:
            front["disable-model-invocation"] = True
        if source.argument_hint:
            front["argument-hint"] = source.argument_hint
        passthrough = source.adapters.get(self.name)
        if passthrough is not None:
            for key, value in passthrough.frontmatter.items():
                front[key] = value
        return front

    def sibling_files(
        self, source: CommandSource, *, context: dict[str, object]
    ) -> Iterable[ArtifactFile]:
        del context  # No Claude-native sibling files; passthrough files only.
        passthrough = source.adapters.get(self.name)
        if passthrough is None:
            return ()
        return tuple(
            ArtifactFile(relative_path=path, content=content)
            for path, content in passthrough.files.items()
        )
