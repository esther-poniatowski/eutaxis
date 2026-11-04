"""Exercise descriptor-anchored authoritative and verification reads."""

from __future__ import annotations

import copy
import errno
import gc
import os
import pickle
from pathlib import Path
from threading import Barrier, Event, Thread

import pytest

import eutaxis.declarations.byte_carriers as carrier_module
from eutaxis.declarations.byte_carriers import (
    AuthoritativeByteCarrier,
    DirectoryIdentity,
    FileMetadata,
    RetainedDirectory,
    TrustedDirectory,
    VerifiedByteCarrier,
    _trusted_directory_from_workspace_path,
)
from eutaxis.declarations.exceptions import ByteCarrierError


def _trusted(path: Path) -> TrustedDirectory:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        return TrustedDirectory.from_fd(descriptor, label=str(path))
    finally:
        os.close(descriptor)


def _fd_count() -> int:
    return len(os.listdir("/dev/fd"))


def _equal_carrier(value: AuthoritativeByteCarrier) -> AuthoritativeByteCarrier:
    del value
    return object.__new__(AuthoritativeByteCarrier)


def test_authoritative_and_verification_reads_retain_exact_evidence(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "nested").mkdir()
    expected = b"exact retained bytes\n"
    (source / "nested" / "rule.yaml").write_bytes(expected)

    with _trusted(tmp_path) as workspace:
        with workspace.retain_directory("source") as retained:
            authoritative = retained.read_authoritative("nested/rule.yaml")
            verified = retained.verify(authoritative)

    assert authoritative.data == expected
    assert authoritative.sha256.startswith("sha256:")
    assert authoritative.before == authoritative.after
    assert verified.authoritative is authoritative
    assert verified.verification.data == expected
    assert verified.verification.before == authoritative.before


def test_dot_retains_the_already_open_trusted_directory(tmp_path: Path) -> None:
    (tmp_path / "rule.yaml").write_bytes(b"rule")
    with _trusted(tmp_path) as trusted:
        with trusted.retain_directory(".") as retained:
            assert retained.identity == trusted.identity
            retained.verify(retained.read_authoritative("rule.yaml"))


def test_workspace_path_is_retained_by_component_traversal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()

    absolute = _trusted_directory_from_workspace_path(str(workspace_path))
    try:
        assert absolute.label == str(workspace_path)
    finally:
        absolute.close()

    monkeypatch.chdir(tmp_path)
    relative = _trusted_directory_from_workspace_path("workspace")
    current = _trusted_directory_from_workspace_path(".")
    try:
        assert relative.identity == absolute.identity
        assert current.label == "."
    finally:
        relative.close()
        current.close()


@pytest.mark.parametrize(
    "path",
    ["", "a//b", "a/./b", "a/../b", "./a", "a/", "a\\b", "a\x00b"],
)
def test_workspace_path_rejects_every_non_normalized_component(path: str) -> None:
    with pytest.raises(ByteCarrierError):
        _trusted_directory_from_workspace_path(path)

    class Text(str):
        pass

    with pytest.raises(ByteCarrierError, match="exact text"):
        _trusted_directory_from_workspace_path(Text("."))


