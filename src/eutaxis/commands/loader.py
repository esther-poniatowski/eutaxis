"""Discover and parse command sources across discovery layers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .. import data_path
from .exceptions import CommandRenderError
from .models import (
    ActionSpec,
    AdapterPassthrough,
    CommandSource,
    TargetsSpec,
)

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_SUPPORTED_REGIMES = frozenset({"user-invoked"})


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
    return _build_source(meta, body=body, path=path, layer=layer)


def _build_source(
    meta: dict[str, Any], *, body: str, path: Path, layer: str
) -> CommandSource:
    for required in ("name", "description", "regime"):
        if required not in meta:
            raise CommandRenderError(
                f"Command source {path} missing required key: {required!r}"
            )

    regime = str(meta["regime"])
    if regime not in _SUPPORTED_REGIMES:
        raise CommandRenderError(
            f"Unsupported regime {regime!r} in {path}; "
            f"expected one of {sorted(_SUPPORTED_REGIMES)}"
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

    return CommandSource(
        name=str(meta["name"]),
        description=str(meta["description"]),
        regime=regime,
        scope_default=scope_default,
        targets=targets,
        action=action,
        body=body,
        argument_hint=argument_hint,
        adapters=adapters,
        overrides=overrides,
        source_path=path,
        layer=layer,
    )


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
