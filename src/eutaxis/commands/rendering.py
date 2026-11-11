"""Render adapter-neutral Skill inputs into multi-file artifacts.

The renderer writes no file. Its one read of the file system tests whether
the target of a relative link exists.

The command-source entry point converts ``CommandSource`` into the shared
``SkillRenderInput`` model. The assembler then emits a multi-file artifact:

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
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

import yaml

from .adapters import AgentAdapter
from .disclosure import DISCLOSURE_PROGRESSIVE, disclose
from .exceptions import CommandRenderError, FailureModeError
from .links import LinkResolver
from .models import (
    ActionSpec,
    AdapterPassthrough,
    ArtifactFile,
    CommandSource,
    RenderedArtifact,
    SkillRenderInput,
)
from .templating import render as render_template

OWNED_FRONTMATTER_KEY = "x-eutaxis-owned"
SIDECAR_FILENAME = ".eutaxis-owned.json"
SIDECAR_SCHEMA = "eutaxis:skill-ownership@1"
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
    render_input = _command_render_input(source, adapter.name, body_context)
    adapter_files = tuple(adapter.sibling_files(render_input))
    rendered_body, rule_files, warnings = _layout_body(
        source,
        adapter.name,
        render_input.entrypoint_body,
        sibling_paths=frozenset(file.relative_path for file in adapter_files),
    )
    render_input = replace(
        render_input,
        entrypoint_body=rendered_body,
        resources=rule_files,
    )
    return _assemble_skill_with_adapter_files(
        render_input,
        adapter,
        adapter_files,
        warnings=warnings,
    )


def assemble_skill(
    source: SkillRenderInput,
    adapter: AgentAdapter,
    *,
    warnings: tuple[str, ...] = (),
) -> RenderedArtifact:
    """Assemble one adapter-neutral input into a host-native Skill artifact."""
    if not adapter.supports_scope(source.scope):
        raise CommandRenderError(
            f"Adapter {adapter.name!r} does not support scope {source.scope!r}"
        )
    adapter_files = tuple(adapter.sibling_files(source))
    return _assemble_skill_with_adapter_files(
        source,
        adapter,
        adapter_files,
        warnings=warnings,
    )


def _assemble_skill_with_adapter_files(
    source: SkillRenderInput,
    adapter: AgentAdapter,
    adapter_files: tuple[ArtifactFile, ...],
    *,
    warnings: tuple[str, ...],
) -> RenderedArtifact:
    """Assemble with one retained result from the adapter extension point."""

    front = adapter.skill_frontmatter(source, rendered_body=source.entrypoint_body)
    if OWNED_FRONTMATTER_KEY in front:
        raise CommandRenderError(
            f"Adapter {adapter.name!r} set reserved frontmatter key "
            f"{OWNED_FRONTMATTER_KEY!r}"
        )

    content_files = (
        *((source.contract_file,) if source.contract_file is not None else ()),
        *source.resources,
    )
    first, second = (
        (content_files, adapter_files)
        if source.contract_file is not None
        else (adapter_files, content_files)
    )
    siblings = _merge_artifact_files(first, second, adapter_name=adapter.name)

    pre_hash = _content_hash(front, source.entrypoint_body, siblings)

    front_with_marker = dict(front)
    front_with_marker[OWNED_FRONTMATTER_KEY] = pre_hash
    skill_md = _format_skill_md(front_with_marker, source.entrypoint_body)

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
        scope=source.scope,
        files=files,
        content_hash=pre_hash,
        warnings=tuple(warnings),
    )


def _command_render_input(
    source: CommandSource,
    adapter_name: str,
    body_context: dict[str, object],
) -> SkillRenderInput:
    """Convert one established command source into the shared render model."""
    passthrough = source.adapters.get(adapter_name, AdapterPassthrough())
    frontmatter = dict(passthrough.frontmatter)
    if adapter_name == "claude" and source.argument_hint:
        frontmatter.setdefault("argument-hint", source.argument_hint)
    files = dict(passthrough.files)
    if adapter_name == "codex":
        files = {
            path: (
                content
                if path == "agents/openai.yaml"
                else render_template(content, body_context)
            )
            for path, content in files.items()
        }
    adapter_passthrough = MappingProxyType(
        {
            adapter_name: AdapterPassthrough(
                frontmatter=frontmatter,
                files=files,
            )
        }
    )
    return SkillRenderInput(
        name=source.name,
        description=source.description,
        scope=source.scope_default,
        invocation=source.invocation,
        entrypoint_body=render_template(source.body, body_context),
        contract_file=None,
        resources=(),
        adapter_passthrough=adapter_passthrough,
    )


def _layout_body(
    source: CommandSource,
    adapter_name: str,
    body: str,
    *,
    sibling_paths: frozenset[str] = frozenset(),
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
            body,
            source_path=source.source_path,
            first_line=source.body_start_line,
            artifact_paths=sibling_paths,
        )
    )
    rule_files: tuple[ArtifactFile, ...] = ()
    if source.disclosure == DISCLOSURE_PROGRESSIVE:
        disclosed = disclose(body, module=source.name)
        body = disclosed.entrypoint_body
        rule_files = disclosed.rule_files
    body, rule_files = _rewrite_links(
        resolver, body, rule_files, sibling_paths=sibling_paths
    )
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
    resolver: LinkResolver,
    body: str,
    rule_files: tuple[ArtifactFile, ...],
    *,
    sibling_paths: frozenset[str] = frozenset(),
) -> tuple[str, tuple[ArtifactFile, ...]]:
    """Rewrite the relative links of the entrypoint body and of each rule file."""
    artifact_paths = frozenset(
        {
            ENTRYPOINT_FILENAME,
            *sibling_paths,
            *(f.relative_path for f in rule_files),
        }
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


def _merge_artifact_files(
    first: tuple[ArtifactFile, ...],
    second: tuple[ArtifactFile, ...],
    *,
    adapter_name: str,
) -> tuple[ArtifactFile, ...]:
    """Merge adapter and source files while rejecting every path collision."""
    files = (*first, *second)
    reserved = (ENTRYPOINT_FILENAME, SIDECAR_FILENAME)
    for index, candidate in enumerate(files):
        if any(
            _artifact_paths_collide(candidate.relative_path, path) for path in reserved
        ):
            raise CommandRenderError(
                f"Adapter {adapter_name!r} emits reserved artifact path "
                f"{candidate.relative_path!r}"
            )
        for prior in files[:index]:
            if _artifact_paths_collide(candidate.relative_path, prior.relative_path):
                raise CommandRenderError(
                    f"Artifact paths {prior.relative_path!r} and "
                    f"{candidate.relative_path!r} collide for adapter "
                    f"{adapter_name!r}"
                )
    return files


def _artifact_paths_collide(first: str, second: str) -> bool:
    """Return whether two POSIX file paths require one path as a directory."""
    first_parts = tuple(first.split("/"))
    second_parts = tuple(second.split("/"))
    common = min(len(first_parts), len(second_parts))
    return first_parts[:common] == second_parts[:common]


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
        "_schema": SIDECAR_SCHEMA,
        "name": artifact_name,
        "adapter": adapter_name,
        "content_hash": content_hash,
        "files": entries,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _file_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
