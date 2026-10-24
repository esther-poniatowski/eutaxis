"""Tests for deterministic cumulative composition planning."""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from typing import Mapping, cast

import pytest
import yaml

from eutaxis.declarations import (
    CompositionError,
    CumulativeArtifact,
    CumulativeCompositionPlan,
    DeclarationRegistryError,
    PlannedComponent,
    ResolvedCompilationUnit,
    ResolvedComponent,
    ResolvedDependency,
    assemble_cumulative_artifact,
    load_declaration_registry,
    load_facet_registry,
    plan_cumulative_composition,
)
from eutaxis.declarations.composition import _issue_resolved_compilation_unit

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "composition" / "cumulative"


def _registry(root: Path = FIXTURE_ROOT):
    paths = tuple(
        path
        for path in sorted(root.glob("*.yaml"))
        if path.name != "context-facets.yaml"
    )
    return load_declaration_registry(
        paths, load_facet_registry(root / "context-facets.yaml")
    )


def _mutable_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "cumulative"
    shutil.copytree(FIXTURE_ROOT, target)
    return target


def _fragments() -> dict[str, str]:
    return {
        "fixture/a-peer": "# Peer π e\u0301  ",
        "fixture/z-base": "# Base\nKeep two spaces here  \nNext",
        "fixture/dependant": "# Dependant",
        "fixture/member": "# Member",
        "fixture/a-independent": "# Independent  ",
    }


class _ReadOnceMapping(Mapping[str, str]):
    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = dict(values)
        self.read_counts = {key: 0 for key in values}

    def __getitem__(self, key: str) -> str:
        self.read_counts[key] += 1
        if self.read_counts[key] > 1:
            raise RuntimeError(f"caller mapping value read twice: {key}")
        return self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


def _unit(
    *,
    components: tuple[ResolvedComponent, ...] | None = None,
    dependencies: tuple[ResolvedDependency, ...] | None = None,
    manifest: str = "fixture/cumulative",
) -> ResolvedCompilationUnit:
    if components is None:
        components = (
            ResolvedComponent("core", "fixture/dependant", 0),
            ResolvedComponent("core", "fixture/a-peer", 0),
            ResolvedComponent("core", "fixture/z-base", 0),
            ResolvedComponent("core", "fixture/member", 1),
            ResolvedComponent("additional", "fixture/a-independent", 2),
        )
    if dependencies is None:
        dependencies = (
            ResolvedDependency("fixture/a-peer", "fixture/dependant"),
            ResolvedDependency("fixture/z-base", "fixture/dependant"),
        )
    return _issue_resolved_compilation_unit(manifest, components, dependencies)


def test_multi_component_plan_accepts_dependency_closure_and_is_repeatable() -> None:
    registry = _registry()
    unit = _unit()
    reversed_unit = _issue_resolved_compilation_unit(
        unit.manifest, tuple(reversed(unit.components)), unit.dependencies
    )

    first = plan_cumulative_composition(registry, unit)
    second = plan_cumulative_composition(registry, reversed_unit)

    assert first == second
    assert first.manifest == "fixture/cumulative"
    assert first.scope == "project"
    assert first.target == "AGENTS.md"
    assert first.components == (
        PlannedComponent(section="core", declaration="fixture/a-peer"),
        PlannedComponent(section="core", declaration="fixture/z-base"),
        PlannedComponent(section="core", declaration="fixture/dependant"),
        PlannedComponent(section="core", declaration="fixture/member"),
        PlannedComponent(section="additional", declaration="fixture/a-independent"),
    )


@pytest.mark.parametrize("mechanism", ["separate-directory", "single-slot"])
def test_cumulative_planner_rejects_other_manifest_mechanisms(
    tmp_path: Path, mechanism: str
) -> None:
    root = _mutable_fixture(tmp_path)
    path = root / "manifest.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["mechanism"] = mechanism
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    with pytest.raises(CompositionError) as captured:
        plan_cumulative_composition(_registry(root), _unit())

    assert captured.value.location == "$.mechanism"
    assert captured.value.path == path.resolve()
    assert captured.value.line == next(
        index
        for index, line in enumerate(path.read_text().splitlines(), 1)
        if line.startswith("mechanism:")
    )
    assert f"{mechanism!r} is not cumulative" in str(captured.value)