def test_workspace_path_never_follows_a_symbolic_component(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(target, target_is_directory=True)

    with pytest.raises(ByteCarrierError):
        _trusted_directory_from_workspace_path(str(linked))


@pytest.mark.parametrize(
    "path",
    ["", "/absolute", "a\\b", "a//b", "a/./b", "a/../b", "a\x00b"],
)
def test_every_non_normalized_path_form_fails_before_traversal(
    tmp_path: Path, path: str
) -> None:
    with _trusted(tmp_path) as trusted:
        with pytest.raises(ByteCarrierError, match="normalized relative POSIX"):
            trusted.retain_directory(path)


def test_file_path_rejects_dot_and_unicode_surrogates(tmp_path: Path) -> None:
    with _trusted(tmp_path) as trusted:
        with trusted.retain_directory(".") as retained:
            with pytest.raises(ByteCarrierError):
                retained.read_authoritative(".")
            with pytest.raises(ByteCarrierError, match="surrogate"):
                retained.read_authoritative("bad\ud800")


def test_directory_and_file_symlinks_never_supply_fallback_paths(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "real").mkdir()
    (source / "real" / "rule.yaml").write_bytes(b"rule")
    (tmp_path / "source-link").symlink_to(source, target_is_directory=True)
    (source / "nested-link").symlink_to(source / "real", target_is_directory=True)
    (source / "rule-link.yaml").symlink_to(source / "real" / "rule.yaml")

    with _trusted(tmp_path) as workspace:
        with pytest.raises(ByteCarrierError):
            workspace.retain_directory("source-link")
        with workspace.retain_directory("source") as retained:
            with pytest.raises(ByteCarrierError):
                retained.read_authoritative("nested-link/rule.yaml")
            with pytest.raises(ByteCarrierError):
                retained.read_authoritative("rule-link.yaml")


def test_only_regular_files_are_read(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "directory").mkdir()
    fifo = source / "pipe"
    os.mkfifo(fifo)
    with _trusted(tmp_path) as workspace:
        with workspace.retain_directory("source") as retained:
            with pytest.raises(ByteCarrierError, match="regular file"):
                retained.read_authoritative("directory")
            with pytest.raises(ByteCarrierError, match="regular file"):
                retained.read_authoritative("pipe")


def test_replacing_source_root_invalidates_verification(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "rule.yaml").write_bytes(b"original")
    with _trusted(tmp_path) as workspace:
        with workspace.retain_directory("source") as retained:
            authoritative = retained.read_authoritative("rule.yaml")
            source.rename(tmp_path / "old-source")
            source.mkdir()
            (source / "rule.yaml").write_bytes(b"original")
            with pytest.raises(ByteCarrierError, match="root identity changed"):
                retained.verify(authoritative)


def test_replacing_source_root_during_verification_fails_final_revalidation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "rule.yaml").write_bytes(b"original")
    original_read = carrier_module._read_file_at
    reads = 0

    def replacing_read(root_fd: int, path: str) -> AuthoritativeByteCarrier:
        nonlocal reads
        reads += 1
        result = original_read(root_fd, path)
        if reads == 2:
            source.rename(tmp_path / "old-source")
            source.mkdir()
            (source / "rule.yaml").write_bytes(b"original")
        return result

    monkeypatch.setattr(carrier_module, "_read_file_at", replacing_read)
    with _trusted(tmp_path) as workspace:
        with workspace.retain_directory("source") as retained:
            authoritative = retained.read_authoritative("rule.yaml")
            with pytest.raises(ByteCarrierError, match="during verification"):
                retained.verify(authoritative)


def test_replacing_file_invalidates_verification_even_with_equal_bytes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    path = source / "rule.yaml"
    path.write_bytes(b"same")
    with _trusted(tmp_path) as workspace:
        with workspace.retain_directory("source") as retained:
            authoritative = retained.read_authoritative("rule.yaml")
            path.unlink()
            path.write_bytes(b"same")
            with pytest.raises(ByteCarrierError, match="metadata differ"):
                retained.verify(authoritative)


