"""Pure rendering: ``CommandSource × AgentAdapter -> RenderedArtifact``.

The renderer assembles a multi-file Agent Skill artifact:

- ``SKILL.md`` — entrypoint, YAML frontmatter + Markdown body.
- adapter-specific siblings (e.g. ``agents/openai.yaml`` for Codex).
- ``.eutaxis-owned.json`` — sidecar manifest used by the installer to
  detect ownership and drive idempotent updates.

Ownership is tracked **twice** for robustness:

1. ``SKILL.md`` frontmatter carries an ``x-eutaxis-owned`` hash key —
   readable without parsing JSON, survives partial sidecar loss.
2. ``.eutaxis-owned.json`` lists every file the installer owns and its
   per-file hash — survives manual edits to ``SKILL.md`` frontmatter.

The hash is computed over the rendered body plus the
non-ownership frontmatter dict (canonicalised) plus the sibling files
(sorted by relative path). The marker is injected last, so the hash is
stable regardless of the marker bytes themselves.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from .adapters import AgentAdapter
from .models import ActionSpec, ArtifactFile, CommandSource, RenderedArtifact
from .templating import render as render_template

OWNED_FRONTMATTER_KEY = "x-eutaxis-owned"
SIDECAR_FILENAME = ".eutaxis-owned.json"
ENTRYPOINT_FILENAME = "SKILL.md"


def render_command(
    source: CommandSource,
    adapter: AgentAdapter,
    *,
    project_root: Path,
    home: Path,
) -> RenderedArtifact:
    """Render a command source for one adapter as a multi-file artifact."""
    body_context = _body_context(source, adapter.name, project_root, home)
    rendered_body = render_template(source.body, body_context)

    front = adapter.skill_frontmatter(source, rendered_body=rendered_body)
    if OWNED_FRONTMATTER_KEY in front:
        from .exceptions import CommandRenderError

        raise CommandRenderError(
            f"Adapter {adapter.name!r} set reserved frontmatter key "
            f"{OWNED_FRONTMATTER_KEY!r}"
        )

    siblings = tuple(adapter.sibling_files(source, context=body_context))

    pre_hash = _content_hash(front, rendered_body, siblings)

    front_with_marker = dict(front)
    front_with_marker[OWNED_FRONTMATTER_KEY] = pre_hash
    skill_md = _format_skill_md(front_with_marker, rendered_body)

    sidecar = _format_sidecar(
        skill_md=skill_md,
        siblings=siblings,
        artifact_name=source.name,
        adapter_name=adapter.name,
        content_hash=pre_hash,
    )

    files = (
        ArtifactFile(relative_path=ENTRYPOINT_FILENAME, content=skill_md),
        *siblings,
        ArtifactFile(relative_path=SIDECAR_FILENAME, content=sidecar),
    )

    return RenderedArtifact(
        name=source.name,
        adapter=adapter.name,
        files=files,
        content_hash=pre_hash,
    )


def _body_context(
    source: CommandSource, adapter_name: str, project_root: Path, home: Path
) -> dict[str, object]:
    action = _effective_action(source, adapter_name)
    base = {
        "agent": adapter_name,
        "project_root": str(project_root),
        "home": str(home),
    }
    return {
        **base,
        "action": {
            "kind": action.kind if action else "",
            "template": render_template(action.template, base) if action else "",
        },
    }


def _effective_action(source: CommandSource, adapter_name: str) -> ActionSpec | None:
    override = source.overrides.get(adapter_name, {})
    if "action" in override:
        action_over = override["action"]
        template = action_over.get("template")
        if not isinstance(template, str) or not template.strip():
            return source.action
        kind = str(
            action_over.get("kind", source.action.kind if source.action else "shell")
        )
        return ActionSpec(kind=kind, template=template)
    return source.action


def _content_hash(
    front: dict[str, object],
    body: str,
    siblings: tuple[ArtifactFile, ...],
) -> str:
    canonical = {
        "frontmatter": _canonicalise(front),
        "body": body,
        "siblings": [
            {"path": f.relative_path, "content": f.content}
            for f in sorted(siblings, key=lambda f: f.relative_path)
        ],
    }
    blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _canonicalise(value: object) -> object:
    if isinstance(value, dict):
        return {key: _canonicalise(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonicalise(item) for item in value]
    return value


def _format_skill_md(frontmatter: dict[str, object], body: str) -> str:
    yaml_block = yaml.safe_dump(
        frontmatter, sort_keys=True, default_flow_style=False
    ).rstrip()
    body_clean = body.rstrip() + "\n"
    return f"---\n{yaml_block}\n---\n\n{body_clean}"


def _format_sidecar(
    *,
    skill_md: str,
    siblings: tuple[ArtifactFile, ...],
    artifact_name: str,
    adapter_name: str,
    content_hash: str,
) -> str:
    entries = [
        {
            "path": ENTRYPOINT_FILENAME,
            "sha256": _file_hash(skill_md),
        }
    ]
    for sib in sorted(siblings, key=lambda f: f.relative_path):
        entries.append({"path": sib.relative_path, "sha256": _file_hash(sib.content)})
    payload = {
        "schema_version": 1,
        "name": artifact_name,
        "adapter": adapter_name,
        "content_hash": content_hash,
        "files": entries,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _file_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
