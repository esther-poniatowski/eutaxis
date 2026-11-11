"""Build deterministic intermediate plans for cumulative artifacts."""

from __future__ import annotations

import heapq
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import NoReturn, cast

from .exceptions import CompositionError
from .models import (
    CompositionMechanism,
    CompositionManifestDeclaration,
    ProcedureDeclaration,
    RuleDeclaration,
    RuleSetDeclaration,
)
from .registry import DeclarationRegistry, RegisteredDeclaration
from .resolution import (
    ResolvedCompilationUnit,
    ResolvedComponent,
    ResolvedDependency,
)
from .source import DocumentPath, format_document_path, nearest_location


@dataclass(frozen=True)
class PlannedComponent:
    """One selected declaration at its ordered artifact position."""

    section: str
    declaration: str


@dataclass(frozen=True, init=False)
class CumulativeCompositionPlan:
    """Planner-issued component order for one cumulative artifact."""

    manifest: str
    scope: str
    target: str
    components: tuple[PlannedComponent, ...]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Reject construction outside the composition planner."""
        raise TypeError(
            "CumulativeCompositionPlan instances must be issued by the composition planner"
        )


@dataclass(frozen=True, init=False)
class CumulativeArtifact:
    """Assembler-issued cumulative artifact with canonical bytes."""

    manifest: str
    scope: str
    target: str
    content: bytes

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Reject construction outside the cumulative assembler."""
        raise TypeError(
            "CumulativeArtifact instances must be issued by the cumulative assembler"
        )

    @property
    def text(self) -> str:
        """Decode the canonical bytes as strict UTF-8."""
        return self.content.decode("utf-8", errors="strict")


def _issue_cumulative_composition_plan(
    manifest: str,
    scope: str,
    target: str,
    components: tuple[PlannedComponent, ...],
) -> CumulativeCompositionPlan:
    """Issue one plan after composition validation and ordering."""
    plan = object.__new__(CumulativeCompositionPlan)
    object.__setattr__(plan, "manifest", manifest)
    object.__setattr__(plan, "scope", scope)
    object.__setattr__(plan, "target", target)
    object.__setattr__(plan, "components", components)
    return plan


def _issue_cumulative_artifact(
    manifest: str,
    scope: str,
    target: str,
    content: bytes,
) -> CumulativeArtifact:
    """Issue one artifact after fragment validation and assembly."""
    artifact = object.__new__(CumulativeArtifact)
    object.__setattr__(artifact, "manifest", manifest)
    object.__setattr__(artifact, "scope", scope)
    object.__setattr__(artifact, "target", target)
    object.__setattr__(artifact, "content", content)
    return artifact


def plan_cumulative_composition(
    registry: DeclarationRegistry,
    unit: ResolvedCompilationUnit,
) -> CumulativeCompositionPlan:
    """Order one resolved compilation unit without revisiting its semantics."""
    record = registry.records.get(unit.manifest)
    if record is None:
        raise CompositionError(
            "$.manifest",
            f"unknown composition manifest {unit.manifest!r}",
        )
    if not isinstance(record.declaration, CompositionManifestDeclaration):
        raise CompositionError(
            "$.manifest",
            f"record {unit.manifest!r} is not a composition manifest",
        )
    manifest = cast(CompositionManifestDeclaration, record.declaration)
    if manifest.mechanism is not CompositionMechanism.CUMULATIVE:
        _raise_record_error(
            record,
            ("mechanism",),
            f"manifest mechanism {manifest.mechanism.value!r} is not cumulative",
        )
    manifest_selections = _index_selections(registry, record, manifest)
    components = _index_resolved_components(
        registry, manifest, manifest_selections, unit
    )
    _validate_rule_projections(registry, unit, components)
    dependencies = _index_resolved_dependencies(unit, components)
    section_order = {
        section.id: index for index, section in enumerate(manifest.sections)
    }
    order = _stable_dependency_order(components, dependencies, section_order)
    return _issue_cumulative_composition_plan(
        manifest.id,
        manifest.scope,
        manifest.target,
        tuple(
            PlannedComponent(
                section=components[identifier].section,
                declaration=identifier,
            )
            for identifier in order
        ),
    )


