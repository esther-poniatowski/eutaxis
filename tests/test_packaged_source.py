"""Exercise authenticated acquisition of the Eutaxis-owned source corpus."""

from __future__ import annotations

import copy
import hashlib
import os
import pickle
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

import eutaxis.declarations.packaged_source as packaged_module
import eutaxis.declarations.byte_carriers as carrier_module
from eutaxis import data_path
from eutaxis.declarations.acquisition_contract import (
    PACKAGED_DECLARATION_PATHS,
    PACKAGED_FACET_PATH,
    AcquisitionKind,
    AcquisitionLock,
    ExternalSourceLock,
    FacetConstituentLock,
    FacetRegistryLock,
    InternalSourceLock,
    LockedFile,
    composite_facet_content_revision,
    facet_content_revision,
    source_content_revision,
)
from eutaxis.declarations.canonical_json import jcs_bytes
from eutaxis.declarations.byte_carriers import RetainedDirectory, TrustedDirectory
from eutaxis.declarations.exceptions import AcquisitionContractError, ByteCarrierError
from eutaxis.declarations.packaged_source import (
    PackagedInternalSource,
    _acquire_packaged_internal_source_from_root,
    acquire_packaged_internal_source,
)


def _revision(value: object) -> str:
    return "sha256:" + hashlib.sha256(jcs_bytes(value)).hexdigest()


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_lock(root: Path) -> AcquisitionLock:
    facet_sha = _digest(root / PACKAGED_FACET_PATH)
    facet_content = facet_content_revision(
        "eutaxis/context-facets",
        "eutaxis",
        "eutaxis",
        PACKAGED_FACET_PATH,
        facet_sha,
    )
    facet_acquisition = _revision(
        {
            "schema-version": 1,
            "namespace": "eutaxis",
            "kind": "packaged",
            "distribution": "eutaxis",
            "resource-root": "data",
            "path": PACKAGED_FACET_PATH,
            "content-revision": facet_content,
        }
    )
    base = FacetConstituentLock(
        facet_acquisition,
        facet_content,
        "eutaxis/context-facets",
        "packaged",
        "eutaxis",
        "eutaxis",
        PACKAGED_FACET_PATH,
        facet_sha,
    )
    files = tuple(
        LockedFile(path, _digest(root / "declarations" / "v1" / path))
        for path in PACKAGED_DECLARATION_PATHS
    )
    source_content = source_content_revision("eutaxis", files)
    source_acquisition = _revision(
        {
            "schema-version": 1,
            "namespace": "eutaxis",
            "kind": "packaged",
            "distribution": "eutaxis",
            "resource-root": "data/declarations/v1",
            "content-revision": source_content,
        }
    )
    internal = InternalSourceLock(
        source_acquisition,
        source_content,
        files,
        "packaged",
        "eutaxis",
    )
    dummy = ExternalSourceLock(
        "sha256:" + "0" * 64,
        "sha256:" + "1" * 64,
        (LockedFile("rule.yaml", "sha256:" + "2" * 64),),
        AcquisitionKind.WORKSPACE,
        "tests",
        None,
    )
    return AcquisitionLock(
        FacetRegistryLock(
            base,
            composite_facet_content_revision(facet_content, ()),
            (),
        ),
        internal,
        1,
        (dummy,),
    )


