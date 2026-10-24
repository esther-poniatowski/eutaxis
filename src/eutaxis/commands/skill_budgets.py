"""Measure Skill entrypoints and declared loading units."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..instructions.models import InstructionConfig, SkillLoadingUnit
from .adapters import AgentAdapter
from .exceptions import CommandRenderError
from .models import CommandSource, RenderedArtifact
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
    source_by_module = _sources_by_module(config, sources)
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
        )
        for loading_unit in config.skill_loading_units
    )
    return tuple(measurements)


def _sources_by_module(
    config: InstructionConfig, sources: list[CommandSource]
) -> dict[str, CommandSource]:
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


def _entrypoint_measurement(
    module_id: str,
    artifact: RenderedArtifact,
    adapter_name: str,
    limit: int | None,
) -> SkillBudgetMeasurement:
    entrypoint = _artifact_file(artifact, ENTRYPOINT_FILENAME)
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
) -> SkillBudgetMeasurement:
    loading_unit_by_name = {item.name: item for item in loading_units}
    files = _loading_unit_files(
        loading_unit,
        loading_unit_by_name,
        rendered,
        adapter_name,
    )
    return SkillBudgetMeasurement(
        kind="loading-unit",
        name=loading_unit.name,
        adapter=adapter_name,
        byte_size=sum(_byte_size(content) for content in files.values()),
        byte_budget=loading_unit.max_bytes,
        files=tuple(files),
    )


def _loading_unit_files(
    loading_unit: SkillLoadingUnit,
    loading_units: dict[str, SkillLoadingUnit],
    rendered: dict[str, RenderedArtifact],
    adapter_name: str,
) -> dict[str, str]:
    files: dict[str, str] = {}
    for included_name in loading_unit.includes:
        files.update(
            _loading_unit_files(
                loading_units[included_name],
                loading_units,
                rendered,
                adapter_name,
            )
        )
    for member in loading_unit.members:
        try:
            artifact = rendered[member.module]
        except KeyError as exc:
            raise CommandRenderError(
                f"Skill loading unit {loading_unit.name!r} references module "
                f"{member.module!r}, which does not target adapter "
                f"{adapter_name!r}"
            ) from exc
        if member.include_entrypoint:
            entrypoint_path = f"{member.module}/{ENTRYPOINT_FILENAME}"
            files[entrypoint_path] = _artifact_file(
                artifact, ENTRYPOINT_FILENAME
            )
        for rule in member.rules:
            relative_path = f"rules/{rule}.md"
            files[f"{member.module}/{relative_path}"] = _artifact_file(
                artifact, relative_path
            )
    return files


def _artifact_file(artifact: RenderedArtifact, relative_path: str) -> str:
    for artifact_file in artifact.files:
        if artifact_file.relative_path == relative_path:
            return artifact_file.content
    raise CommandRenderError(
        f"Rendered Skill {artifact.name!r} for {artifact.adapter!r} has no "
        f"file {relative_path!r}; declare only rules emitted by progressive "
        "disclosure"
    )


def _byte_size(content: str) -> int:
    return len(content.encode("utf-8"))