def test_changing_file_bytes_invalidates_verification(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    path = source / "rule.yaml"
    path.write_bytes(b"first")
    with _trusted(tmp_path) as workspace:
        with workspace.retain_directory("source") as retained:
            authoritative = retained.read_authoritative("rule.yaml")
            path.write_bytes(b"other")
            with pytest.raises(ByteCarrierError, match="bytes differ"):
                retained.verify(authoritative)


def test_metadata_change_during_read_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    path = source / "large.bin"
    path.write_bytes(b"a" * (1024 * 1024 + 10))
    original_read = os.read
    changed = False

    def changing_read(fd: int, size: int) -> bytes:
        nonlocal changed
        result = original_read(fd, size)
        if result and not changed:
            changed = True
            os.utime(path, None)
        return result

    monkeypatch.setattr(os, "read", changing_read)
    with _trusted(tmp_path) as workspace:
        with workspace.retain_directory("source") as retained:
            with pytest.raises(ByteCarrierError, match="metadata changed"):
                retained.read_authoritative("large.bin")


def test_closed_capabilities_fail_and_close_is_idempotent(tmp_path: Path) -> None:
    trusted = _trusted(tmp_path)
    retained = trusted.retain_directory(".")
    retained.close()
    retained.close()
    with pytest.raises(ByteCarrierError, match="closed"):
        retained.read_authoritative("rule.yaml")
    trusted.close()
    trusted.close()
    with pytest.raises(ByteCarrierError, match="closed"):
        trusted.retain_directory(".")


def test_capabilities_reject_wrong_descriptors_copying_and_serialization(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "file"
    file_path.write_bytes(b"file")
    file_descriptor = os.open(file_path, os.O_RDONLY)
    try:
        with pytest.raises(ByteCarrierError, match="directory"):
            TrustedDirectory.from_fd(file_descriptor, label="file")
    finally:
        os.close(file_descriptor)
    with pytest.raises(ByteCarrierError, match="exact integer"):
        TrustedDirectory.from_fd(True, label="bool")  # type: ignore[arg-type]

    with _trusted(tmp_path) as trusted:
        retained = trusted.retain_directory(".")
        try:
            for value in (trusted, retained):
                with pytest.raises(TypeError, match="cannot be copied"):
                    copy.copy(value)
                with pytest.raises(TypeError, match="cannot be serialized"):
                    pickle.dumps(value)
        finally:
            retained.close()


def test_verification_requires_an_exact_authoritative_carrier(tmp_path: Path) -> None:
    with _trusted(tmp_path) as trusted:
        with trusted.retain_directory(".") as retained:
            with pytest.raises(ByteCarrierError, match="wrong exact type"):
                retained.verify(object())  # type: ignore[arg-type]


def test_carriers_require_process_local_issuance_and_complete_unchanged_state(
    tmp_path: Path,
) -> None:
    (tmp_path / "rule.yaml").write_bytes(b"rule")
    with _trusted(tmp_path) as trusted:
        with trusted.retain_directory(".") as retained:
            authoritative = retained.read_authoritative("rule.yaml")
            with pytest.raises(ByteCarrierError, match="not issued here"):
                retained.verify(_equal_carrier(authoritative))

            altered_hash = retained.read_authoritative("rule.yaml")
            with pytest.raises(AttributeError):
                object.__setattr__(altered_hash, "sha256", "sha256:not-real")
            retained.verify(altered_hash)

            altered_metadata = retained.read_authoritative("rule.yaml")
            object.__setattr__(
                altered_metadata.before,
                "size",
                altered_metadata.before.size + 1,
            )
            retained.verify(altered_metadata)


def test_verification_uses_issued_snapshot_during_concurrent_slot_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.yaml").write_bytes(b"authoritative")
    (tmp_path / "b.yaml").write_bytes(b"forged")
    with _trusted(tmp_path) as trusted:
        with trusted.retain_directory(".") as retained:
            authoritative = retained.read_authoritative("a.yaml")
            alternate = retained.read_authoritative("b.yaml")
            original_open = carrier_module._open_directory_at
            mutated = False

            def mutating_open(fd: int, components: tuple[str, ...], path: str) -> int:
                nonlocal mutated
                if not mutated:
                    mutated = True
                    for field in ("path", "data", "sha256", "before", "after"):
                        with pytest.raises(AttributeError):
                            object.__setattr__(
                                authoritative,
                                field,
                                getattr(alternate, field),
                            )
                return original_open(fd, components, path)

            monkeypatch.setattr(carrier_module, "_open_directory_at", mutating_open)
            verified = retained.verify(authoritative)

            assert verified.authoritative.path == "a.yaml"
            assert verified.authoritative.data == b"authoritative"
            assert verified.verification.path == "a.yaml"
            assert verified.verification.data == b"authoritative"


def test_carriers_reject_direct_construction_copying_and_serialization(
    tmp_path: Path,
) -> None:
    metadata = FileMetadata(1, 2, 3, 4, 5, 6)
    with pytest.raises(TypeError, match="issued by reading"):
        AuthoritativeByteCarrier("a", b"a", "sha256:x", metadata, metadata)
    with pytest.raises(TypeError, match="issued by verification"):
        VerifiedByteCarrier(object(), object())

    (tmp_path / "rule.yaml").write_bytes(b"rule")
    with _trusted(tmp_path) as trusted:
        with trusted.retain_directory(".") as retained:
            authoritative = retained.read_authoritative("rule.yaml")
            verified = retained.verify(authoritative)
            for value in (authoritative, verified):
                with pytest.raises(TypeError, match="cannot be copied"):
                    copy.copy(value)
                with pytest.raises(TypeError, match="cannot be serialized"):
                    pickle.dumps(value)


def test_retained_root_semantics_are_read_only_and_authority_checked(
    tmp_path: Path,
) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "rule.yaml").write_bytes(b"a")
    with _trusted(tmp_path) as trusted:
        with trusted.retain_directory("a") as retained:
            with pytest.raises(AttributeError):
                retained.path = "b"  # type: ignore[misc]
            with pytest.raises(AttributeError):
                retained.identity = DirectoryIdentity(0, 0)  # type: ignore[misc]
            object.__setattr__(retained, "_path", "b")
            with pytest.raises(ByteCarrierError, match="state changed"):
                retained.read_authoritative("rule.yaml")


def test_verification_pins_issued_root_context_before_result_issuance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "rule.yaml").write_bytes(b"same")
    (tmp_path / "b" / "rule.yaml").write_bytes(b"same")
    with _trusted(tmp_path) as trusted:
        with trusted.retain_directory("a") as retained:
            authoritative = retained.read_authoritative("rule.yaml")
            original_issue = carrier_module._issue_byte_carrier

            def mutating_issue(
                observation: object,
                *,
                role: str,
                root_path: str,
                root_identity: DirectoryIdentity,
            ) -> AuthoritativeByteCarrier:
                if role == "verification":
                    observed = os.stat(tmp_path / "b")
                    object.__setattr__(retained, "_path", "b")
                    object.__setattr__(
                        retained,
                        "_identity",
                        DirectoryIdentity(observed.st_dev, observed.st_ino),
                    )
                return original_issue(
                    observation,  # type: ignore[arg-type]
                    role=role,
                    root_path=root_path,
                    root_identity=root_identity,
                )

            monkeypatch.setattr(carrier_module, "_issue_byte_carrier", mutating_issue)
            verified = retained.verify(authoritative)

            authoritative_state = carrier_module._BYTE_AUTHORITIES.state(authoritative)
            verification_state = carrier_module._BYTE_AUTHORITIES.state(
                verified.verification
            )
            verified_state = carrier_module._VERIFIED_AUTHORITIES.state(verified)
            assert authoritative_state is not None
            assert verification_state is not None
            assert verified_state is not None
            assert authoritative_state[1] == "a"
            assert verification_state[1] == "a"
            assert verified_state[0] == "a"