def _copy_resources(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    shutil.copytree(data_path(), root)
    return root


def test_packaged_source_retains_verified_resources_in_code_owned_order() -> None:
    root = data_path()
    acquired = acquire_packaged_internal_source(_valid_lock(root))

    assert acquired.facet_document["id"] == "eutaxis/context-facets"
    assert acquired.facet_document["owner"] == "eutaxis"
    assert acquired.facet_registry.id == "eutaxis/context-facets"
    assert acquired.facet_registry.owner == "eutaxis"
    assert (
        tuple(evidence.authoritative.path for evidence in acquired.declaration_evidence)
        == PACKAGED_DECLARATION_PATHS
    )
    assert len(acquired.declaration_documents) == len(PACKAGED_DECLARATION_PATHS)
    assert (
        acquired.facet_evidence.authoritative.data
        == acquired.facet_evidence.verification.data
    )
    assert all(
        evidence.authoritative.data == evidence.verification.data
        for evidence in acquired.declaration_evidence
    )


def test_packaged_session_exposes_ordered_phases(tmp_path: Path) -> None:
    root = _copy_resources(tmp_path)
    base_lock, source_lock = packaged_module._SYSTEM_DEPENDENCIES.validate_lock(
        _valid_lock(root)
    )
    trusted = packaged_module._trusted_directory_from_path(
        root,
        packaged_module._SYSTEM_DEPENDENCIES,
    )
    with trusted:
        with (
            trusted.retain_directory(".") as facet_root,
            trusted.retain_directory("declarations/v1") as declaration_root,
        ):
            session = packaged_module._PackagedAcquisitionSession(
                base_lock,
                source_lock,
                facet_root,
                declaration_root,
                packaged_module._SYSTEM_DEPENDENCIES,
            )
            with pytest.raises(
                AcquisitionContractError,
                match="facet phase must run",
            ):
                session.read_declarations()
            with pytest.raises(
                AcquisitionContractError,
                match="must be read before parsing",
            ):
                session.parse_declarations()
            facet_read = session.read_facet()
            declaration_reads = session.read_declarations()
            with pytest.raises(AcquisitionContractError, match="reads are incomplete"):
                session.verify_and_issue()
            parsed_declarations = session.parse_declarations()
            acquired = session.verify_and_issue()

    assert facet_read.registry is acquired.facet_registry
    assert (
        tuple(carrier.path for carrier in declaration_reads.authoritative)
        == PACKAGED_DECLARATION_PATHS
    )
    assert parsed_declarations.documents == acquired.declaration_documents


def test_packaged_acquirer_verifies_only_after_all_authoritative_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, str, str]] = []
    original_read = RetainedDirectory.read_authoritative
    original_verify = RetainedDirectory.verify

    def recording_read(self: RetainedDirectory, path: str):
        events.append(("read", self.path, path))
        return original_read(self, path)

    def recording_verify(self: RetainedDirectory, carrier):
        events.append(("verify", self.path, carrier.path))
        return original_verify(self, carrier)

    monkeypatch.setattr(RetainedDirectory, "read_authoritative", recording_read)
    monkeypatch.setattr(RetainedDirectory, "verify", recording_verify)

    acquire_packaged_internal_source(_valid_lock(data_path()))

    operations = [event[0] for event in events]
    assert operations == ["read"] * (1 + len(PACKAGED_DECLARATION_PATHS)) + [
        "verify"
    ] * (1 + len(PACKAGED_DECLARATION_PATHS))
    assert events[0][2] == PACKAGED_FACET_PATH
    assert tuple(event[2] for event in events[1:6]) == PACKAGED_DECLARATION_PATHS


def test_packaged_source_parses_only_retained_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = data_path()
    lock = _valid_lock(root)

    def fail_path_read(_path: Path) -> bytes:
        raise AssertionError("path parser was used")

    monkeypatch.setattr(Path, "read_bytes", fail_path_read)
    acquired = acquire_packaged_internal_source(lock)
    assert acquired.facet_document["owner"] == "eutaxis"


def test_packaged_source_rejects_resource_change_after_lock(
    tmp_path: Path,
) -> None:
    root = _copy_resources(tmp_path)
    lock = _valid_lock(root)
    target = root / "declarations" / "v1" / PACKAGED_DECLARATION_PATHS[0]
    target.write_bytes(target.read_bytes() + b"\n")

    with pytest.raises(AcquisitionContractError, match="digest differs") as raised:
        _acquire_packaged_internal_source_from_root(lock, root)
    assert raised.value.location == "$.internal-source.files[0].sha256"