def test_cumulative_assembly_is_byte_identical_and_preserves_fragments() -> None:
    plan = plan_cumulative_composition(_registry(), _unit())
    fragments = _fragments()
    reversed_fragments = dict(reversed(tuple(fragments.items())))

    first = assemble_cumulative_artifact(plan, fragments)
    second = assemble_cumulative_artifact(plan, reversed_fragments)

    assert first == second
    assert first.manifest == "fixture/cumulative"
    assert first.scope == "project"
    assert first.target == "AGENTS.md"
    assert first.content == (
        "# Peer π e\u0301  \n\n"
        "# Base\nKeep two spaces here  \nNext\n\n"
        "# Dependant\n\n"
        "# Member\n\n"
        "# Independent  \n"
    ).encode("utf-8")
    assert b"e\xcc\x81  \n\n# Base" in first.content
    assert first.text.endswith("# Independent  \n")


def test_cumulative_assembly_snapshots_the_fragment_mapping() -> None:
    plan = plan_cumulative_composition(_registry(), _unit())
    fragments = _ReadOnceMapping(_fragments())

    artifact = assemble_cumulative_artifact(plan, fragments)

    assert artifact == assemble_cumulative_artifact(plan, _fragments())
    assert set(fragments.read_counts.values()) == {1}


def test_native_scopes_remain_distinct_for_the_same_target() -> None:
    registry = _registry()
    project = assemble_cumulative_artifact(
        plan_cumulative_composition(registry, _unit()), _fragments()
    )
    personal_unit = _unit(
        manifest="fixture/personal",
        components=(ResolvedComponent("core", "fixture/a-independent", 0),),
        dependencies=(),
    )
    personal = assemble_cumulative_artifact(
        plan_cumulative_composition(registry, personal_unit),
        {"fixture/a-independent": "# Personal"},
    )

    artifacts = {
        (artifact.scope, artifact.target): artifact for artifact in (project, personal)
    }

    assert len(artifacts) == 2
    assert project.target == personal.target == "AGENTS.md"
    assert project.scope == "project"
    assert personal.scope == "personal"
    assert project.manifest != personal.manifest


def test_empty_cumulative_plan_emits_no_synthetic_newline() -> None:
    plan = plan_cumulative_composition(
        _registry(), _unit(components=(), dependencies=())
    )

    artifact = assemble_cumulative_artifact(plan, {})

    assert artifact.content == b""
    assert artifact.text == ""


def test_cumulative_assembly_requires_an_exact_fragment_key_set() -> None:
    plan = plan_cumulative_composition(_registry(), _unit())
    missing = _fragments()
    del missing["fixture/z-base"]
    del missing["fixture/a-independent"]
    with pytest.raises(CompositionError) as captured_missing:
        assemble_cumulative_artifact(plan, missing)
    assert captured_missing.value.location == '$.fragments["fixture/z-base"]'
    assert "missing projected fragment" in str(captured_missing.value)

    extras = _fragments()
    extras["fixture/z-extra"] = "# Z"
    extras["fixture/a-extra"] = "# A"
    with pytest.raises(CompositionError) as captured_extra:
        assemble_cumulative_artifact(plan, extras)
    assert captured_extra.value.location == '$.fragments["fixture/a-extra"]'
    assert "unplanned projected fragment" in str(captured_extra.value)