def test_reconstructed_retained_root_has_no_authority() -> None:
    forged = object.__new__(RetainedDirectory)
    object.__setattr__(forged, "_parent_fd", 999_998)
    object.__setattr__(forged, "_root_fd", 999_999)
    object.__setattr__(forged, "_identity", DirectoryIdentity(1, 2))
    object.__setattr__(forged, "_path", "source")
    with pytest.raises(ByteCarrierError, match="closed|state changed"):
        forged.read_authoritative("rule.yaml")
    object.__setattr__(forged, "_parent_fd", -1)
    object.__setattr__(forged, "_root_fd", -1)


def test_exact_capability_forgeries_fail_through_public_error() -> None:
    forged_trusted = object.__new__(TrustedDirectory)
    with pytest.raises(ByteCarrierError, match="closed"):
        forged_trusted.retain_directory(".")

    forged_retained = object.__new__(RetainedDirectory)
    with pytest.raises(ByteCarrierError, match="closed"):
        forged_retained.read_authoritative("rule.yaml")


@pytest.mark.parametrize(
    "failure", [OSError(errno.EIO, "injected"), RuntimeError("injected")]
)
def test_duplicate_cleanup_closes_descriptor_when_inheritable_setup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    baseline = _fd_count()

    def fail_inheritable(_fd: int, _value: bool) -> None:
        raise failure

    def fail_former_cleanup_boundary(*_args: object, **_kwargs: object) -> None:
        raise MemoryError("former cleanup boundary")

    monkeypatch.setattr(os, "set_inheritable", fail_inheritable)
    monkeypatch.setattr(
        carrier_module,
        "_close_descriptors_once",
        fail_former_cleanup_boundary,
        raising=False,
    )
    try:
        with pytest.raises(ByteCarrierError, match="injected"):
            TrustedDirectory.from_fd(descriptor, label="root")
        assert _fd_count() == baseline
    finally:
        os.close(descriptor)


