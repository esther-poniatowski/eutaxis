"""Public-result tests for authenticated external declaration acquisition."""

from __future__ import annotations

import copy
import os
import pickle
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import MappingProxyType

import pytest

import eutaxis.declarations as declarations_api
import eutaxis.declarations.composite_facets as composite_module
import eutaxis.declarations.external_result as result_module
from eutaxis.declarations import (
    AcquisitionKind,
    AcquisitionSourceCoordinate,
    ExternalAcquisitionResult,
    acquire_external_declarations,
    acquire_external_declarations_from_path,
)
from eutaxis.declarations._external_evidence import _EVIDENCE_AUTHORITIES
from eutaxis.declarations.acquisition_contract import PACKAGED_DECLARATION_PATHS
from eutaxis.declarations.byte_carriers import (
    _trusted_directory_from_workspace_path,
)
from eutaxis.declarations.exceptions import AcquisitionContractError
from eutaxis.declarations.external_acquisition import (
    _acquire_external_stage_from_path,
    _STAGE_AUTHORITIES,
    _issued_external_stage_state,
    _retire_stage_tree,
)
from eutaxis.declarations.external_result import (
    _RESULT_AUTHORITIES,
    _issue_external_result,
    _issued_external_result_state,
)
from eutaxis.declarations.external_registry import (
    _EXTERNAL_REGISTRY_AUTHORITIES,
    _build_external_declaration_registry,
    _issue_external_declaration_registry,
    _retire_external_registry,
)
from tests.test_external_acquisition import (
    _build_git_workspace,
    _declaration_source,
    _write_contract,
    _write_multi_contract,
)


def _acquire(tmp_path: Path) -> ExternalAcquisitionResult:
    """Acquire one valid workspace contract through the public path boundary."""
    manifest_path, lock_path = _write_contract(tmp_path)
    return acquire_external_declarations_from_path(
        str(tmp_path),
        manifest_path,
        lock_path,
    )


def _nested_authorities(stage):
    """Return the nested authority objects retained by one issued stage."""
    state = _issued_external_stage_state(stage)
    composite_state = composite_module._COMPOSITE_AUTHORITIES.state(state.composite)
    return (
        state,
        composite_state.provenance,
        state.evidence,
    )


def test_public_result_retains_exact_contract_and_portable_coordinates(
    tmp_path: Path,
) -> None:
    result = _acquire(tmp_path)
    state = _issued_external_result_state(result)

    assert result.manifest is state.evidence_state.manifest
    assert result.lock is state.evidence_state.lock
    assert result.facet_registry is state.stage_state.composite
    assert not hasattr(result, "registry")
    assert result.source_coordinates is state.source_coordinates
    assert tuple(item.namespace for item in result.source_coordinates) == (
        ("eutaxis",) * len(PACKAGED_DECLARATION_PATHS) + ("oikos",)
    )
    assert tuple(item.path for item in result.source_coordinates) == (
        PACKAGED_DECLARATION_PATHS + ("declarations/process-core.yaml",)
    )
    assert all(item.sha256.startswith("sha256:") for item in result.source_coordinates)
    assert tuple(source for source, _coordinate in state.source_map) == (
        state.stage_state.declarations
    )


def test_capability_entrypoint_leaves_the_caller_workspace_open(
    tmp_path: Path,
) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))
    try:
        result = acquire_external_declarations(workspace, manifest_path, lock_path)
        with workspace.retain_directory("."):
            pass
    finally:
        workspace.close()

    assert isinstance(result, ExternalAcquisitionResult)


def test_path_entrypoint_closes_every_descriptor(tmp_path: Path) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    baseline = len(os.listdir("/dev/fd"))

    acquire_external_declarations_from_path(
        str(tmp_path),
        manifest_path,
        lock_path,
    )

    assert len(os.listdir("/dev/fd")) == baseline