@pytest.mark.parametrize(
    ("fragment", "message"),
    [
        (42, "must be text"),
        ("", "must not be empty"),
        (" \t", "must not be empty"),
        ("# Peer\r\nbody", "must use LF newlines"),
        ("\n# Peer", "must not have a boundary newline"),
        ("# Peer\n", "must not have a boundary newline"),
        ("# Peer \ud800", "not valid UTF-8 text"),
    ],
)
def test_cumulative_assembly_rejects_noncanonical_fragments(
    fragment: object, message: str
) -> None:
    plan = plan_cumulative_composition(_registry(), _unit())
    fragments: dict[str, object] = {
        identifier: content for identifier, content in _fragments().items()
    }
    fragments["fixture/a-peer"] = fragment

    with pytest.raises(CompositionError) as captured:
        assemble_cumulative_artifact(plan, cast(Mapping[str, str], fragments))

    assert captured.value.location == '$.fragments["fixture/a-peer"]'
    assert message in str(captured.value)


def test_resolved_substitute_can_satisfy_an_absent_authored_dependency() -> None:
    unit = _unit(
        manifest="fixture/substitution",
        components=(
            ResolvedComponent("core", "fixture/dependant", 0),
            ResolvedComponent("core", "fixture/a-peer", 0),
            ResolvedComponent("core", "fixture/substitute", 0),
            ResolvedComponent("core", "fixture/blocker", 1),
            ResolvedComponent("core", "fixture/member", 2),
            ResolvedComponent("additional", "fixture/a-independent", 3),
        ),
        dependencies=(
            ResolvedDependency("fixture/a-peer", "fixture/dependant"),
            ResolvedDependency("fixture/substitute", "fixture/dependant"),
        ),
    )

    plan = plan_cumulative_composition(_registry(), unit)

    assert [component.declaration for component in plan.components] == [
        "fixture/a-peer",
        "fixture/substitute",
        "fixture/dependant",
        "fixture/blocker",
        "fixture/member",
        "fixture/a-independent",
    ]


def test_equal_rank_components_use_stable_identifier_tie_break() -> None:
    plan = plan_cumulative_composition(_registry(), _unit())

    assert [component.declaration for component in plan.components[:2]] == [
        "fixture/a-peer",
        "fixture/z-base",
    ]


def test_duplicate_manifest_membership_fails_at_the_later_position(
    tmp_path: Path,
) -> None:
    root = _mutable_fixture(tmp_path)
    path = root / "manifest.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["sections"][1]["declarations"].append("fixture/dependant")
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    with pytest.raises(DeclarationRegistryError) as captured:
        _registry(root)
    assert captured.value.location == "$.sections[1].declarations[1]"
    assert captured.value.path == path.resolve()
    assert "duplicate manifest selection" in str(captured.value)


@pytest.mark.parametrize(
    ("components", "location", "message"),
    [
        (
            (
                ResolvedComponent("core", "fixture/dependant", 0),
                ResolvedComponent("core", "fixture/dependant", 0),
            ),
            "$.components[1].declaration",
            "duplicate effective declaration",
        ),
        (
            (ResolvedComponent("core", "fixture/missing", 0),),
            "$.components[0].declaration",
            "unknown effective declaration",
        ),
        (
            (ResolvedComponent("core", "fixture/cumulative", 0),),
            "$.components[0].declaration",
            "is not content",
        ),
        (
            (ResolvedComponent("missing", "fixture/dependant", 0),),
            "$.components[0].section",
            "unknown manifest section",
        ),
        (
            (ResolvedComponent("core", "fixture/dependant", 1),),
            "$.components[0]",
            "retain its manifest anchor",
        ),
        (
            (ResolvedComponent("core", "fixture/z-base", 3),),
            "$.components[0]",
            "do not identify one manifest anchor",
        ),
        (
            (ResolvedComponent("additional", "fixture/z-base", 0),),
            "$.components[0]",
            "do not identify one manifest anchor",
        ),
    ],
)
def test_resolved_components_require_valid_unique_anchors(
    components: tuple[ResolvedComponent, ...], location: str, message: str
) -> None:
    with pytest.raises(CompositionError) as captured:
        plan_cumulative_composition(
            _registry(), _unit(components=components, dependencies=())
        )
    assert captured.value.location == location
    assert message in str(captured.value)