def test_capability_issuance_rejects_subclass_dispatch(tmp_path: Path) -> None:
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)

    class OverridingDirectory(TrustedDirectory):
        def _require_open(self) -> int:
            return descriptor

    try:
        with pytest.raises(TypeError, match="subclasses cannot issue"):
            OverridingDirectory.from_fd(descriptor, label="root")
    finally:
        os.close(descriptor)


def test_trusted_issuance_failure_releases_locally_owned_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    baseline = _fd_count()

    def fail_issue(_value: object, _state: object) -> object:
        raise RuntimeError("injected authority failure")

    monkeypatch.setattr(carrier_module._TRUSTED_AUTHORITIES, "issue", fail_issue)
    try:
        with pytest.raises(RuntimeError, match="authority failure"):
            TrustedDirectory.from_fd(descriptor, label="root")
        assert _fd_count() == baseline
    finally:
        os.close(descriptor)


def test_trusted_post_issuance_interruption_retires_and_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    original_issue = carrier_module._TRUSTED_AUTHORITIES.issue
    issued: list[TrustedDirectory] = []
    duplicates: list[int] = []

    def interrupt_after_issue(value: TrustedDirectory, state: object) -> object:
        token = original_issue(value, state)  # type: ignore[arg-type]
        issued.append(value)
        duplicates.append(value._fd)
        raise KeyboardInterrupt("injected post-issuance interruption")

    monkeypatch.setattr(
        carrier_module._TRUSTED_AUTHORITIES,
        "issue",
        interrupt_after_issue,
    )
    try:
        with pytest.raises(KeyboardInterrupt, match="post-issuance interruption"):
            TrustedDirectory.from_fd(descriptor, label="root")
        trusted = issued[0]
        duplicate = duplicates[0]
        assert carrier_module._TRUSTED_AUTHORITIES.state(trusted) is None
        assert trusted._fd == -1
        with pytest.raises(OSError):
            os.fstat(duplicate)
        with pytest.raises(ByteCarrierError, match="closed"):
            trusted.retain_directory(".")
    finally:
        os.close(descriptor)


def test_retained_issuance_failure_releases_both_locally_owned_descriptors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _trusted(tmp_path) as trusted:
        baseline = _fd_count()

        def fail_issue(_value: object, _state: object) -> object:
            raise RuntimeError("injected authority failure")

        monkeypatch.setattr(carrier_module._RETAINED_AUTHORITIES, "issue", fail_issue)
        with pytest.raises(RuntimeError, match="authority failure"):
            trusted.retain_directory(".")
        assert _fd_count() == baseline


def test_retained_issuance_interruption_retires_before_descriptor_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    (replacement / "rule.yaml").write_bytes(b"replacement")
    with _trusted(tmp_path) as trusted:
        original_issue = carrier_module._RETAINED_AUTHORITIES.issue
        issued: list[RetainedDirectory] = []
        descriptors: list[tuple[int, int]] = []

        def interrupt_after_issue(value: RetainedDirectory, state: object) -> object:
            token = original_issue(value, state)  # type: ignore[arg-type]
            issued.append(value)
            descriptors.append((value._root_fd, value._parent_fd))
            raise KeyboardInterrupt("injected post-issuance interruption")

        monkeypatch.setattr(
            carrier_module._RETAINED_AUTHORITIES,
            "issue",
            interrupt_after_issue,
        )
        with pytest.raises(KeyboardInterrupt, match="post-issuance interruption"):
            trusted.retain_directory(".")

        retained = issued[0]
        root_fd, parent_fd = descriptors[0]
        assert carrier_module._RETAINED_AUTHORITIES.state(retained) is None
        assert retained._root_fd == -1
        assert retained._parent_fd == -1
        for descriptor in (root_fd, parent_fd):
            with pytest.raises(OSError):
                os.fstat(descriptor)

        replacement_fd = os.open(replacement, os.O_RDONLY | os.O_DIRECTORY)
        os.dup2(replacement_fd, root_fd)
        if replacement_fd != root_fd:
            os.close(replacement_fd)
        try:
            with pytest.raises(ByteCarrierError, match="closed"):
                retained.read_authoritative("rule.yaml")
        finally:
            os.close(root_fd)


