"""Combined-registry tests for the private external acquisition stage."""

from __future__ import annotations

from pathlib import Path

import pytest

import eutaxis.declarations as declarations_api
import eutaxis.declarations.external_registry as external_registry_module
from eutaxis.declarations.exceptions import (
    AcquisitionContractError,
    DeclarationRegistryError,
)
from eutaxis.declarations.external_acquisition import (
    _ExternalAcquisitionStage,
    _acquire_external_stage_from_path,
    _issued_external_stage_state,
    _retire_stage_tree,
)
from eutaxis.declarations.external_registry import (
    _build_external_declaration_registry,
)
from tests.test_external_acquisition import _declaration_source, _write_contract


def _acquire(tmp_path: Path, source: bytes) -> _ExternalAcquisitionStage:
    """Acquire one external source through the complete retained-byte boundary."""
    manifest_path, lock_path = _write_contract(
        tmp_path,
        declaration_bytes=source,
    )
    return _acquire_external_stage_from_path(
        str(tmp_path),
        manifest_path,
        lock_path,
    )


def test_combined_registry_reuses_the_issued_stage_without_reloading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage = _acquire(tmp_path, _declaration_source("oikos"))
    state = _issued_external_stage_state(stage)

    def reject_reload(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("combined registry reloaded a declaration path")

    monkeypatch.setattr(
        "eutaxis.declarations.registry.load_declaration_source",
        reject_reload,
    )

    registry = _build_external_declaration_registry(stage)

    assert registry.facet_registry is state.composite
    assert registry.paths == tuple(source.path for source in state.declarations)
    assert registry.records["oikos/reader-purpose"].source is state.declarations[-1]
    assert "eutaxis/manual-judgment" in registry.families


def test_combined_registry_rejects_a_duplicate_at_the_later_source(
    tmp_path: Path,
) -> None:
    source = _declaration_source("oikos")
    manifest_path, lock_path = _write_contract(
        tmp_path,
        declaration_files=(
            ("declarations/z-first.yaml", source),
            ("declarations/a-second.yaml", source),
        ),
    )
    stage = _acquire_external_stage_from_path(
        str(tmp_path),
        manifest_path,
        lock_path,
    )

    with pytest.raises(
        DeclarationRegistryError,
        match="duplicate declaration id 'oikos/reader-purpose'",
    ) as raised:
        _build_external_declaration_registry(stage)

    assert raised.value.path == Path("declarations/a-second.yaml")
    assert raised.value.location == "$.id"


def test_combined_registry_rejects_an_unknown_relation_target(tmp_path: Path) -> None:
    source = _declaration_source("oikos").replace(
        b"relations: []",
        b"relations: [{type: requires, target: oikos/missing}]",
    )
    stage = _acquire(tmp_path, source)

    with pytest.raises(
        DeclarationRegistryError,
        match="unknown effective content declaration 'oikos/missing'",
    ) as raised:
        _build_external_declaration_registry(stage)

    assert raised.value.location == "$.relations[0].target"


@pytest.mark.parametrize(
    ("reference", "location", "message"),
    [
        (
            b"eutaxis/manual-judgment, version: 2",
            "$.criteria[0].evaluator.version",
            "unknown contract version",
        ),
        (
            b"eutaxis/load-declaration-registry, version: 1",
            "$.criteria[0].evaluator.id",
            "is not an evaluator",
        ),
    ],
)
def test_combined_registry_enforces_exact_version_and_kind(
    tmp_path: Path,
    reference: bytes,
    location: str,
    message: str,
) -> None:
    source = _declaration_source("oikos").replace(
        b"eutaxis/manual-judgment, version: 1",
        reference,
    )
    stage = _acquire(tmp_path, source)

    with pytest.raises(DeclarationRegistryError, match=message) as raised:
        _build_external_declaration_registry(stage)

    assert raised.value.location == location


def test_external_registry_builder_remains_private() -> None:
    assert not hasattr(declarations_api, "build_external_declaration_registry")


def test_external_registry_builder_rejects_forged_and_retired_stages(
    tmp_path: Path,
) -> None:
    forged = object.__new__(_ExternalAcquisitionStage)
    with pytest.raises(AcquisitionContractError, match="not issued"):
        _build_external_declaration_registry(forged)

    stage = _acquire(tmp_path, _declaration_source("oikos"))
    _retire_stage_tree(stage)
    with pytest.raises(AcquisitionContractError, match="not issued"):
        _build_external_declaration_registry(stage)


def test_external_registry_builder_reauthenticates_after_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage = _acquire(tmp_path, _declaration_source("oikos"))
    original = external_registry_module._build_declaration_registry_from_sources

    def mutate_after_build(sources, facets):
        registry = original(sources, facets)
        object.__setattr__(sources[-1].declaration, "id", "oikos/mutated")
        return registry

    monkeypatch.setattr(
        external_registry_module,
        "_build_declaration_registry_from_sources",
        mutate_after_build,
    )

    with pytest.raises(
        AcquisitionContractError,
        match="parsed declaration state changed",
    ):
        _build_external_declaration_registry(stage)


def test_external_registry_builder_reauthenticates_after_build_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage = _acquire(tmp_path, _declaration_source("oikos"))
    primary = RuntimeError("injected registry failure")

    def mutate_then_fail(sources, _facets):
        object.__setattr__(sources[-1].declaration, "id", "oikos/mutated")
        raise primary

    monkeypatch.setattr(
        external_registry_module,
        "_build_declaration_registry_from_sources",
        mutate_then_fail,
    )

    with pytest.raises(
        AcquisitionContractError,
        match="parsed declaration state changed",
    ) as raised:
        _build_external_declaration_registry(stage)

    assert raised.value.__cause__ is primary