def test_public_acquirer_fails_closed_without_descriptor_support() -> None:
    project = Path(__file__).parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project / "src")
    program = """
import os

for name in ("O_DIRECTORY", "O_CLOEXEC", "O_NOFOLLOW", "O_NONBLOCK"):
    os.__dict__.pop(name, None)
os.supports_dir_fd = set()

def reject_open(*_args, **_kwargs):
    raise AssertionError("descriptor open attempted")

os.open = reject_open

from eutaxis.declarations import (
    AcquisitionContractError,
    acquire_packaged_internal_source,
)

try:
    acquire_packaged_internal_source(object())
except AcquisitionContractError as exc:
    assert exc.location == "$.internal-source"
    assert "descriptor support" in str(exc)
else:
    raise AssertionError("unsupported acquisition did not fail")
"""
    completed = subprocess.run(
        [sys.executable, "-c", program],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_retained_distribution_rejects_path_replacement(
    tmp_path: Path,
) -> None:
    distribution_path = tmp_path / "eutaxis"
    original_root = distribution_path / "data"
    shutil.copytree(data_path(), original_root)
    original_lock = _valid_lock(original_root)
    distribution = packaged_module._trusted_directory_from_path(
        distribution_path,
        packaged_module._SYSTEM_DEPENDENCIES,
    )
    acquirer = packaged_module._build_packaged_source_acquirer(
        distribution,
        packaged_module._acquire_from_retained_roots,
        packaged_module._SYSTEM_DEPENDENCIES,
    )
    retained_path = tmp_path / "retained-eutaxis"
    distribution_path.rename(retained_path)
    replacement_root = distribution_path / "data"
    shutil.copytree(data_path(), replacement_root)
    first = replacement_root / "declarations" / "v1" / PACKAGED_DECLARATION_PATHS[0]
    first.write_text("caller-controlled\n")
    replacement_lock = _valid_lock(replacement_root)

    try:
        with pytest.raises(AcquisitionContractError, match="digest differs"):
            acquirer(replacement_lock)
        acquired = acquirer(original_lock)
        assert acquired.declaration_documents[0] != "caller-controlled"
    finally:
        distribution.close()


@pytest.mark.parametrize(
    ("field", "value"), [("id", "other/facets"), ("owner", "other")]
)
def test_packaged_source_rejects_wrong_base_identity(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    root = _copy_resources(tmp_path)
    target = root / PACKAGED_FACET_PATH
    text = target.read_text()
    old = "eutaxis/context-facets" if field == "id" else "owner: eutaxis"
    replacement = value if field == "id" else f"owner: {value}"
    target.write_text(text.replace(old, replacement, 1))
    lock = _valid_lock(root)

    with pytest.raises(AcquisitionContractError, match=f"facet {field} differs"):
        _acquire_packaged_internal_source_from_root(lock, root)


def test_packaged_source_rejects_symlinked_declaration_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    shutil.copytree(data_path() / "registries", root / "registries")
    (root / "declarations").mkdir()
    (root / "declarations" / "v1").symlink_to(
        data_path() / "declarations" / "v1",
        target_is_directory=True,
    )
    lock = _valid_lock(data_path())

    with pytest.raises(ByteCarrierError):
        _acquire_packaged_internal_source_from_root(lock, root)


def test_packaged_source_rejects_symlinked_data_root(
    tmp_path: Path,
) -> None:
    real_root = _copy_resources(tmp_path)
    linked_root = tmp_path / "data-link"
    linked_root.symlink_to(real_root, target_is_directory=True)
    lock = _valid_lock(real_root)

    with pytest.raises(AcquisitionContractError):
        _acquire_packaged_internal_source_from_root(lock, linked_root)


def test_facet_mutation_during_declaration_reads_fails_final_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _copy_resources(tmp_path)
    lock = _valid_lock(root)
    facet_path = root / PACKAGED_FACET_PATH
    original_read = RetainedDirectory.read_authoritative
    mutated = False

    def mutating_read(self: RetainedDirectory, path: str):
        nonlocal mutated
        if self.path == "declarations/v1" and not mutated:
            mutated = True
            facet_path.write_bytes(facet_path.read_bytes() + b"\n")
        return original_read(self, path)

    monkeypatch.setattr(RetainedDirectory, "read_authoritative", mutating_read)
    with pytest.raises(ByteCarrierError, match="verification"):
        _acquire_packaged_internal_source_from_root(lock, root)


def test_packaged_source_result_is_process_issued_and_immutable() -> None:
    acquired = acquire_packaged_internal_source(_valid_lock(data_path()))
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(acquired)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(acquired)
    with pytest.raises(AttributeError):
        object.__setattr__(acquired, "content_revision", "sha256:" + "0" * 64)
    with pytest.raises(TypeError):
        acquired.facet_document["owner"] = "other"  # type: ignore[index]

    forged = object.__new__(PackagedInternalSource)
    with pytest.raises(AcquisitionContractError, match="not issued"):
        _ = forged.content_revision


def test_bootstrap_close_failure_retires_trusted_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = data_path()
    lock = _valid_lock(root)
    original_issue = carrier_module._TRUSTED_AUTHORITIES.issue
    original_trusted_close = TrustedDirectory.close
    issued: list[TrustedDirectory] = []
    retained_descriptors: list[int] = []
    cleanup_calls = 0

    class InterruptedBootstrapOS:
        O_RDONLY = os.O_RDONLY
        O_DIRECTORY = os.O_DIRECTORY
        O_CLOEXEC = os.O_CLOEXEC
        O_NOFOLLOW = os.O_NOFOLLOW

        def __init__(self) -> None:
            self.bootstrap: int | None = None
            self.injected = False

        def open(self, *args: object, **kwargs: object) -> int:
            descriptor = os.open(*args, **kwargs)  # type: ignore[arg-type]
            self.bootstrap = descriptor
            return descriptor

        def close(self, fd: int) -> None:
            os.close(fd)
            if fd == self.bootstrap and not self.injected:
                self.injected = True
                raise RuntimeError("injected bootstrap close failure")

    def recording_issue(value: TrustedDirectory, state: object) -> object:
        token = original_issue(value, state)  # type: ignore[arg-type]
        issued.append(value)
        retained_descriptors.append(value._fd)
        return token

    def interrupted_cleanup(value: TrustedDirectory) -> None:
        nonlocal cleanup_calls
        cleanup_calls += 1
        if cleanup_calls == 1:
            raise MemoryError("injected pre-retirement cleanup failure")
        original_trusted_close(value)

    interrupted_os = InterruptedBootstrapOS()
    dependencies = packaged_module._SYSTEM_DEPENDENCIES._replace(
        open_root=interrupted_os.open,
        close_fd=interrupted_os.close,
    )
    monkeypatch.setattr(carrier_module._TRUSTED_AUTHORITIES, "issue", recording_issue)
    monkeypatch.setattr(TrustedDirectory, "close", interrupted_cleanup)

    with pytest.raises(MemoryError, match="pre-retirement cleanup failure") as raised:
        packaged_module._acquire_packaged_internal_source_with_dependencies(
            lock,
            root,
            dependencies,
        )
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert "bootstrap close failure" in str(raised.value.__cause__)

    trusted = issued[0]
    assert carrier_module._TRUSTED_AUTHORITIES.state(trusted) is None
    assert trusted._fd == -1
    assert cleanup_calls == 2
    with pytest.raises(OSError):
        os.fstat(retained_descriptors[0])


def test_result_publication_interruption_retires_provisional_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_issue = packaged_module._PACKAGED_AUTHORITIES.issue
    issued: list[PackagedInternalSource] = []

    def interrupt_after_issue(value: PackagedInternalSource, state: object) -> object:
        token = original_issue(value, state)  # type: ignore[arg-type]
        issued.append(value)
        raise KeyboardInterrupt("injected result publication interruption")

    monkeypatch.setattr(
        packaged_module._PACKAGED_AUTHORITIES,
        "issue",
        interrupt_after_issue,
    )
    baseline = len(os.listdir("/dev/fd"))
    with pytest.raises(KeyboardInterrupt, match="publication interruption"):
        acquire_packaged_internal_source(_valid_lock(data_path()))

    assert len(os.listdir("/dev/fd")) == baseline
    provisional = issued[0]
    assert packaged_module._PACKAGED_AUTHORITIES.state(provisional) is None
    with pytest.raises(AcquisitionContractError, match="not issued"):
        _ = provisional.content_revision


def test_post_retirement_cleanup_report_is_not_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_trusted_close = TrustedDirectory.close
    retained_descriptors: list[int] = []
    cleanup_calls = 0

    class InterruptedBootstrapOS:
        O_RDONLY = os.O_RDONLY
        O_DIRECTORY = os.O_DIRECTORY
        O_CLOEXEC = os.O_CLOEXEC
        O_NOFOLLOW = os.O_NOFOLLOW

        def __init__(self) -> None:
            self.bootstrap: int | None = None

        def open(self, *args: object, **kwargs: object) -> int:
            descriptor = os.open(*args, **kwargs)  # type: ignore[arg-type]
            self.bootstrap = descriptor
            return descriptor

        def close(self, fd: int) -> None:
            os.close(fd)
            if fd == self.bootstrap:
                raise RuntimeError("injected bootstrap close failure")

    def reporting_cleanup(value: TrustedDirectory) -> None:
        nonlocal cleanup_calls
        cleanup_calls += 1
        if cleanup_calls == 1:
            retained_descriptors.append(value._fd)
            original_trusted_close(value)
            raise RuntimeError("injected cleanup close report")
        original_trusted_close(value)

    interrupted_os = InterruptedBootstrapOS()
    dependencies = packaged_module._SYSTEM_DEPENDENCIES._replace(
        open_root=interrupted_os.open,
        close_fd=interrupted_os.close,
    )
    monkeypatch.setattr(TrustedDirectory, "close", reporting_cleanup)

    with pytest.raises(RuntimeError, match="cleanup close report") as raised:
        packaged_module._acquire_packaged_internal_source_with_dependencies(
            _valid_lock(data_path()),
            data_path(),
            dependencies,
        )

    assert cleanup_calls == 2
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert "bootstrap close failure" in str(raised.value.__cause__)
    with pytest.raises(OSError):
        os.fstat(retained_descriptors[0])


def test_packaged_source_failure_releases_all_descriptors(
    tmp_path: Path,
) -> None:
    root = _copy_resources(tmp_path)
    lock = _valid_lock(root)
    (root / "declarations" / "v1" / PACKAGED_DECLARATION_PATHS[-1]).unlink()
    baseline = len(os.listdir("/dev/fd"))

    with pytest.raises(ByteCarrierError):
        _acquire_packaged_internal_source_from_root(lock, root)

    assert len(os.listdir("/dev/fd")) == baseline


def test_packaged_source_keeps_unvalidated_declarations_as_json_values(
    tmp_path: Path,
) -> None:
    root = _copy_resources(tmp_path)
    target = root / "declarations" / "v1" / PACKAGED_DECLARATION_PATHS[0]
    target.write_text("unvalidated-scalar\n")
    lock = _valid_lock(root)

    acquired = _acquire_packaged_internal_source_from_root(lock, root)

    assert acquired.declaration_documents[0] == "unvalidated-scalar"


def test_packaged_generation_observer_binds_expected_lock_and_evidence() -> None:
    observation = packaged_module._observe_running_packaged_generation()
    try:
        facet_lock, source_lock = packaged_module._packaged_generation_components(
            observation
        )
        expected = _valid_lock(data_path())
        state = packaged_module._issued_packaged_generation_state(observation)

        assert facet_lock == expected.facet_registry.base
        assert source_lock == expected.internal_source
        assert state.facet_evidence.authoritative.path == PACKAGED_FACET_PATH
        assert (
            tuple(
                evidence.authoritative.path for evidence in state.declaration_evidence
            )
            == PACKAGED_DECLARATION_PATHS
        )
        assert state.facet_evidence.authoritative.data == (
            state.facet_evidence.verification.data
        )
        assert all(
            evidence.authoritative.data == evidence.verification.data
            for evidence in state.declaration_evidence
        )
    finally:
        packaged_module._retire_packaged_generation_observation(observation)


def test_packaged_generation_observer_reads_every_resource_before_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, str]] = []
    original_read = RetainedDirectory.read_authoritative
    original_verify = RetainedDirectory.verify

    def recording_read(self: RetainedDirectory, path: str):
        events.append(("read", path))
        return original_read(self, path)

    def recording_verify(self: RetainedDirectory, carrier):
        events.append(("verify", carrier.path))
        return original_verify(self, carrier)

    monkeypatch.setattr(RetainedDirectory, "read_authoritative", recording_read)
    monkeypatch.setattr(RetainedDirectory, "verify", recording_verify)

    observation = packaged_module._observe_running_packaged_generation()
    packaged_module._retire_packaged_generation_observation(observation)

    paths = (PACKAGED_FACET_PATH, *PACKAGED_DECLARATION_PATHS)
    assert events == [("read", path) for path in paths] + [
        ("verify", path) for path in paths
    ]