def test_retained_issuance_failure_attempts_both_closes_after_base_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _trusted(tmp_path) as trusted:
        original_close = os.close
        calls: list[int] = []

        def fail_issue(_value: object, _state: object) -> object:
            raise RuntimeError("injected authority failure")

        def reporting_close(fd: int) -> None:
            calls.append(fd)
            original_close(fd)
            if len(calls) == 1:
                raise KeyboardInterrupt("injected close interruption")

        monkeypatch.setattr(carrier_module._RETAINED_AUTHORITIES, "issue", fail_issue)
        monkeypatch.setattr(os, "close", reporting_close)
        with pytest.raises(KeyboardInterrupt, match="close interruption"):
            trusted.retain_directory(".")

        assert len(calls) == 2
        assert len(set(calls)) == 2


@pytest.mark.parametrize("stage", ["open", "identity"])
def test_retain_directory_cleans_local_descriptors_on_base_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    with _trusted(tmp_path) as trusted:
        baseline = _fd_count()

        def interrupt(*_args: object, **_kwargs: object) -> None:
            raise KeyboardInterrupt("injected")

        target = "_open_directory_at" if stage == "open" else "_directory_identity"
        monkeypatch.setattr(carrier_module, target, interrupt)
        with pytest.raises(KeyboardInterrupt, match="injected"):
            trusted.retain_directory(".")
        assert _fd_count() == baseline


def test_trusted_cleanup_uses_issued_descriptor_not_mutated_slot(
    tmp_path: Path,
) -> None:
    trusted = _trusted(tmp_path)
    issued = trusted._fd
    victim = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    object.__setattr__(trusted, "_fd", victim)
    trusted.close()
    os.fstat(victim)
    with pytest.raises(OSError):
        os.fstat(issued)
    os.close(victim)


def test_retained_cleanup_uses_issued_descriptors_not_mutated_slots(
    tmp_path: Path,
) -> None:
    with _trusted(tmp_path) as trusted:
        retained = trusted.retain_directory(".")
        issued_root = retained._root_fd
        issued_parent = retained._parent_fd
        victim_root = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
        victim_parent = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
        object.__setattr__(retained, "_root_fd", victim_root)
        object.__setattr__(retained, "_parent_fd", victim_parent)
        retained.close()
        os.fstat(victim_root)
        os.fstat(victim_parent)
        with pytest.raises(OSError):
            os.fstat(issued_root)
        with pytest.raises(OSError):
            os.fstat(issued_parent)
        os.close(victim_root)
        os.close(victim_parent)


def test_retained_destructor_uses_issued_descriptors_not_mutated_slots(
    tmp_path: Path,
) -> None:
    with _trusted(tmp_path) as trusted:
        retained = trusted.retain_directory(".")
        issued_root = retained._root_fd
        issued_parent = retained._parent_fd
        victim = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
        object.__setattr__(retained, "_root_fd", victim)
        del retained
        gc.collect()
        os.fstat(victim)
        with pytest.raises(OSError):
            os.fstat(issued_root)
        with pytest.raises(OSError):
            os.fstat(issued_parent)
        os.close(victim)


def test_close_does_not_depend_on_allocating_new_authority_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted = _trusted(tmp_path)
    retained = trusted.retain_directory(".")
    trusted_fd = trusted._fd
    root_fd = retained._root_fd
    parent_fd = retained._parent_fd

    def fail_issue(_value: object, _state: object) -> object:
        raise MemoryError("injected")

    monkeypatch.setattr(carrier_module._TRUSTED_AUTHORITIES, "issue", fail_issue)
    monkeypatch.setattr(carrier_module._RETAINED_AUTHORITIES, "issue", fail_issue)
    retained.close()
    trusted.close()
    for descriptor in (trusted_fd, root_fd, parent_fd):
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_close_extracts_issued_state_before_retirement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _trusted(tmp_path) as trusted:
        retained = trusted.retain_directory(".")
        root = retained._root_fd
        parent = retained._parent_fd
        original_cast = carrier_module.cast

        def fail_cast(*_args: object, **_kwargs: object) -> object:
            raise MemoryError("injected extraction failure")

        monkeypatch.setattr(carrier_module, "cast", fail_cast)
        with pytest.raises(MemoryError, match="extraction failure"):
            retained.close()
        assert carrier_module._RETAINED_AUTHORITIES.state(retained) is not None
        os.fstat(root)
        os.fstat(parent)

        monkeypatch.setattr(carrier_module, "cast", original_cast)
        retained.close()