def test_direct_manifest_anchor_wins_over_a_derived_candidate() -> None:
    components = (ResolvedComponent("core", "fixture/a-independent", 0),)

    with pytest.raises(CompositionError) as captured:
        plan_cumulative_composition(
            _registry(), _unit(components=components, dependencies=())
        )

    assert captured.value.location == "$.components[0]"
    assert "retain its manifest anchor" in str(captured.value)


@pytest.mark.parametrize(
    ("dependency", "location"),
    [
        (
            ResolvedDependency("fixture/missing", "fixture/dependant"),
            "$.dependencies[0].prerequisite",
        ),
        (
            ResolvedDependency("fixture/z-base", "fixture/missing"),
            "$.dependencies[0].dependant",
        ),
    ],
)
def test_resolved_dependency_endpoints_must_be_effective(
    dependency: ResolvedDependency, location: str
) -> None:
    with pytest.raises(CompositionError) as captured:
        plan_cumulative_composition(_registry(), _unit(dependencies=(dependency,)))
    assert captured.value.location == location


def test_resolved_compilation_unit_requires_resolver_issuance() -> None:
    with pytest.raises(TypeError, match="issued by semantic resolution"):
        ResolvedCompilationUnit("fixture/cumulative", (), ())
    with pytest.raises(TypeError, match="issued by semantic resolution"):
        replace(_unit(), dependencies=())


def test_cumulative_plan_requires_planner_issuance() -> None:
    with pytest.raises(TypeError, match="issued by the composition planner"):
        CumulativeCompositionPlan("fixture/cumulative", "project", "AGENTS.md", ())
    plan = plan_cumulative_composition(_registry(), _unit())
    with pytest.raises(TypeError, match="issued by the composition planner"):
        replace(plan, components=())


def test_cumulative_artifact_requires_assembler_issuance() -> None:
    with pytest.raises(TypeError, match="issued by the cumulative assembler"):
        CumulativeArtifact("fixture/cumulative", "project", "AGENTS.md", b"")
    artifact = assemble_cumulative_artifact(
        plan_cumulative_composition(_registry(), _unit()), _fragments()
    )
    with pytest.raises(TypeError, match="issued by the cumulative assembler"):
        replace(artifact, content=b"forged")


def test_duplicate_and_cyclic_resolved_dependencies_fail() -> None:
    dependency = ResolvedDependency("fixture/z-base", "fixture/dependant")
    with pytest.raises(CompositionError) as duplicate:
        plan_cumulative_composition(
            _registry(), _unit(dependencies=(dependency, dependency))
        )
    assert duplicate.value.location == "$.dependencies[1].dependant"

    cycle = (
        dependency,
        ResolvedDependency("fixture/dependant", "fixture/z-base"),
    )
    with pytest.raises(CompositionError) as cyclic:
        plan_cumulative_composition(_registry(), _unit(dependencies=cycle))
    assert cyclic.value.location == "$.dependencies"


def test_backward_cross_section_dependency_is_rejected() -> None:
    dependency = ResolvedDependency("fixture/a-independent", "fixture/dependant")
    with pytest.raises(CompositionError) as captured:
        plan_cumulative_composition(_registry(), _unit(dependencies=(dependency,)))
    assert captured.value.location == "$.dependencies[0]"
    assert "cannot follow" in str(captured.value)


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        ("fixture/missing", "unknown composition manifest"),
        ("fixture/dependant", "is not a composition manifest"),
    ],
)
def test_missing_and_wrong_kind_manifests_are_distinct(
    manifest: str, message: str
) -> None:
    with pytest.raises(CompositionError) as captured:
        plan_cumulative_composition(_registry(), _unit(manifest=manifest))
    assert captured.value.location == "$.manifest"
    assert message in str(captured.value)