def test_packaged_generation_observer_rejects_change_before_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_resources(tmp_path)
    facet_path = root / PACKAGED_FACET_PATH
    original_read = RetainedDirectory.read_authoritative
    mutated = False

    def mutating_read(self: RetainedDirectory, path: str):
        nonlocal mutated
        carrier = original_read(self, path)
        if self.path == "declarations/v1" and not mutated:
            mutated = True
            facet_path.write_bytes(facet_path.read_bytes() + b"\n")
        return carrier

    monkeypatch.setattr(RetainedDirectory, "read_authoritative", mutating_read)

    with pytest.raises(ByteCarrierError, match="verification"):
        packaged_module._observe_packaged_generation_from_root(root)


@pytest.mark.parametrize(
    ("field", "old", "new", "location"),
    [
        ("id", "eutaxis/context-facets", "other/facets", "base.id"),
        ("owner", "owner: eutaxis", "owner: other", "base.owner"),
    ],
)
def test_packaged_generation_observer_rejects_wrong_facet_identity(
    tmp_path: Path,
    field: str,
    old: str,
    new: str,
    location: str,
) -> None:
    root = _copy_resources(tmp_path)
    target = root / PACKAGED_FACET_PATH
    target.write_text(target.read_text().replace(old, new, 1))

    with pytest.raises(
        AcquisitionContractError, match=f"facet {field} differs"
    ) as raised:
        packaged_module._observe_packaged_generation_from_root(root)
    assert location in raised.value.location


