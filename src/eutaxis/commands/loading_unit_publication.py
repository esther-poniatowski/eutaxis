"""Publish budgeted loading units inside an existing Agent Skill artifact."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

from ..instructions.loading_units import expand_loading_unit
from ..instructions.models import InstructionConfig, SkillLoadingUnit
from .adapters import AgentAdapter
from .exceptions import CommandRenderError
from .models import (
    AdapterPassthrough,
    CommandSource,
    RenderedArtifact,
)
from .rendering import ENTRYPOINT_FILENAME, OWNED_FRONTMATTER_KEY, render_command

ROUTE_DIRECTORY = "routes"
ROUTE_INDEX_MARKER = "<!-- eutaxis:published-loading-routes -->"


@dataclass(frozen=True)
class LoadingUnitPublication:
    """One generated route manifest and its exact selected content."""

    name: str
    owner_module: str
    owner: str
    adapter: str
    route_path: str
    batch_paths: tuple[str, ...]
    batch_units: tuple[str, ...]
    batch_digests: tuple[str, ...]
    content_files: tuple[str, ...]
    content_bytes: int
    delivery_bytes: int
    closure_digest: str


def prepare_published_loading_units(
    config: InstructionConfig,
    sources: list[CommandSource],
    adapters: list[AgentAdapter],
    *,
    project_root: Path,
    home: Path,
) -> tuple[list[CommandSource], tuple[LoadingUnitPublication, ...]]:
    """Attach generated route manifests to their configured owner Skills.

    The loading-unit graph remains the sole authority for route membership.
    The returned sources render through the ordinary Skill installer, so the
    owner artifact's hash and ownership sidecar cover every manifest.
    """
    published = tuple(
        unit for unit in config.skill_loading_units if unit.publish_to is not None
    )
    if not published:
        return sources, ()

    by_module = sources_by_module(config, sources)
    indexed = _append_route_indexes(by_module, published)
    generated_by_owner: dict[tuple[str, str], dict[str, str]] = {}
    publications: list[LoadingUnitPublication] = []

    for adapter in adapters:
        rendered = {
            module_id: render_command(
                source,
                adapter,
                project_root=project_root,
                home=home,
            )
            for module_id, source in indexed.items()
            if source.targets.admits(adapter.name)
        }
        for unit in published:
            assert unit.publish_to is not None
            owner_module = unit.publish_to
            if owner_module not in rendered:
                continue
            owner = rendered[owner_module].name
            route_path = f"{ROUTE_DIRECTORY}/{unit.name}.md"
            content = loading_unit_files(
                unit,
                config.skill_loading_units,
                rendered,
                adapter.name,
            )
            batches = _included_batches(unit, config.skill_loading_units)
            generated: dict[str, str] = {}
            batch_paths: list[str] = []
            batch_digests: list[str] = []
            for batch in batches:
                batch_path = f"{ROUTE_DIRECTORY}/batches/{batch.name}.md"
                batch_paths.append(batch_path)
                batch_content = loading_unit_files(
                    batch,
                    config.skill_loading_units,
                    rendered,
                    adapter.name,
                )
                batch_digests.append(_closure_digest(batch_content))
                generated[batch_path] = _format_batch_manifest(
                    batch,
                    owner=owner,
                    path=batch_path,
                    adapter=adapter,
                    files=batch_content,
                )
            generated[route_path] = _format_route_manifest(
                unit,
                owner=owner,
                path=route_path,
                adapter=adapter,
                files=content,
                batches=tuple(zip(batches, batch_paths, strict=True)),
            )
            owner_files = generated_by_owner.setdefault(
                (owner_module, adapter.name), {}
            )
            owner_identities = {
                _path_identity(existing_path): existing_path
                for existing_path in owner_files
            }
            for relative_path, manifest in generated.items():
                identity = _path_identity(relative_path)
                prior_path = owner_identities.get(identity)
                if prior_path is not None and prior_path != relative_path:
                    raise CommandRenderError(
                        f"Published loading units emit case-equivalent paths "
                        f"inside {owner!r}: {prior_path!r} and {relative_path!r}"
                    )
                existing = owner_files.get(relative_path)
                if existing is not None and existing != manifest:
                    raise CommandRenderError(
                        f"Published loading units emit different content at "
                        f"{owner}/{relative_path} for adapter {adapter.name!r}"
                    )
                owner_files[relative_path] = manifest
                owner_identities[identity] = relative_path

            publications.append(
                LoadingUnitPublication(
                    name=unit.name,
                    owner_module=owner_module,
                    owner=owner,
                    adapter=adapter.name,
                    route_path=route_path,
                    batch_paths=tuple(batch_paths),
                    batch_units=tuple(batch.name for batch in batches),
                    batch_digests=tuple(batch_digests),
                    content_files=tuple(content),
                    content_bytes=sum(_byte_size(value) for value in content.values()),
                    delivery_bytes=sum(
                        _byte_size(value) for value in generated.values()
                    ),
                    closure_digest=_closure_digest(content),
                )
            )

    prepared = dict(indexed)
    for (owner_module, adapter_name), generated in generated_by_owner.items():
        source = prepared[owner_module]
        passthrough = source.adapters.get(adapter_name, AdapterPassthrough())
        authored_by_identity = {
            _path_identity(path): path for path in passthrough.files
        }
        collisions = sorted(
            (
                authored_by_identity[_path_identity(path)],
                path,
            )
            for path in generated
            if _path_identity(path) in authored_by_identity
        )
        if collisions:
            raise CommandRenderError(
                f"Published loading units collide with authored files in Skill "
                f"{source.name!r} for adapter {adapter_name!r}: {collisions}"
            )
        adapters_map = dict(source.adapters)
        adapters_map[adapter_name] = replace(
            passthrough,
            files={**passthrough.files, **generated},
        )
        prepared[owner_module] = replace(source, adapters=adapters_map)

    return (
        [prepared[module.id] for module in config.task_modules],
        tuple(publications),
    )


def sources_by_module(
    config: InstructionConfig, sources: list[CommandSource]
) -> dict[str, CommandSource]:
    """Correlate configured task-module identifiers with loaded sources."""
    by_path = {source.source_path.resolve(): source for source in sources}
    resolved: dict[str, CommandSource] = {}
    for module in config.task_modules:
        path = config.resolve(module.path).resolve()
        try:
            resolved[module.id] = by_path[path]
        except KeyError as exc:
            raise CommandRenderError(
                f"No loaded Skill source corresponds to task module "
                f"{module.id!r} at {path}"
            ) from exc
    return resolved


def loading_unit_files(
    loading_unit: SkillLoadingUnit,
    loading_units: list[SkillLoadingUnit],
    rendered: dict[str, RenderedArtifact],
    adapter_name: str,
) -> dict[str, str]:
    """Return the ordered, deduplicated rendered files selected by one unit."""
    files: dict[str, str] = {}
    for member in expand_loading_unit(loading_unit, loading_units):
        try:
            artifact = rendered[member.module]
        except KeyError as exc:
            raise CommandRenderError(
                f"Skill loading unit {loading_unit.name!r} references module "
                f"{member.module!r}, which does not target adapter "
                f"{adapter_name!r}"
            ) from exc
        if member.include_entrypoint:
            path = f"{artifact.name}/{ENTRYPOINT_FILENAME}"
            files[path] = artifact_file(artifact, ENTRYPOINT_FILENAME)
        for rule in member.rules:
            relative_path = f"rules/{rule}.md"
            files[f"{artifact.name}/{relative_path}"] = artifact_file(
                artifact, relative_path
            )
    return files


def artifact_file(artifact: RenderedArtifact, relative_path: str) -> str:
    """Return one rendered file or reject a loading-unit declaration gap."""
    for candidate in artifact.files:
        if candidate.relative_path == relative_path:
            return candidate.content
    raise CommandRenderError(
        f"Rendered Skill {artifact.name!r} for {artifact.adapter!r} has no "
        f"file {relative_path!r}; declare only rules emitted by progressive "
        "disclosure"
    )


def _append_route_indexes(
    by_module: dict[str, CommandSource],
    published: tuple[SkillLoadingUnit, ...],
) -> dict[str, CommandSource]:
    indexed = dict(by_module)
    by_owner: dict[str, list[SkillLoadingUnit]] = {}
    for unit in published:
        assert unit.publish_to is not None
        by_owner.setdefault(unit.publish_to, []).append(unit)
    for owner, units in by_owner.items():
        source = indexed[owner]
        if ROUTE_INDEX_MARKER in source.body:
            raise CommandRenderError(
                f"Skill {owner!r} contains the reserved route-index marker"
            )
        lines = [
            "## Published loading routes",
            ROUTE_INDEX_MARKER,
            "",
            "Each generated manifest names the exact installed files for one bounded route.",
            "",
            *(f"- [`{unit.name}`]({ROUTE_DIRECTORY}/{unit.name}.md)" for unit in units),
        ]
        body = f"{source.body.rstrip()}\n\n" + "\n".join(lines) + "\n"
        indexed[owner] = replace(source, body=body)
    return indexed


def _included_batches(
    unit: SkillLoadingUnit, loading_units: list[SkillLoadingUnit]
) -> tuple[SkillLoadingUnit, ...]:
    """Return the leaf read batches included by one published route."""
    by_name = {candidate.name: candidate for candidate in loading_units}
    ordered: list[SkillLoadingUnit] = []
    seen: set[str] = set()

    def append(name: str) -> None:
        if name in seen:
            return
        child = by_name[name]
        for nested in child.includes:
            append(nested)
        seen.add(name)
        if not child.includes:
            ordered.append(child)

    for included in unit.includes:
        append(included)
    return tuple(ordered)


def _format_route_manifest(
    unit: SkillLoadingUnit,
    *,
    owner: str,
    path: str,
    adapter: AgentAdapter,
    files: dict[str, str],
    batches: tuple[tuple[SkillLoadingUnit, str], ...],
) -> str:
    lines = [
        f"# `{unit.name}`",
        "",
        "This generated manifest identifies the bounded installed route selected by the workflow.",
        "",
        f"- Adapter: `{adapter.name}`",
        f"- Content bytes: `{sum(_byte_size(value) for value in files.values())}`",
        f"- Closure digest: `{_closure_digest(files)}`",
        "- Digest normalization: generated ownership markers are excluded",
        "",
        "## Ordered batches",
        "",
    ]
    if batches:
        for batch, batch_path in batches:
            link = _relative_link(
                adapter,
                owner=owner,
                from_path=path,
                target_owner=owner,
                target_path=batch_path,
            )
            lines.append(f"- [`{batch.name}`]({link})")
    else:
        lines.append("- This route declares its files directly.")
    lines.extend(["", "## Deduplicated file order", ""])
    lines.extend(_file_links(adapter, owner=owner, from_path=path, files=files))
    return "\n".join(lines) + "\n"


def _format_batch_manifest(
    unit: SkillLoadingUnit,
    *,
    owner: str,
    path: str,
    adapter: AgentAdapter,
    files: dict[str, str],
) -> str:
    lines = [
        f"# `{unit.name}`",
        "",
        "This generated batch manifest identifies one bounded read within a published route.",
        "",
        f"- Adapter: `{adapter.name}`",
        f"- Content bytes: `{sum(_byte_size(value) for value in files.values())}`",
        f"- Closure digest: `{_closure_digest(files)}`",
        "- Digest normalization: generated ownership markers are excluded",
        "",
        "## File order",
        "",
        *_file_links(adapter, owner=owner, from_path=path, files=files),
    ]
    return "\n".join(lines) + "\n"


def _file_links(
    adapter: AgentAdapter,
    *,
    owner: str,
    from_path: str,
    files: dict[str, str],
) -> list[str]:
    links: list[str] = []
    for selected_path in files:
        target_owner, target_path = selected_path.split("/", 1)
        link = _relative_link(
            adapter,
            owner=owner,
            from_path=from_path,
            target_owner=target_owner,
            target_path=target_path,
        )
        links.append(f"1. [`{selected_path}`]({link})")
    return links


def _relative_link(
    adapter: AgentAdapter,
    *,
    owner: str,
    from_path: str,
    target_owner: str,
    target_path: str,
) -> str:
    return adapter.relative_artifact_link(
        from_artifact=owner,
        from_file=from_path,
        to_artifact=target_owner,
        to_file=target_path,
    )


def _closure_digest(files: dict[str, str]) -> str:
    payload = [
        {
            "path": path,
            "sha256": hashlib.sha256(
                _digest_content(path, content).encode("utf-8")
            ).hexdigest(),
        }
        for path, content in files.items()
    ]
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _byte_size(content: str) -> int:
    return len(content.encode("utf-8"))


def _digest_content(path: str, content: str) -> str:
    """Remove the owner hash that recursively covers generated manifests."""
    if not path.endswith(f"/{ENTRYPOINT_FILENAME}"):
        return content
    prefix = f"{OWNED_FRONTMATTER_KEY}:"
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        return content
    closing = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.rstrip("\r\n") == "---"
        ),
        None,
    )
    if closing is None:
        return content
    return "".join(
        line
        for index, line in enumerate(lines)
        if not (0 < index < closing and line.startswith(prefix))
    )


def _path_identity(path: str) -> str:
    """Return the cross-platform collision identity of one artifact path."""
    normalized = unicodedata.normalize("NFC", PurePosixPath(path).as_posix())
    return normalized.casefold()