def test_mixed_sources_and_multiple_files_preserve_logical_order(
    tmp_path: Path,
) -> None:
    mixed_root = tmp_path / "mixed"
    mixed_root.mkdir()
    manifest_path, lock_path = _write_multi_contract(
        mixed_root,
        specs=(
            ("alpha", AcquisitionKind.WORKSPACE, "."),
            ("beta", AcquisitionKind.VENDORED, "vendor/beta"),
        ),
        extension_order=("beta", "alpha"),
    )
    mixed = acquire_external_declarations_from_path(
        str(mixed_root), manifest_path, lock_path
    )
    external = mixed.source_coordinates[len(PACKAGED_DECLARATION_PATHS) :]
    assert tuple((item.namespace, item.path) for item in external) == (
        ("alpha", "declarations/process-core.yaml"),
        ("beta", "declarations/process-core.yaml"),
    )

    files_root = tmp_path / "files"
    first = _declaration_source("oikos")
    second = first.replace(b"oikos/reader-purpose", b"oikos/second-purpose")
    manifest_path, lock_path = _write_contract(
        files_root,
        declaration_files=(
            ("declarations/z-first.yaml", first),
            ("declarations/a-second.yaml", second),
        ),
    )
    multiple = acquire_external_declarations_from_path(
        str(files_root), manifest_path, lock_path
    )
    external = multiple.source_coordinates[len(PACKAGED_DECLARATION_PATHS) :]
    assert tuple(item.path for item in external) == (
        "declarations/z-first.yaml",
        "declarations/a-second.yaml",
    )