def test_packaged_generation_observer_rejects_missing_declaration(
    tmp_path: Path,
) -> None:
    root = _copy_resources(tmp_path)
    (root / "declarations" / "v1" / PACKAGED_DECLARATION_PATHS[-1]).unlink()

    with pytest.raises(ByteCarrierError):
        packaged_module._observe_packaged_generation_from_root(root)


def test_arbitrary_root_observation_cannot_cross_production_authority(
    tmp_path: Path,
) -> None:
    root = _copy_resources(tmp_path)
    observation = packaged_module._observe_packaged_generation_from_root(root)
    try:
        assert (
            packaged_module._PACKAGED_TEST_GENERATION_AUTHORITIES.state(observation)
            is not None
        )
        assert (
            packaged_module._PACKAGED_GENERATION_AUTHORITIES.state(observation) is None
        )
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            packaged_module._packaged_generation_components(observation)
    finally:
        packaged_module._PACKAGED_TEST_GENERATION_AUTHORITIES.retire(observation)


def test_arbitrary_retained_roots_produce_only_unissued_material(
    tmp_path: Path,
) -> None:
    root = _copy_resources(tmp_path)
    trusted = packaged_module._trusted_directory_from_path(
        root,
        packaged_module._SYSTEM_DEPENDENCIES,
    )
    with trusted:
        with (
            trusted.retain_directory(".") as facet_root,
            trusted.retain_directory("declarations/v1") as declaration_root,
        ):
            material = packaged_module._observe_packaged_generation_from_retained_roots(
                facet_root,
                declaration_root,
                packaged_module._SYSTEM_DEPENDENCIES,
            )

    assert type(material) is packaged_module._PackagedGenerationState
    with pytest.raises(AcquisitionContractError, match="not issued here"):
        packaged_module._packaged_generation_components(material)


