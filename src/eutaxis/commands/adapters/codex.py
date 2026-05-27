"""Codex adapter: compile a command source into a Codex skill.

Targets ``$HOME/.agents/skills/<name>/SKILL.md`` (user scope) and
``<project>/.agents/skills/<name>/SKILL.md`` (project scope). Codex
requires the ``name`` field in ``SKILL.md`` to **equal the parent
directory name** (`skills-comparison.md`), so the installer always
mirrors the source ``name`` slug as the artifact directory name.

Codex-specific metadata — invocation policy, UI metadata, declared tool
dependencies — lives in the sibling ``agents/openai.yaml`` file
(`codex/skills.md`). Invocation translation:

- ``"model" not in invocation`` -> ``policy.allow_implicit_invocation:
  false`` in the derived ``agents/openai.yaml``. Explicit user
  invocation via ``$<name>`` still works.
- ``"model" in invocation`` -> the ``policy`` block is not derived;
  Codex is free to pick the skill implicitly. Passthrough keys are still
  honoured if the author supplies them.

The ``dependencies.tools`` block declared via passthrough is *metadata
only, not a permission grant*; sandbox / approval policy still lives in
``~/.codex/config.toml`` and is out of scope for the artifact.

The experimental ``allowed-tools`` field in ``SKILL.md`` is **not
emitted** by this adapter: the Agent Skills spec marks it experimental
on Codex and Codex documents pre-approval as host configuration, not
artifact metadata (`skills-comparison.md:106`).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..exceptions import CommandError
from ..models import ArtifactFile, CommandSource
from ..templating import render as render_template


@dataclass(frozen=True)
class CodexAdapter:
    """Compile a command source into a Codex skill directory."""

    name: str = "codex"

    def supports_scope(self, scope: str) -> bool:
        return scope in {"user", "project"}

    def artifact_dir(
        self, command_name: str, scope: str, *, home: Path, project_root: Path
    ) -> Path:
        if scope == "user":
            return home / ".agents" / "skills" / command_name
        if scope == "project":
            return project_root / ".agents" / "skills" / command_name
        raise CommandError(f"Unknown scope: {scope!r}")

    def skill_frontmatter(
        self, source: CommandSource, *, rendered_body: str
    ) -> dict[str, object]:
        del rendered_body
        front: dict[str, object] = {
            "name": source.name,
            "description": source.description,
        }
        passthrough = source.adapters.get(self.name)
        if passthrough is not None:
            for key, value in passthrough.frontmatter.items():
                if key == "allowed-tools":
                    # Experimental on Codex and not a permission grant;
                    # refuse to emit so authors do not assume otherwise.
                    raise CommandError(
                        "'allowed-tools' is not emitted on Codex; "
                        "use ~/.codex/config.toml for pre-approval."
                    )
                front[key] = value
        return front

    def sibling_files(
        self, source: CommandSource, *, context: dict[str, object]
    ) -> Iterable[ArtifactFile]:
        siblings: list[ArtifactFile] = []
        passthrough = source.adapters.get(self.name)
        passthrough_files = passthrough.files if passthrough is not None else {}

        openai_yaml = _build_openai_yaml(source, passthrough_files)
        if openai_yaml is not None:
            siblings.append(
                ArtifactFile(relative_path="agents/openai.yaml", content=openai_yaml)
            )

        for path, content in passthrough_files.items():
            if path == "agents/openai.yaml":
                # Already merged into the derived openai.yaml above.
                continue
            rendered = render_template(content, context)
            siblings.append(ArtifactFile(relative_path=path, content=rendered))

        return tuple(siblings)


def _build_openai_yaml(
    source: CommandSource, passthrough_files: dict[str, str]
) -> str | None:
    """Merge regime-derived policy into the passthrough openai.yaml.

    The derived document always carries ``policy.allow_implicit_invocation``
    when ``regime: user-invoked``. Passthrough keys are merged on top so
    the author can extend (or override) the derived defaults.
    """
    derived: dict[str, object] = {}
    if "model" not in source.invocation:
        derived["policy"] = {"allow_implicit_invocation": False}

    raw = passthrough_files.get("agents/openai.yaml")
    if raw is not None:
        parsed = yaml.safe_load(raw)
        if parsed is not None and not isinstance(parsed, dict):
            raise CommandError(
                "'agents/openai.yaml' passthrough must be a YAML mapping"
            )
        if isinstance(parsed, dict):
            _deep_merge(derived, parsed)

    if not derived:
        return None
    return yaml.safe_dump(derived, sort_keys=True)


def _deep_merge(base: dict, overlay: dict) -> None:
    for key, value in overlay.items():
        existing = base.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            _deep_merge(existing, value)
        else:
            base[key] = value