def assemble_cumulative_artifact(
    plan: CumulativeCompositionPlan,
    fragments: Mapping[str, str],
) -> CumulativeArtifact:
    """Join one closed set of projected fragments in planned order."""
    fragment_map = dict(fragments)
    fragment_ids = tuple(fragment_map)
    if any(not isinstance(identifier, str) for identifier in fragment_ids):
        raise CompositionError("$.fragments", "fragment identifiers must be strings")
    planned_ids = tuple(component.declaration for component in plan.components)
    planned_set = set(planned_ids)
    for identifier in planned_ids:
        if identifier not in fragment_map:
            raise CompositionError(
                _fragment_location(identifier),
                f"missing projected fragment {identifier!r}",
            )
    extras = sorted(
        identifier for identifier in fragment_ids if identifier not in planned_set
    )
    if extras:
        identifier = extras[0]
        raise CompositionError(
            _fragment_location(identifier),
            f"unplanned projected fragment {identifier!r}",
        )

    blocks: list[bytes] = []
    for identifier in planned_ids:
        location = _fragment_location(identifier)
        fragment = fragment_map[identifier]
        if not isinstance(fragment, str):
            raise CompositionError(location, "projected fragment must be text")
        if not fragment.strip():
            raise CompositionError(location, "projected fragment must not be empty")
        if "\r" in fragment:
            raise CompositionError(location, "projected fragment must use LF newlines")
        if fragment.startswith("\n") or fragment.endswith("\n"):
            raise CompositionError(
                location,
                "projected fragment must not have a boundary newline",
            )
        try:
            blocks.append(fragment.encode("utf-8", errors="strict"))
        except UnicodeEncodeError as error:
            raise CompositionError(
                location, "projected fragment is not valid UTF-8 text"
            ) from error

    content = b"\n\n".join(blocks)
    if content:
        content += b"\n"
    return _issue_cumulative_artifact(
        plan.manifest,
        plan.scope,
        plan.target,
        content,
    )


def _fragment_location(identifier: str) -> str:
    """Return a stable diagnostic location for one opaque identifier."""
    return f"$.fragments[{json.dumps(identifier, ensure_ascii=False)}]"


def _index_resolved_components(
    registry: DeclarationRegistry,
    manifest: CompositionManifestDeclaration,
    manifest_selections: dict[str, ResolvedComponent],
    unit: ResolvedCompilationUnit,
) -> dict[str, ResolvedComponent]:
    """Validate resolver-assigned anchors without restricting closure records."""
    sections = {section.id for section in manifest.sections}
    anchors = {
        (selection.section, selection.rank)
        for selection in manifest_selections.values()
    }
    components: dict[str, ResolvedComponent] = {}
    for index, component in enumerate(unit.components):
        base = f"$.components[{index}]"
        if component.declaration in components:
            raise CompositionError(
                f"{base}.declaration",
                f"duplicate effective declaration {component.declaration!r}",
            )
        registered = registry.records.get(component.declaration)
        if registered is None:
            raise CompositionError(
                f"{base}.declaration",
                f"unknown effective declaration {component.declaration!r}",
            )
        if not isinstance(
            registered.declaration,
            (RuleDeclaration, ProcedureDeclaration),
        ):
            raise CompositionError(
                f"{base}.declaration",
                f"effective declaration {component.declaration!r} is not content",
            )
        if component.section not in sections:
            raise CompositionError(
                f"{base}.section",
                f"unknown manifest section {component.section!r}",
            )
        if component.rank < 0:
            raise CompositionError(
                f"{base}.rank", "manifest anchor rank must be non-negative"
            )
        if (component.section, component.rank) not in anchors:
            raise CompositionError(
                base,
                "section and rank do not identify one manifest anchor",
            )
        authored = manifest_selections.get(component.declaration)
        if authored is not None and (
            component.section != authored.section or component.rank != authored.rank
        ):
            raise CompositionError(
                base,
                f"authored declaration {component.declaration!r} must retain its manifest anchor",
            )
        components[component.declaration] = component
    return components


def _validate_rule_projections(
    registry: DeclarationRegistry,
    unit: ResolvedCompilationUnit,
    components: dict[str, ResolvedComponent],
) -> None:
    """Validate the resolver's final local norm and criterion projections."""
    projections: dict[str, int] = {}
    for index, projection in enumerate(unit.rule_projections):
        base = f"$.rule_projections[{index}]"
        if projection.declaration not in components:
            raise CompositionError(
                f"{base}.declaration",
                f"unknown projected rule {projection.declaration!r}",
            )
        declaration = registry.records[projection.declaration].declaration
        if not isinstance(declaration, RuleDeclaration):
            raise CompositionError(
                f"{base}.declaration",
                f"procedure {projection.declaration!r} cannot have a rule projection",
            )
        if projection.declaration in projections:
            raise CompositionError(
                f"{base}.declaration",
                f"duplicate projection for rule {projection.declaration!r}",
            )
        projections[projection.declaration] = index
        _validate_projection_identifiers(
            base,
            "norms",
            projection.norms,
            tuple(norm.id for norm in declaration.norms),
        )
        _validate_projection_identifiers(
            base,
            "criteria",
            projection.criteria,
            tuple(criterion.id for criterion in declaration.criteria),
        )

    for identifier, component in components.items():
        declaration = registry.records[identifier].declaration
        if isinstance(declaration, RuleDeclaration) and identifier not in projections:
            raise CompositionError(
                "$.rule_projections",
                f"missing projection for rule {identifier!r}",
            )


