"""Measure Skill entrypoints and declared loading units."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..instructions.loading_units import expand_loading_unit
from ..instructions.models import InstructionConfig, SkillLoadingUnit
from .adapters import AgentAdapter
from .models import CommandSource, RenderedArtifact
from .loading_unit_publication import (
    LoadingUnitPublication,
    artifact_file,
    loading_unit_files,
    prepare_published_loading_units,
    sources_by_module,
)
from .rendering import ENTRYPOINT_FILENAME, render_command


@dataclass(frozen=True)
class SkillBudgetMeasurement:
    """One measured Skill entrypoint or loading unit."""

    kind: str
    name: str
    adapter: str
    byte_size: int
    byte_budget: int | None
    files: tuple[str, ...]
    publication_owners: tuple[str, ...] = ()

    @property
    def over_budget(self) -> bool:
        """Return whether the measured size exceeds its configured budget."""
        return self.byte_budget is not None and self.byte_size > self.byte_budget


def measure_skill_budgets(
    config: InstructionConfig,
    sources: list[CommandSource],
    adapter: AgentAdapter,
    *,
    project_root: Path,
    home: Path,
) -> tuple[SkillBudgetMeasurement, ...]:
    """Measure every rendered entrypoint and declared loading unit."""
    prepared, publications = prepare_published_loading_units(
        config,
        sources,
        [adapter],
        project_root=project_root,
        home=home,
    )
    source_by_module = sources_by_module(config, prepared)
    rendered = {
        module_id: render_command(
            source,
            adapter,
            project_root=project_root,
            home=home,
        )
        for module_id, source in source_by_module.items()
        if source.targets.admits(adapter.name)
    }

    measurements = [
        _entrypoint_measurement(
            module_id,
            artifact,
            adapter.name,
            config.skill_entrypoint_max_bytes,
        )
        for module_id, artifact in sorted(rendered.items())
    ]
    measurements.extend(
        _loading_unit_measurement(
            loading_unit,
            config.skill_loading_units,
            rendered,
            adapter.name,
            publications,
        )
        for loading_unit in config.skill_loading_units
        if all(
            member.module in rendered
            for member in expand_loading_unit(loading_unit, config.skill_loading_units)
        )
    )
    return tuple(measurements)


def _entrypoint_measurement(
    module_id: str,
    artifact: RenderedArtifact,
    adapter_name: str,
    limit: int | None,
) -> SkillBudgetMeasurement:
    entrypoint = artifact_file(artifact, ENTRYPOINT_FILENAME)
    return SkillBudgetMeasurement(
        kind="entrypoint",
        name=module_id,
        adapter=adapter_name,
        byte_size=_byte_size(entrypoint),
        byte_budget=limit,
        files=(f"{module_id}/{ENTRYPOINT_FILENAME}",),
    )


def _loading_unit_measurement(
    loading_unit: SkillLoadingUnit,
    loading_units: list[SkillLoadingUnit],
    rendered: dict[str, RenderedArtifact],
    adapter_name: str,
    publications: tuple[LoadingUnitPublication, ...],
) -> SkillBudgetMeasurement:
    files = loading_unit_files(
        loading_unit,
        loading_units,
        rendered,
        adapter_name,
    )
    publication = next(
        (
            candidate
            for candidate in publications
            if candidate.name == loading_unit.name and candidate.adapter == adapter_name
        ),
        None,
    )
    published_owners = (
        {loading_unit.publish_to} if loading_unit.publish_to is not None else set()
    )
    delivery_variants: list[dict[str, str]] = []
    if publication is not None:
        owner = rendered[publication.owner_module]
        route_files: dict[str, str] = {}
        for relative_path in (
            publication.route_path,
            *publication.batch_paths,
        ):
            route_files[f"{publication.owner}/{relative_path}"] = artifact_file(
                owner, relative_path
            )
        delivery_variants.append(route_files)
    for candidate in publications:
        if loading_unit.name in candidate.batch_units:
            published_owners.add(candidate.owner_module)
            index = candidate.batch_units.index(loading_unit.name)
            owner = rendered[candidate.owner_module]
            relative_path = candidate.batch_paths[index]
            delivery_variants.append(
                {
                    f"{candidate.owner}/{relative_path}": artifact_file(
                        owner, relative_path
                    )
                }
            )
    if delivery_variants:
        selected_variant = max(
            delivery_variants,
            key=lambda variant: (
                sum(_byte_size(content) for content in variant.values()),
                tuple(variant),
            ),
        )
        files.update(selected_variant)
    return SkillBudgetMeasurement(
        kind="loading-unit",
        name=loading_unit.name,
        adapter=adapter_name,
        byte_size=sum(_byte_size(content) for content in files.values()),
        byte_budget=loading_unit.max_bytes,
        files=tuple(files),
        publication_owners=tuple(sorted(published_owners)),
    )


def _byte_size(content: str) -> int:
    return len(content.encode("utf-8"))