def test_concurrent_close_cannot_redirect_authoritative_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "rule.yaml").write_bytes(b"authoritative")
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    (replacement / "rule.yaml").write_bytes(b"replacement")
    started = Event()
    resume = Event()
    original_read = carrier_module._read_file_at
    result: list[AuthoritativeByteCarrier] = []
    failures: list[BaseException] = []

    def paused_read(fd: int, path: str):
        started.set()
        assert resume.wait(5)
        return original_read(fd, path)

    monkeypatch.setattr(carrier_module, "_read_file_at", paused_read)
    with _trusted(tmp_path) as trusted:
        retained = trusted.retain_directory("source")
        issued_root = retained._root_fd

        def read() -> None:
            try:
                result.append(retained.read_authoritative("rule.yaml"))
            except BaseException as exc:
                failures.append(exc)

        worker = Thread(target=read)
        worker.start()
        assert started.wait(5)
        retained.close()
        replacement_fd = os.open(replacement, os.O_RDONLY | os.O_DIRECTORY)
        if replacement_fd != issued_root:
            os.dup2(replacement_fd, issued_root)
            os.close(replacement_fd)
        try:
            resume.set()
            worker.join(5)
            assert not worker.is_alive()
            assert not failures
            assert result[0].data == b"authoritative"
        finally:
            os.close(issued_root)


def test_concurrent_close_cannot_redirect_trusted_root_retention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "rule.yaml").write_bytes(b"authoritative")
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    (replacement / "source").mkdir()
    (replacement / "source" / "rule.yaml").write_bytes(b"replacement")
    started = Event()
    resume = Event()
    original_open = carrier_module._open_directory_at
    result: list[RetainedDirectory] = []
    failures: list[BaseException] = []

    def paused_open(fd: int, components: tuple[str, ...], path: str) -> int:
        started.set()
        assert resume.wait(5)
        return original_open(fd, components, path)

    monkeypatch.setattr(carrier_module, "_open_directory_at", paused_open)
    trusted = _trusted(tmp_path)
    issued_fd = trusted._fd

    def retain() -> None:
        try:
            result.append(trusted.retain_directory("source"))
        except BaseException as exc:
            failures.append(exc)

    worker = Thread(target=retain)
    worker.start()
    assert started.wait(5)
    trusted.close()
    replacement_fd = os.open(replacement, os.O_RDONLY | os.O_DIRECTORY)
    if replacement_fd != issued_fd:
        os.dup2(replacement_fd, issued_fd)
        os.close(replacement_fd)
    try:
        resume.set()
        worker.join(5)
        assert not worker.is_alive()
        assert not failures
        retained = result[0]
        try:
            assert retained.read_authoritative("rule.yaml").data == b"authoritative"
        finally:
            retained.close()
    finally:
        os.close(issued_fd)


def test_concurrent_close_cannot_redirect_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "rule.yaml").write_bytes(b"authoritative")
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    (replacement / "source").mkdir()
    (replacement / "source" / "rule.yaml").write_bytes(b"replacement")
    started = Event()
    resume = Event()
    original_open = carrier_module._open_directory_at
    result: list[VerifiedByteCarrier] = []
    failures: list[BaseException] = []

    with _trusted(tmp_path) as trusted:
        retained = trusted.retain_directory("source")
        authoritative = retained.read_authoritative("rule.yaml")
        issued_parent = retained._parent_fd

        def paused_open(fd: int, components: tuple[str, ...], path: str) -> int:
            started.set()
            assert resume.wait(5)
            return original_open(fd, components, path)

        monkeypatch.setattr(carrier_module, "_open_directory_at", paused_open)

        def verify() -> None:
            try:
                result.append(retained.verify(authoritative))
            except BaseException as exc:
                failures.append(exc)

        worker = Thread(target=verify)
        worker.start()
        assert started.wait(5)
        retained.close()
        replacement_fd = os.open(replacement, os.O_RDONLY | os.O_DIRECTORY)
        if replacement_fd != issued_parent:
            os.dup2(replacement_fd, issued_parent)
            os.close(replacement_fd)
        try:
            resume.set()
            worker.join(5)
            assert not worker.is_alive()
            assert not failures
            assert result[0].verification.data == b"authoritative"
        finally:
            os.close(issued_parent)