def test_packaged_generation_observer_fails_closed_without_descriptor_support() -> None:
    dependencies = packaged_module._SYSTEM_DEPENDENCIES._replace(
        nofollow=None,
        root_flags=None,
    )

    with pytest.raises(AcquisitionContractError, match="descriptor support"):
        packaged_module._observe_packaged_generation_from_root(
            data_path(),
            dependencies,
        )


def test_packaged_generation_observation_rejects_forgery_copy_and_serialization() -> (
    None
):
    observation = packaged_module._observe_running_packaged_generation()
    try:
        with pytest.raises(TypeError, match="must be issued"):
            packaged_module._PackagedGenerationObservation()
        with pytest.raises(TypeError, match="cannot be copied"):
            copy.copy(observation)
        with pytest.raises(TypeError, match="cannot be copied"):
            copy.deepcopy(observation)
        with pytest.raises(TypeError, match="cannot be serialized"):
            pickle.dumps(observation)

        forged = object.__new__(packaged_module._PackagedGenerationObservation)
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            packaged_module._packaged_generation_components(forged)
        with pytest.raises(AcquisitionContractError, match="not issued here"):
            packaged_module._packaged_generation_components(object())
    finally:
        packaged_module._retire_packaged_generation_observation(observation)


def test_packaged_generation_observation_rejects_mutated_and_retired_state() -> None:
    observation = packaged_module._observe_running_packaged_generation()
    facet_lock, _source_lock = packaged_module._packaged_generation_components(
        observation
    )
    object.__setattr__(facet_lock, "sha256", "sha256:" + "0" * 64)

    with pytest.raises(AcquisitionContractError, match="lock state changed"):
        packaged_module._packaged_generation_components(observation)

    packaged_module._retire_packaged_generation_observation(observation)
    with pytest.raises(AcquisitionContractError, match="not issued here"):
        packaged_module._packaged_generation_components(observation)
    with pytest.raises(AcquisitionContractError, match="not issued here"):
        packaged_module._retire_packaged_generation_observation(observation)


