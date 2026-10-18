"""Rendering: ``CommandSource × AgentAdapter -> RenderedArtifact``.

The renderer writes no file. Its one read of the file system tests whether
the target of a relative link exists.

The renderer assembles a multi-file Agent Skill artifact:

- ``SKILL.md`` — entrypoint, YAML frontmatter + Markdown body.
- adapter-specific siblings (e.g. ``agents/openai.yaml`` for Codex).
- ``rules/<label>.md`` — one file per rule, when the source declares
  ``disclosure: progressive`` (see :mod:`eutaxis.commands.disclosure`).
- ``.eutaxis-owned.json`` — sidecar manifest used by the installer to
  detect ownership and drive idempotent updates.

The relative links of ``SKILL.md`` and of each rule file are rewritten for
the installed location (see :mod:`eutaxis.commands.links`). A relative link
whose target does not exist is kept as written and reported in
:attr:`RenderedArtifact.warnings`.

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
from .disclosure import DISCLOSURE_PROGRESSIVE, disclose
from .exceptions import CommandRenderError, FailureModeError
from .links import LinkResolver
from .models import ActionSpec, ArtifactFile, CommandSource, RenderedArtifact
from .templating import render as render_template

OWNED_FRONTMATTER_KEY = "x-eutaxis-owned"
SIDECAR_FILENAME = ".eutaxis-owned.json"
ENTRYPOINT_FILENAME = "SKILL.md"


def check_failure_mode(source: CommandSource) -> None:
    """Refuse a source whose failure-mode forbids its invocation routes.

    The compiler gate from the ``failure-mode-as-source-field`` ADR:

    - ``failure-mode: silent`` cannot ship as a skill that admits model
      invocation (``"model"`` in ``invocation``). Model-judgment
      activation gives no visibility guarantee before the first
      irreversible action.
    - ``failure-mode: silent`` with ``required-visibility: pre-invocation``
      cannot ship as any skill: the rule must be visible *before*
      deciding which procedure applies, so it routes only to the
      always-on body.

    Raises
    ------
    FailureModeError
        On a forbidden combination, with the source path in the message.
    """
    if source.failure_mode != "silent":
        return
    if "model" in source.invocation:
        raise FailureModeError(
            f"Refusing to emit a skill that admits model invocation from a "
            f"silent-failure source: {source.source_path}. Remove 'model' "
            f"from `invocation`, move the rule to the always-on body, or "
            f"re-author it as visible-failure. See ADR "
            f"failure-mode-as-source-field."
        )
    if source.required_visibility == "pre-invocation":
        raise FailureModeError(
            f"Refusing to emit any skill from a silent-failure source whose "
            f"required-visibility is 'pre-invocation': {source.source_path}. "
            f"The rule must route to the always-on body. See ADR "
            f"failure-mode-as-source-field."
        )


def render_command(
    source: CommandSource,
    adapter: AgentAdapter,
    *,
    project_root: Path,
    home: Path,
) -> RenderedArtifact:
    """Render a command source for one adapter as a multi-file artifact."""
    check_failure_mode(source)
    body_context = _body_context(source, adapter.name, project_root, home)
    rendered_body, rule_files, warnings = _layout_body(
        source, adapter.name, render_template(source.body, body_context)
    )

    front = adapter.skill_frontmatter(source, rendered_body=rendered_body)
    if OWNED_FRONTMATTER_KEY in front:
        raise CommandRenderError(
            f"Adapter {adapter.name!r} set reserved frontmatter key "
            f"{OWNED_FRONTMATTER_KEY!r}"
        )

    siblings = _merge_siblings(
        tuple(adapter.sibling_files(source, context=body_context)),
        rule_files,
        adapter_name=adapter.name,
    )

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
        warnings=warnings,
    )


def _layout_body(
    source: CommandSource, adapter_name: str, body: str
) -> tuple[str, tuple[ArtifactFile, ...], tuple[str, ...]]:
    """Split the rendered body as its disclosure mode requires, then relink it.

    Returns the ``SKILL.md`` body, the rule files and the link warnings. The
    missing link targets are collected on the body before the split, so their
    line numbers refer to the source file.
    """
    resolver = _link_resolver(source, adapter_name)
    warnings = tuple(
        missing.message
        for missing in resolver.missing(
            body, source_path=source.source_path, first_line=source.body_start_line
        )
    )
    rule_files: tuple[ArtifactFile, ...] = ()
    if source.disclosure == DISCLOSURE_PROGRESSIVE:
        disclosed = disclose(body, module=source.name)
        body = disclosed.entrypoint_body
        rule_files = disclosed.rule_files
    body, rule_files = _rewrite_links(resolver, body, rule_files)
    return body, rule_files, warnings


def _link_resolver(source: CommandSource, adapter_name: str) -> LinkResolver:
    """Return the resolver of the links of ``source`` for one adapter.

    A sibling skill that the adapter does not receive is left out, so a link
    to it falls back to the absolute path of its source.
    """
    return LinkResolver(
        source_dir=source.source_path.parent,
        skills={
            path: sibling.name
            for path, sibling in source.sibling_skills.items()
            if sibling.targets.admits(adapter_name)
        },
    )


def _rewrite_links(
    resolver: LinkResolver, body: str, rule_files: tuple[ArtifactFile, ...]
) -> tuple[str, tuple[ArtifactFile, ...]]:
    """Rewrite the relative links of the entrypoint body and of each rule file."""
    artifact_paths = frozenset(
        {ENTRYPOINT_FILENAME, *(f.relative_path for f in rule_files)}
    )
    rewritten_body = resolver.rewrite(
        body, emitter=ENTRYPOINT_FILENAME, artifact_paths=artifact_paths
    )
    rewritten_rules = tuple(
        ArtifactFile(
            relative_path=f.relative_path,
            content=resolver.rewrite(
                f.content, emitter=f.relative_path, artifact_paths=artifact_paths
            ),
        )
        for f in rule_files
    )
    return rewritten_body, rewritten_rules


def _merge_siblings(
    adapter_files: tuple[ArtifactFile, ...],
    rule_files: tuple[ArtifactFile, ...],
    *,
    adapter_name: str,
) -> tuple[ArtifactFile, ...]:
    """Append the rule files to the adapter siblings, refusing path clashes.

    A passthrough file at the path of a rule file would be silently replaced
    by one of the two, so the clash is an authoring error.
    """
    adapter_paths = {f.relative_path for f in adapter_files}
    clashes = sorted(
        f.relative_path for f in rule_files if f.relative_path in adapter_paths
    )
    if clashes:
        raise CommandRenderError(
            f"Adapter {adapter_name!r} emits sibling files at rule-file "
            f"paths {clashes}; rename the passthrough files or the rules."
        )
    return (*adapter_files, *rule_files)


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