def test_simultaneous_retained_close_releases_each_descriptor_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _trusted(tmp_path) as trusted:
        retained = trusted.retain_directory(".")
        root = retained._root_fd
        parent = retained._parent_fd
        original_close = os.close
        calls: list[int] = []
        ready = Barrier(3)
        failures: list[BaseException] = []

        def reporting_close(fd: int) -> None:
            if fd in {root, parent}:
                calls.append(fd)
            original_close(fd)

        def close() -> None:
            ready.wait()
            try:
                retained.close()
            except BaseException as exc:
                failures.append(exc)

        monkeypatch.setattr(os, "close", reporting_close)
        workers = [Thread(target=close), Thread(target=close)]
        for worker in workers:
            worker.start()
        ready.wait()
        for worker in workers:
            worker.join(5)

        assert all(not worker.is_alive() for worker in workers)
        assert not failures
        assert calls.count(root) == 1
        assert calls.count(parent) == 1


def test_retained_close_attempts_each_owned_descriptor_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _trusted(tmp_path) as trusted:
        retained = trusted.retain_directory(".")
        root = retained._root_fd
        parent = retained._parent_fd
        original_close = os.close
        calls: list[int] = []

        def reporting_close(fd: int) -> None:
            calls.append(fd)
            original_close(fd)
            if fd == root:
                raise OSError(errno.EINTR, "injected close report")

        monkeypatch.setattr(os, "close", reporting_close)
        with pytest.raises(ByteCarrierError, match="injected close report"):
            retained.close()
        assert calls.count(root) == 1
        assert calls.count(parent) == 1


@pytest.mark.parametrize(
    "failure",
    [RuntimeError("injected close failure"), MemoryError("injected close failure")],
)
def test_retained_close_attempts_parent_after_non_os_root_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
) -> None:
    with _trusted(tmp_path) as trusted:
        retained = trusted.retain_directory(".")
        root = retained._root_fd
        parent = retained._parent_fd
        original_close = os.close
        calls: list[int] = []

        def reporting_close(fd: int) -> None:
            calls.append(fd)
            original_close(fd)
            if fd == root:
                raise failure

        monkeypatch.setattr(os, "close", reporting_close)
        with pytest.raises(type(failure), match="injected close failure"):
            retained.close()
        assert calls.count(root) == 1
        assert calls.count(parent) == 1


def test_open_file_cleanup_never_retries_an_ambiguous_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "rule.yaml").write_bytes(b"rule")
    with _trusted(tmp_path) as trusted:
        with trusted.retain_directory(".") as retained:
            baseline = _fd_count()
            original_close = os.close
            calls: list[int] = []
            injected = False

            def reporting_close(fd: int) -> None:
                nonlocal injected
                calls.append(fd)
                original_close(fd)
                if not injected:
                    injected = True
                    raise OSError(errno.EINTR, "injected close report")

            monkeypatch.setattr(os, "close", reporting_close)
            with pytest.raises(ByteCarrierError, match="injected close report"):
                retained.read_authoritative("rule.yaml")
            assert len(calls) == len(set(calls))
            assert _fd_count() == baseline


def test_unsupported_descriptor_platform_fails_through_public_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    monkeypatch.delattr(os, "O_NOFOLLOW")
    try:
        with pytest.raises(ByteCarrierError) as raised:
            TrustedDirectory.from_fd(descriptor, label="root")
        assert raised.value.path == "<platform>"
    finally:
        os.close(descriptor)


def test_capability_classes_cannot_be_constructed_directly() -> None:
    with pytest.raises(TypeError, match="retained from a descriptor"):
        TrustedDirectory()
    with pytest.raises(TypeError, match="opened from a capability"):
        RetainedDirectory()