def test_portable_coordinates_are_transport_independent(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace-kind"
    vendored_root = tmp_path / "vendored-kind"
    git_root = tmp_path / "git-kind"
    workspace_root.mkdir()
    vendored_root.mkdir()
    git_root.mkdir()

    workspace_paths = _write_contract(workspace_root)
    workspace = acquire_external_declarations_from_path(
        str(workspace_root), *workspace_paths
    )
    vendored_paths = _write_contract(
        vendored_root,
        kind=AcquisitionKind.VENDORED,
        root="vendor/oikos",
    )
    vendored = acquire_external_declarations_from_path(
        str(vendored_root), *vendored_paths
    )
    git_workspace, git_locks = _build_git_workspace(
        git_root,
        (("oikos", "vendor/oikos", True),),
    )
    git_paths = _write_contract(
        git_workspace,
        kind=AcquisitionKind.GIT_SUBMODULE,
        root="vendor/oikos",
        git=git_locks["oikos"],
    )
    git_result = acquire_external_declarations_from_path(str(git_workspace), *git_paths)

    assert workspace.source_coordinates == vendored.source_coordinates
    assert workspace.source_coordinates == git_result.source_coordinates
    assert workspace.facet_registry.content_revision == (
        vendored.facet_registry.content_revision
    )
    assert workspace.facet_registry.content_revision == (
        git_result.facet_registry.content_revision
    )
    assert workspace.lock.sources[0].content_revision == (
        vendored.lock.sources[0].content_revision
    )
    assert workspace.lock.sources[0].content_revision == (
        git_result.lock.sources[0].content_revision
    )
    assert (
        len(
            {
                workspace.lock.sources[0].acquisition_revision,
                vendored.lock.sources[0].acquisition_revision,
                git_result.lock.sources[0].acquisition_revision,
            }
        )
        == 3
    )
    for result in (workspace, vendored, git_result):
        for coordinate in result.source_coordinates:
            assert not coordinate.path.startswith("/")
            assert "vendor/oikos" not in coordinate.path
            assert str(tmp_path) not in coordinate.path


def test_public_boundary_exports_only_the_result_surface() -> None:
    for name in (
        "AcquisitionSourceCoordinate",
        "ExternalAcquisitionResult",
        "acquire_external_declarations",
        "acquire_external_declarations_from_path",
    ):
        assert getattr(declarations_api, name) is not None
    for name in (
        "ExternalAcquisitionStage",
        "build_external_declaration_registry",
        "issued_external_result_state",
        "retire_external_result_tree",
    ):
        assert not hasattr(declarations_api, name)


def test_result_rejects_construction_subclass_copy_and_serialization() -> None:
    with pytest.raises(TypeError, match="must be issued"):
        ExternalAcquisitionResult()
    with pytest.raises(TypeError, match="cannot be subclassed"):

        class _DerivedResult(ExternalAcquisitionResult):
            pass

    forged = object.__new__(ExternalAcquisitionResult)
    with pytest.raises(AcquisitionContractError, match="not issued"):
        _issued_external_result_state(forged)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(forged)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.deepcopy(forged)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(forged)


def test_result_rejects_registry_mutation(tmp_path: Path) -> None:
    result = _acquire(tmp_path)
    state = _issued_external_result_state(result)
    object.__setattr__(state.external_registry_state.registry, "paths", ())

    with pytest.raises(AcquisitionContractError, match="registry state changed"):
        _issued_external_result_state(result)


@pytest.mark.parametrize("omission", ("records", "families", "conflicts", "equal"))
def test_result_issuer_rejects_unissued_registry_variants(
    tmp_path: Path,
    omission: str,
) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    stage = _acquire_external_stage_from_path(str(tmp_path), manifest_path, lock_path)
    try:
        registry = _build_external_declaration_registry(stage)
        if omission == "records":
            supplied = replace(registry, records=MappingProxyType({}))
        elif omission == "families":
            supplied = replace(registry, families=MappingProxyType({}))
        elif omission == "conflicts":
            supplied = replace(registry, conflicts=frozenset())
        else:
            supplied = replace(registry)

        with pytest.raises(
            AcquisitionContractError, match="registry result.*not issued"
        ):
            _issue_external_result(stage, supplied)  # type: ignore[arg-type]
    finally:
        _retire_stage_tree(stage)


def test_result_issuer_rejects_registry_from_another_stage(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first_paths = _write_contract(first_root)
    second_paths = _write_contract(second_root)
    first = _acquire_external_stage_from_path(str(first_root), *first_paths)
    second = _acquire_external_stage_from_path(str(second_root), *second_paths)
    issued_registry = _issue_external_declaration_registry(first)
    try:
        with pytest.raises(AcquisitionContractError, match="another stage"):
            _issue_external_result(second, issued_registry)
    finally:
        _retire_external_registry(issued_registry)
        _retire_stage_tree(first)
        _retire_stage_tree(second)


def test_result_rejects_coordinate_mutation(tmp_path: Path) -> None:
    result = _acquire(tmp_path)
    coordinate = result.source_coordinates[-1]
    object.__setattr__(coordinate, "namespace", "forged")

    with pytest.raises(AcquisitionContractError, match="coordinate state changed"):
        _issued_external_result_state(result)


@pytest.mark.parametrize("field", ("path", "sha256"))
def test_result_rejects_other_coordinate_field_mutations(
    tmp_path: Path,
    field: str,
) -> None:
    result = _acquire(tmp_path)
    coordinate = result.source_coordinates[-1]
    value = "forged.yaml" if field == "path" else "sha256:" + "0" * 64
    object.__setattr__(coordinate, field, value)

    with pytest.raises(AcquisitionContractError, match="coordinate state changed"):
        _issued_external_result_state(result)


def test_result_rejects_coordinate_tuple_and_source_map_substitution(
    tmp_path: Path,
) -> None:
    first = _acquire(tmp_path / "first")
    first_state = _issued_external_result_state(first)
    equal_coordinates = tuple(
        AcquisitionSourceCoordinate(item.namespace, item.path, item.sha256)
        for item in first_state.source_coordinates
    )
    _RESULT_AUTHORITIES.issue(
        first,
        first_state._replace(source_coordinates=equal_coordinates),
    )
    with pytest.raises(AcquisitionContractError, match="coordinate state changed"):
        _issued_external_result_state(first)

    second = _acquire(tmp_path / "second")
    second_state = _issued_external_result_state(second)
    spliced_map = (
        (second_state.source_map[0][0], second_state.source_map[1][1]),
        *second_state.source_map[1:],
    )
    _RESULT_AUTHORITIES.issue(second, second_state._replace(source_map=spliced_map))
    with pytest.raises(
        AcquisitionContractError, match="differs from acquired evidence"
    ):
        _issued_external_result_state(second)


@pytest.mark.parametrize(
    "target", ("manifest", "lock", "composite", "constituent", "declaration", "records")
)
def test_result_boundary_rechecks_nested_authority(
    tmp_path: Path,
    target: str,
) -> None:
    result = _acquire(tmp_path)
    state = _issued_external_result_state(result)
    if target == "manifest":
        object.__setattr__(result.manifest, "schema_version", 2)
    elif target == "lock":
        object.__setattr__(result.lock, "schema_version", 2)
    elif target == "composite":
        object.__setattr__(result.facet_registry, "content_revision", "changed")
    elif target == "constituent":
        constituent = result.facet_registry.authority_for("oikos.enabled")
        object.__setattr__(constituent, "source_revision", "changed")
    elif target == "declaration":
        object.__setattr__(
            state.stage_state.declarations[-1].declaration,
            "id",
            "oikos/changed",
        )
    else:
        registry = state.external_registry_state.registry
        object.__setattr__(
            registry, "records", MappingProxyType(dict(registry.records))
        )

    with pytest.raises(AcquisitionContractError):
        _issued_external_result_state(result)


def test_registry_failure_retires_the_complete_stage_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    original_acquire = result_module._acquire_external_stage_from_path
    retained = []

    def acquire(*args, **kwargs):
        stage = original_acquire(*args, **kwargs)
        retained.append((stage, *_nested_authorities(stage)))
        return stage

    def reject(_stage):
        raise RuntimeError("injected registry failure")

    monkeypatch.setattr(result_module, "_acquire_external_stage_from_path", acquire)
    monkeypatch.setattr(result_module, "_issue_external_declaration_registry", reject)

    with pytest.raises(RuntimeError, match="registry failure"):
        acquire_external_declarations_from_path(
            str(tmp_path),
            manifest_path,
            lock_path,
        )

    stage, state, provenance, evidence = retained[0]
    assert _STAGE_AUTHORITIES.state(stage) is None
    assert composite_module._COMPOSITE_AUTHORITIES.state(state.composite) is None
    assert composite_module._FACET_PROVENANCE_AUTHORITIES.state(provenance) is None
    assert _EVIDENCE_AUTHORITIES.state(evidence) is None


def test_interrupted_result_publication_retires_every_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    original_issue = _RESULT_AUTHORITIES.issue
    attempted = []

    def interrupt(result, state):
        original_issue(result, state)
        stage_state, provenance, evidence = _nested_authorities(state.stage)
        attempted.append(
            (
                result,
                state.external_registry,
                state.stage,
                stage_state,
                provenance,
                evidence,
            )
        )
        raise KeyboardInterrupt("injected result publication interruption")

    monkeypatch.setattr(_RESULT_AUTHORITIES, "issue", interrupt)

    with pytest.raises(KeyboardInterrupt, match="publication interruption"):
        acquire_external_declarations_from_path(
            str(tmp_path),
            manifest_path,
            lock_path,
        )

    result, external_registry, stage, stage_state, provenance, evidence = attempted[0]
    assert _RESULT_AUTHORITIES.state(result) is None
    assert _EXTERNAL_REGISTRY_AUTHORITIES.state(external_registry) is None
    assert _STAGE_AUTHORITIES.state(stage) is None
    assert composite_module._COMPOSITE_AUTHORITIES.state(stage_state.composite) is None
    assert composite_module._FACET_PROVENANCE_AUTHORITIES.state(provenance) is None
    assert _EVIDENCE_AUTHORITIES.state(evidence) is None


def test_interrupted_registry_publication_retires_every_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    original_issue = _EXTERNAL_REGISTRY_AUTHORITIES.issue
    attempted = []

    def interrupt(result, state):
        original_issue(result, state)
        stage_state, provenance, evidence = _nested_authorities(state.stage)
        attempted.append((result, state.stage, stage_state, provenance, evidence))
        raise KeyboardInterrupt("injected registry publication interruption")

    monkeypatch.setattr(_EXTERNAL_REGISTRY_AUTHORITIES, "issue", interrupt)

    with pytest.raises(KeyboardInterrupt, match="publication interruption"):
        acquire_external_declarations_from_path(str(tmp_path), manifest_path, lock_path)

    result, stage, stage_state, provenance, evidence = attempted[0]
    assert _EXTERNAL_REGISTRY_AUTHORITIES.state(result) is None
    assert _STAGE_AUTHORITIES.state(stage) is None
    assert composite_module._COMPOSITE_AUTHORITIES.state(stage_state.composite) is None
    assert composite_module._FACET_PROVENANCE_AUTHORITIES.state(provenance) is None
    assert _EVIDENCE_AUTHORITIES.state(evidence) is None


@pytest.mark.parametrize(
    ("error_type", "message"),
    (
        (RuntimeError, "authentication failure"),
        (KeyboardInterrupt, "authentication interruption"),
    ),
)
def test_initial_result_authentication_failure_retires_every_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[BaseException],
    message: str,
) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    original_authenticate = result_module._issued_external_result_state
    attempted = []

    def reject(result):
        state = original_authenticate(result)
        stage_state, provenance, evidence = _nested_authorities(state.stage)
        attempted.append(
            (
                result,
                state.external_registry,
                state.stage,
                stage_state,
                provenance,
                evidence,
            )
        )
        raise error_type(message)

    monkeypatch.setattr(result_module, "_issued_external_result_state", reject)

    with pytest.raises(error_type, match=message):
        acquire_external_declarations_from_path(str(tmp_path), manifest_path, lock_path)

    result, external_registry, stage, stage_state, provenance, evidence = attempted[0]
    assert _RESULT_AUTHORITIES.state(result) is None
    assert _EXTERNAL_REGISTRY_AUTHORITIES.state(external_registry) is None
    assert _STAGE_AUTHORITIES.state(stage) is None
    assert composite_module._COMPOSITE_AUTHORITIES.state(stage_state.composite) is None
    assert composite_module._FACET_PROVENANCE_AUTHORITIES.state(provenance) is None
    assert _EVIDENCE_AUTHORITIES.state(evidence) is None


@pytest.mark.parametrize(
    ("error_type", "message"),
    (
        (RuntimeError, "later authentication failure"),
        (KeyboardInterrupt, "later authentication interruption"),
    ),
)
def test_later_result_authentication_failure_retires_every_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[BaseException],
    message: str,
) -> None:
    result = _acquire(tmp_path)
    state = _issued_external_result_state(result)
    stage_state, provenance, evidence = _nested_authorities(state.stage)

    def reject(_result):
        raise error_type(message)

    monkeypatch.setattr(result_module, "_authenticate_external_result_state", reject)

    with pytest.raises(error_type, match=message):
        _issued_external_result_state(result)

    assert _RESULT_AUTHORITIES.state(result) is None
    assert _EXTERNAL_REGISTRY_AUTHORITIES.state(state.external_registry) is None
    assert _STAGE_AUTHORITIES.state(state.stage) is None
    assert composite_module._COMPOSITE_AUTHORITIES.state(stage_state.composite) is None
    assert composite_module._FACET_PROVENANCE_AUTHORITIES.state(provenance) is None
    assert _EVIDENCE_AUTHORITIES.state(evidence) is None


def test_caller_workspace_survives_result_publication_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, lock_path = _write_contract(tmp_path)
    workspace = _trusted_directory_from_workspace_path(str(tmp_path))

    def reject(_result):
        raise RuntimeError("injected publication failure")

    monkeypatch.setattr(result_module, "_issued_external_result_state", reject)
    try:
        with pytest.raises(RuntimeError, match="publication failure"):
            acquire_external_declarations(workspace, manifest_path, lock_path)
        with workspace.retain_directory("."):
            pass
    finally:
        workspace.close()


def test_coordinate_class_is_frozen_value_data() -> None:
    coordinate = AcquisitionSourceCoordinate(
        "owner", "rules.yaml", "sha256:" + "0" * 64
    )
    with pytest.raises(FrozenInstanceError):
        coordinate.namespace = "changed"  # type: ignore[misc]