def test_packaged_generation_observation_reauthenticates_verified_evidence() -> None:
    observation = packaged_module._observe_running_packaged_generation()
    state = packaged_module._issued_packaged_generation_state(observation)
    evidence = state.facet_evidence
    verified_state = carrier_module._VERIFIED_AUTHORITIES.retire(evidence)
    assert verified_state is not None
    verification_snapshot = cast(
        tuple[str, bytes, str, object, object],
        verified_state[6],
    )
    corrupted_snapshot = (
        verification_snapshot[0],
        verification_snapshot[1],
        "sha256:" + "0" * 64,
        verification_snapshot[3],
        verification_snapshot[4],
    )
    carrier_module._VERIFIED_AUTHORITIES.issue(
        evidence,
        (*verified_state[:6], corrupted_snapshot),
    )

    try:
        with pytest.raises(ByteCarrierError, match="verified carrier state is invalid"):
            packaged_module._packaged_generation_components(observation)
    finally:
        packaged_module._retire_packaged_generation_observation(observation)


def test_packaged_generation_publication_interruption_retires_provisional_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_issue = packaged_module._PACKAGED_GENERATION_AUTHORITIES.issue
    issued: list[packaged_module._PackagedGenerationObservation] = []

    def interrupt_after_issue(
        value: packaged_module._PackagedGenerationObservation,
        state: object,
    ) -> object:
        token = original_issue(value, state)  # type: ignore[arg-type]
        issued.append(value)
        raise KeyboardInterrupt("injected observation publication interruption")

    monkeypatch.setattr(
        packaged_module._PACKAGED_GENERATION_AUTHORITIES,
        "issue",
        interrupt_after_issue,
    )

    with pytest.raises(KeyboardInterrupt, match="publication interruption"):
        packaged_module._observe_running_packaged_generation()

    provisional = issued[0]
    assert packaged_module._PACKAGED_GENERATION_AUTHORITIES.state(provisional) is None
    with pytest.raises(AcquisitionContractError, match="not issued here"):
        packaged_module._packaged_generation_components(provisional)
