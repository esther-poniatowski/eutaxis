"""Discover and parse command sources across discovery layers."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from .. import data_path
from .disclosure import DISCLOSURE_INLINE, DISCLOSURE_MODES
from .exceptions import CommandRenderError
from .links import normalize_path
from .models import (
    ActionSpec,
    AdapterPassthrough,
    CommandSource,
    SiblingSkill,
    TargetsSpec,
)

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_SUPPORTED_INVOCATIONS = frozenset({"user", "model"})
_SUPPORTED_FAILURE_MODES = frozenset({"silent", "visible"})
_SUPPORTED_REQUIRED_VISIBILITIES = frozenset({"pre-invocation", "pre-action"})


def builtin_dir() -> Path:
    """Return the directory holding built-in command sources."""
    return data_path() / "commands"


def user_dir(home: Path | None = None) -> Path:
    """Return the user-level command source directory."""
    return (home or Path.home()) / ".eutaxis" / "commands"


def project_dir(project_root: Path) -> Path:
    """Return the project-level command source directory."""
    return project_root / ".eutaxis" / "commands"


def load_sources(
    *,
    project_root: Path | None = None,
    home: Path | None = None,
) -> list[CommandSource]:
    """Discover command sources across all layers.

    Later layers override earlier ones by ``name``. Discovery order is
    built-in, user, project.
    """
    by_name: dict[str, CommandSource] = {}
    layers: list[tuple[str, Path]] = [("builtin", builtin_dir())]
    layers.append(("user", user_dir(home)))
    if project_root is not None:
        layers.append(("project", project_dir(project_root)))

    for layer, directory in layers:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            source = _load_one(path, layer=layer)
            by_name[source.name] = source

    return sorted(by_name.values(), key=lambda src: src.name)


def load_from_instruction_config(config_path: Path) -> list[CommandSource]:
    """Load Skill sources from an instruction-assembly configuration.

    Each ``task_modules`` entry names a Markdown file whose frontmatter
    must satisfy the Skill source schema (``name``, ``description``,
    ``regime``, ``failure-mode``, and ``required-visibility`` when
    silent). Missing files or frontmatter raise ``CommandRenderError``
    with the offending path.

    The discovery layer is recorded as ``"config"`` on each returned
    source.
    """
    from ..instructions.config import load_config

    config = load_config(config_path)
    sources: list[CommandSource] = []
    for module in config.task_modules:
        path = config.resolve(module.path)
        if not path.is_file():
            raise CommandRenderError(
                f"task_module {module.id!r} references missing file: {path}"
            )
        sources.append(_load_one(path, layer="config"))
    siblings = {
        normalize_path(source.source_path): SiblingSkill(
            name=source.name, targets=source.targets
        )
        for source in sources
    }
    return sorted(
        (replace(source, sibling_skills=siblings) for source in sources),
        key=lambda src: src.name,
    )


def _load_one(path: Path, *, layer: str) -> CommandSource:
    raw = path.read_text(encoding="utf-8")
    match = _FRONTMATTER.match(raw)
    if match is None:
        raise CommandRenderError(
            f"Missing YAML frontmatter in command source: {path}"
        )

    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise CommandRenderError(
            f"Invalid YAML frontmatter in {path}: {exc}"
        ) from exc

    if not isinstance(meta, dict):
        raise CommandRenderError(
            f"Frontmatter must be a mapping in {path}"
        )

    body = raw[match.end():].lstrip("\n")
    source = _build_source(meta, body=body, path=path, layer=layer)
    return replace(source, body_start_line=raw[: len(raw) - len(body)].count("\n") + 1)


def _build_source(
    meta: dict[str, Any], *, body: str, path: Path, layer: str
) -> CommandSource:
    for required in ("name", "description", "invocation", "failure-mode"):
        if required not in meta:
            raise CommandRenderError(
                f"Command source {path} missing required key: {required!r}"
            )

    invocation = _parse_invocation(meta["invocation"], path=path)
    failure_mode = str(meta["failure-mode"])
    if failure_mode not in _SUPPORTED_FAILURE_MODES:
        raise CommandRenderError(
            f"Unsupported failure-mode {failure_mode!r} in {path}; "
            f"expected one of {sorted(_SUPPORTED_FAILURE_MODES)}"
        )

    required_visibility = _parse_required_visibility(
        meta.get("required-visibility"), failure_mode=failure_mode, path=path
    )

    scope_default = str(meta.get("scope_default", "user"))
    if scope_default not in {"user", "project"}:
        raise CommandRenderError(
            f"scope_default must be 'user' or 'project' in {path}"
        )

    targets = _parse_targets(meta.get("targets"), path=path)
    action = _parse_action(meta.get("action"), path=path)
    overrides = _parse_overrides(meta.get("overrides"), path=path)
    adapters = _parse_adapters(meta.get("adapters"), path=path)
    argument_hint = str(meta.get("argument-hint", "") or "")
    disclosure = str(meta.get("disclosure", DISCLOSURE_INLINE))
    if disclosure not in DISCLOSURE_MODES:
        raise CommandRenderError(
            f"Unsupported disclosure {disclosure!r} in {path}; "
            f"expected one of {sorted(DISCLOSURE_MODES)}"
        )

    return CommandSource(
        name=str(meta["name"]),
        description=str(meta["description"]),
        invocation=invocation,
        failure_mode=failure_mode,
        required_visibility=required_visibility,
        scope_default=scope_default,
        targets=targets,
        action=action,
        body=body,
        argument_hint=argument_hint,
        adapters=adapters,
        overrides=overrides,
        disclosure=disclosure,
        source_path=path,
        layer=layer,
    )


def _parse_invocation(raw: Any, *, path: Path) -> tuple[str, ...]:
    if isinstance(raw, str):
        raise CommandRenderError(
            f"'invocation' must be a list of permitted routes in {path}; "
            f"got the string {raw!r}. Use list syntax, e.g. "
            f"`invocation: [user]` or `invocation: [model, user]`."
        )
    if not isinstance(raw, list) or not raw:
        raise CommandRenderError(
            f"'invocation' must be a non-empty list in {path}; "
            f"got {raw!r}"
        )
    values = tuple(str(item) for item in raw)
    unknown = [v for v in values if v not in _SUPPORTED_INVOCATIONS]
    if unknown:
        raise CommandRenderError(
            f"Unsupported invocation route(s) {unknown!r} in {path}; "
            f"expected members of {sorted(_SUPPORTED_INVOCATIONS)}"
        )
    if len(set(values)) != len(values):
        raise CommandRenderError(
            f"'invocation' contains duplicate routes in {path}: {values!r}"
        )
    return values


def _parse_required_visibility(
    raw: Any, *, failure_mode: str, path: Path
) -> str | None:
    if failure_mode == "silent":
        if raw is None:
            raise CommandRenderError(
                f"required-visibility is mandatory when failure-mode is "
                f"'silent' in {path}; expected one of "
                f"{sorted(_SUPPORTED_REQUIRED_VISIBILITIES)}"
            )
        value = str(raw)
        if value not in _SUPPORTED_REQUIRED_VISIBILITIES:
            raise CommandRenderError(
                f"Unsupported required-visibility {value!r} in {path}; "
                f"expected one of "
                f"{sorted(_SUPPORTED_REQUIRED_VISIBILITIES)}"
            )
        return value
    if raw is not None:
        raise CommandRenderError(
            f"required-visibility must be unset when failure-mode is "
            f"'visible' in {path}"
        )
    return None


def _parse_targets(raw: Any, *, path: Path) -> TargetsSpec:
    if raw is None:
        return TargetsSpec()
    if not isinstance(raw, dict):
        raise CommandRenderError(f"'targets' must be a mapping in {path}")
    return TargetsSpec(
        include=tuple(str(item) for item in raw.get("include", ()) or ()),
        exclude=tuple(str(item) for item in raw.get("exclude", ()) or ()),
    )


def _parse_action(raw: Any, *, path: Path) -> ActionSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise CommandRenderError(f"'action' must be a mapping in {path}")
    kind = str(raw.get("kind", "shell"))
    if kind != "shell":
        raise CommandRenderError(
            f"Unsupported action kind {kind!r} in {path}; only 'shell' is supported"
        )
    template = raw.get("template")
    if not isinstance(template, str) or not template.strip():
        raise CommandRenderError(
            f"action.template must be a non-empty string in {path}"
        )
    return ActionSpec(kind=kind, template=template)


def _parse_overrides(raw: Any, *, path: Path) -> dict[str, dict]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise CommandRenderError(f"'overrides' must be a mapping in {path}")
    out: dict[str, dict] = {}
    for adapter_name, value in raw.items():
        if not isinstance(value, dict):
            raise CommandRenderError(
                f"overrides[{adapter_name!r}] must be a mapping in {path}"
            )
        out[str(adapter_name)] = value
    return out


def _parse_adapters(raw: Any, *, path: Path) -> dict[str, AdapterPassthrough]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise CommandRenderError(f"'adapters' must be a mapping in {path}")
    out: dict[str, AdapterPassthrough] = {}
    for adapter_name, value in raw.items():
        if not isinstance(value, dict):
            raise CommandRenderError(
                f"adapters[{adapter_name!r}] must be a mapping in {path}"
            )
        frontmatter = value.get("frontmatter", {}) or {}
        if not isinstance(frontmatter, dict):
            raise CommandRenderError(
                f"adapters[{adapter_name!r}].frontmatter must be a mapping in {path}"
            )
        files = value.get("files", {}) or {}
        if not isinstance(files, dict):
            raise CommandRenderError(
                f"adapters[{adapter_name!r}].files must be a mapping in {path}"
            )
        files_str: dict[str, str] = {}
        for fpath, fcontent in files.items():
            if not isinstance(fcontent, str):
                raise CommandRenderError(
                    f"adapters[{adapter_name!r}].files[{fpath!r}] must be a string in {path}"
                )
            files_str[str(fpath)] = fcontent
        out[str(adapter_name)] = AdapterPassthrough(
            frontmatter=dict(frontmatter),
            files=files_str,
        )
    return out