def _validate_projection_identifiers(
    base: str,
    field: str,
    selected: tuple[str, ...],
    authored: tuple[str, ...],
) -> None:
    """Require unique local identifiers in their authored subsequence order."""
    singular = {"norms": "norm", "criteria": "criterion"}[field]
    authored_positions = {
        identifier: index for index, identifier in enumerate(authored)
    }
    seen: set[str] = set()
    previous_position = -1
    for index, identifier in enumerate(selected):
        location = f"{base}.{field}[{index}]"
        position = authored_positions.get(identifier)
        if position is None:
            raise CompositionError(
                location,
                f"unknown local {singular} identifier {identifier!r}",
            )
        if identifier in seen:
            raise CompositionError(location, f"duplicate {singular} identifier")
        if position <= previous_position:
            raise CompositionError(
                location,
                f"{field} must follow authored order",
            )
        seen.add(identifier)
        previous_position = position


def _index_selections(
    registry: DeclarationRegistry,
    record: RegisteredDeclaration,
    manifest: CompositionManifestDeclaration,
) -> dict[str, ResolvedComponent]:
    """Index effective declarations in manifest and rule-set authored order."""
    direct: dict[str, ResolvedComponent] = {}
    expanded: dict[str, ResolvedComponent] = {}
    seen: set[str] = set()
    rank = 0
    for section_index, section in enumerate(manifest.sections):
        for item_index, identifier in enumerate(section.declarations):
            path = ("sections", section_index, "declarations", item_index)
            if identifier in seen:
                _raise_record_error(
                    record,
                    path,
                    f"declaration {identifier!r} appears in more than one manifest position",
                )
            seen.add(identifier)
            declaration = registry.records[identifier].declaration
            if isinstance(declaration, RuleSetDeclaration):
                for member_offset, rule in enumerate(declaration.rules):
                    selection = ResolvedComponent(
                        section=section.id,
                        declaration=rule.id,
                        rank=rank + member_offset,
                    )
                    prior = expanded.get(rule.id)
                    if prior is None or selection.rank < prior.rank:
                        expanded[rule.id] = selection
                rank += len(declaration.rules)
            else:
                direct[identifier] = ResolvedComponent(
                    section=section.id,
                    declaration=identifier,
                    rank=rank,
                )
                rank += 1
    return {**expanded, **direct}


def _index_resolved_dependencies(
    unit: ResolvedCompilationUnit,
    components: dict[str, ResolvedComponent],
) -> tuple[ResolvedDependency, ...]:
    """Validate the dependency graph supplied by semantic resolution."""
    seen: set[tuple[str, str]] = set()
    dependencies: list[ResolvedDependency] = []
    for index, dependency in enumerate(unit.dependencies):
        base = f"$.dependencies[{index}]"
        if dependency.prerequisite not in components:
            raise CompositionError(
                f"{base}.prerequisite",
                f"unknown prerequisite {dependency.prerequisite!r}",
            )
        if dependency.dependant not in components:
            raise CompositionError(
                f"{base}.dependant",
                f"unknown dependant {dependency.dependant!r}",
            )
        edge = (dependency.prerequisite, dependency.dependant)
        if edge in seen:
            raise CompositionError(f"{base}.dependant", "duplicate resolved dependency")
        seen.add(edge)
        dependencies.append(dependency)
    return tuple(dependencies)


def _stable_dependency_order(
    components: dict[str, ResolvedComponent],
    dependencies: tuple[ResolvedDependency, ...],
    section_order: dict[str, int],
) -> tuple[str, ...]:
    """Topologically order dependencies with manifest position as the tie-break."""
    dependants: dict[str, list[str]] = {identifier: [] for identifier in components}
    indegree: dict[str, int] = {identifier: 0 for identifier in components}
    for index, dependency in enumerate(dependencies):
        prerequisite = components[dependency.prerequisite]
        dependant = components[dependency.dependant]
        if section_order[prerequisite.section] > section_order[dependant.section]:
            raise CompositionError(
                f"$.dependencies[{index}]",
                "a prerequisite cannot follow its dependant's manifest section",
            )
        dependants[dependency.prerequisite].append(dependency.dependant)
        indegree[dependency.dependant] += 1

    available = [
        (selection.rank, identifier)
        for identifier, selection in components.items()
        if indegree[identifier] == 0
    ]
    heapq.heapify(available)
    ordered: list[str] = []
    while available:
        _, identifier = heapq.heappop(available)
        ordered.append(identifier)
        for dependant_id in sorted(
            dependants[identifier],
            key=lambda item: (components[item].rank, item),
        ):
            indegree[dependant_id] -= 1
            if indegree[dependant_id] == 0:
                dependant = components[dependant_id]
                heapq.heappush(available, (dependant.rank, dependant_id))
    if len(ordered) != len(components):
        raise CompositionError(
            "$.dependencies", "resolved dependencies contain a cycle"
        )
    return tuple(ordered)


def _raise_record_error(
    record: RegisteredDeclaration,
    parts: DocumentPath,
    message: str,
    *,
    absolute: bool = False,
) -> NoReturn:
    """Raise one composition error at the source field that owns it."""
    path = parts if absolute else record.root + parts
    source = nearest_location(record.source.locations, path)
    raise CompositionError(
        format_document_path(path),
        message,
        path=record.source.path,
        line=source.line if source else None,
        column=source.column if source else None,
    )
