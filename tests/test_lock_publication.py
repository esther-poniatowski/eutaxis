"""Exercise descriptor-relative lock checking and create-only publication."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import eutaxis.declarations.lock_publication as publication_module
from eutaxis.declarations.byte_carriers import _trusted_directory_from_workspace_path
from eutaxis.declarations.exceptions import ByteCarrierError

_CANDIDATE = b'{"schema-version":1}\n'


def _workspace(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    return _trusted_directory_from_workspace_path(str(path))


def test_checked_lock_requires_verified_exact_bytes(tmp_path: Path) -> None:
    (tmp_path / "locks").mkdir()
    (tmp_path / "locks/current.json").write_bytes(_CANDIDATE)
    workspace = _workspace(tmp_path)
    try:
        assert publication_module._check_candidate_bytes(
            workspace,
            "locks/current.json",
            _CANDIDATE,
        )
        assert not publication_module._check_candidate_bytes(
            workspace,
            "locks/current.json",
            b"different\n",
        )
    finally:
        workspace.close()


def test_checked_lock_rejects_symbolic_parent(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    (actual / "current.json").write_bytes(_CANDIDATE)
    (tmp_path / "locks").symlink_to(actual, target_is_directory=True)
    workspace = _workspace(tmp_path)
    try:
        with pytest.raises(ByteCarrierError, match="Not a directory"):
            publication_module._check_candidate_bytes(
                workspace,
                "locks/current.json",
                _CANDIDATE,
            )
    finally:
        workspace.close()


def test_publication_creates_absent_exact_file(tmp_path: Path) -> None:
    (tmp_path / "locks").mkdir()
    workspace = _workspace(tmp_path)
    try:
        outcome = publication_module._publish_candidate_bytes(
            workspace,
            "locks/generated.json",
            _CANDIDATE,
            temporary_name_factory=lambda: ".fixed-eutaxis.tmp",
        )

        assert outcome.temporary_residue is None
        assert (tmp_path / "locks/generated.json").read_bytes() == _CANDIDATE
        assert not (tmp_path / "locks/.fixed-eutaxis.tmp").exists()
    finally:
        workspace.close()


def test_publication_never_replaces_existing_destination(tmp_path: Path) -> None:
    (tmp_path / "locks").mkdir()
    destination = tmp_path / "locks/generated.json"
    destination.write_bytes(b"reviewed\n")
    workspace = _workspace(tmp_path)
    try:
        with pytest.raises(
            publication_module._LockPublicationError,
            match="already exists",
        ):
            publication_module._publish_candidate_bytes(
                workspace,
                "locks/generated.json",
                _CANDIDATE,
                temporary_name_factory=lambda: ".fixed-eutaxis.tmp",
            )

        assert destination.read_bytes() == b"reviewed\n"
        assert not (tmp_path / "locks/.fixed-eutaxis.tmp").exists()
    finally:
        workspace.close()


def test_post_commit_temporary_cleanup_reports_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "locks").mkdir()
    workspace = _workspace(tmp_path)
    original_unlink = publication_module._unlink_name

    def retain_temporary(parent, name: str):
        if name == ".fixed-eutaxis.tmp":
            raise OSError("injected temporary cleanup failure")
        return original_unlink(parent, name)

    monkeypatch.setattr(publication_module, "_unlink_name", retain_temporary)
    try:
        outcome = publication_module._publish_candidate_bytes(
            workspace,
            "locks/generated.json",
            _CANDIDATE,
            temporary_name_factory=lambda: ".fixed-eutaxis.tmp",
        )

        assert outcome.temporary_residue == "locks/.fixed-eutaxis.tmp"
        assert (tmp_path / "locks/generated.json").read_bytes() == _CANDIDATE
        assert (tmp_path / "locks/.fixed-eutaxis.tmp").read_bytes() == _CANDIDATE
    finally:
        workspace.close()


def test_precommit_mismatch_removes_owned_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "locks").mkdir()
    workspace = _workspace(tmp_path)
    original_verified = publication_module._verified_exact_file
    reads = 0

    def fail_final(parent, name: str, expected: bytes):
        nonlocal reads
        reads += 1
        if name == "generated.json":
            raise publication_module._LockPublicationError(
                name,
                "injected final mismatch",
            )
        return original_verified(parent, name, expected)

    monkeypatch.setattr(publication_module, "_verified_exact_file", fail_final)
    try:
        with pytest.raises(
            publication_module._LockPublicationError,
            match="injected final mismatch",
        ):
            publication_module._publish_candidate_bytes(
                workspace,
                "locks/generated.json",
                _CANDIDATE,
                temporary_name_factory=lambda: ".fixed-eutaxis.tmp",
            )

        assert reads >= 2
        assert not (tmp_path / "locks/generated.json").exists()
        assert not (tmp_path / "locks/.fixed-eutaxis.tmp").exists()
    finally:
        workspace.close()


def test_concurrent_publishers_yield_one_success(tmp_path: Path) -> None:
    (tmp_path / "locks").mkdir()
    first = _workspace(tmp_path)
    second = _workspace(tmp_path)
    try:
        publication_module._publish_candidate_bytes(
            first,
            "locks/generated.json",
            _CANDIDATE,
            temporary_name_factory=lambda: ".first-eutaxis.tmp",
        )
        with pytest.raises(
            publication_module._LockPublicationError,
            match="already exists",
        ):
            publication_module._publish_candidate_bytes(
                second,
                "locks/generated.json",
                b"other\n",
                temporary_name_factory=lambda: ".second-eutaxis.tmp",
            )

        assert (tmp_path / "locks/generated.json").read_bytes() == _CANDIDATE
        assert not (tmp_path / "locks/.second-eutaxis.tmp").exists()
    finally:
        first.close()
        second.close()


def test_partial_writes_are_completed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "locks").mkdir()
    workspace = _workspace(tmp_path)
    original_write = os.write

    def partial_write(descriptor: int, data: bytes) -> int:
        return original_write(descriptor, data[: max(1, len(data) // 2)])

    monkeypatch.setattr(publication_module.os, "write", partial_write)
    try:
        publication_module._publish_candidate_bytes(
            workspace,
            "locks/generated.json",
            _CANDIDATE,
            temporary_name_factory=lambda: ".fixed-eutaxis.tmp",
        )
        assert (tmp_path / "locks/generated.json").read_bytes() == _CANDIDATE
    finally:
        workspace.close()


def test_temporary_mutation_before_link_rolls_back_both_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locks = tmp_path / "locks"
    locks.mkdir()
    workspace = _workspace(tmp_path)
    original_link = publication_module._link_names

    def mutate_then_link(parent, source: str, destination: str, path: str):
        (locks / source).write_bytes(b"mutated\n")
        return original_link(parent, source, destination, path)

    monkeypatch.setattr(publication_module, "_link_names", mutate_then_link)
    try:
        with pytest.raises(
            publication_module._LockPublicationError,
            match="bytes differ",
        ):
            publication_module._publish_candidate_bytes(
                workspace,
                "locks/generated.json",
                _CANDIDATE,
                temporary_name_factory=lambda: ".fixed-eutaxis.tmp",
            )

        assert not (locks / "generated.json").exists()
        assert not (locks / ".fixed-eutaxis.tmp").exists()
    finally:
        workspace.close()


def test_temporary_replacement_reports_destination_may_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locks = tmp_path / "locks"
    locks.mkdir()
    workspace = _workspace(tmp_path)
    original_link = publication_module._link_names

    def replace_then_link(parent, source: str, destination: str, path: str):
        (locks / source).unlink()
        (locks / source).write_bytes(b"foreign\n")
        return original_link(parent, source, destination, path)

    monkeypatch.setattr(publication_module, "_link_names", replace_then_link)
    try:
        with pytest.raises(
            publication_module._LockPublicationError,
            match="destination may exist",
        ) as raised:
            publication_module._publish_candidate_bytes(
                workspace,
                "locks/generated.json",
                _CANDIDATE,
                temporary_name_factory=lambda: ".fixed-eutaxis.tmp",
            )

        assert raised.value.destination_may_exist
        assert (locks / "generated.json").read_bytes() == b"foreign\n"
        assert (locks / ".fixed-eutaxis.tmp").read_bytes() == b"foreign\n"
    finally:
        workspace.close()


def test_temporary_name_cannot_equal_destination(tmp_path: Path) -> None:
    (tmp_path / "locks").mkdir()
    workspace = _workspace(tmp_path)
    try:
        with pytest.raises(
            publication_module._LockPublicationError,
            match="equals the destination",
        ):
            publication_module._publish_candidate_bytes(
                workspace,
                "locks/generated.json",
                _CANDIDATE,
                temporary_name_factory=lambda: "generated.json",
            )
        assert not (tmp_path / "locks/generated.json").exists()
    finally:
        workspace.close()


def test_successful_link_with_cleanup_failure_is_rolled_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locks = tmp_path / "locks"
    locks.mkdir()
    workspace = _workspace(tmp_path)
    original_link = publication_module._link_names

    def link_then_report_cleanup(parent, source: str, destination: str, path: str):
        outcome = original_link(parent, source, destination, path)
        assert outcome.created
        return publication_module._LinkOutcome(
            True,
            OSError("injected link-descriptor cleanup failure"),
        )

    monkeypatch.setattr(
        publication_module,
        "_link_names",
        link_then_report_cleanup,
    )
    try:
        with pytest.raises(OSError, match="link-descriptor cleanup failure"):
            publication_module._publish_candidate_bytes(
                workspace,
                "locks/generated.json",
                _CANDIDATE,
                temporary_name_factory=lambda: ".fixed-eutaxis.tmp",
            )
        assert not (locks / "generated.json").exists()
        assert not (locks / ".fixed-eutaxis.tmp").exists()
    finally:
        workspace.close()


def test_mutate_and_restore_before_final_verification_fails_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locks = tmp_path / "locks"
    locks.mkdir()
    workspace = _workspace(tmp_path)
    original_verified = publication_module._verified_exact_file

    def mutate_restore_then_verify(parent, name: str, expected: bytes):
        if name == "generated.json":
            (locks / name).write_bytes(b"mutated\n")
            (locks / name).write_bytes(expected)
        return original_verified(parent, name, expected)

    monkeypatch.setattr(
        publication_module,
        "_verified_exact_file",
        mutate_restore_then_verify,
    )
    try:
        with pytest.raises(
            publication_module._LockPublicationError,
            match="metadata differs",
        ):
            publication_module._publish_candidate_bytes(
                workspace,
                "locks/generated.json",
                _CANDIDATE,
                temporary_name_factory=lambda: ".fixed-eutaxis.tmp",
            )
        assert not (locks / "generated.json").exists()
        assert not (locks / ".fixed-eutaxis.tmp").exists()
    finally:
        workspace.close()


def test_setup_failure_preserves_foreign_temporary_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locks = tmp_path / "locks"
    locks.mkdir()
    temporary = locks / ".fixed-eutaxis.tmp"
    workspace = _workspace(tmp_path)
    original_set_inheritable = os.set_inheritable

    def replace_then_fail(descriptor: int, inheritable: bool) -> None:
        if (
            temporary.exists()
            and os.fstat(descriptor).st_ino == temporary.stat().st_ino
        ):
            temporary.unlink()
            temporary.write_bytes(b"foreign\n")
            raise OSError("injected temporary setup failure")
        original_set_inheritable(descriptor, inheritable)

    monkeypatch.setattr(publication_module.os, "set_inheritable", replace_then_fail)
    try:
        with pytest.raises(
            publication_module._LockPublicationError,
            match="setup failed",
        ) as raised:
            publication_module._publish_candidate_bytes(
                workspace,
                "locks/generated.json",
                _CANDIDATE,
                temporary_name_factory=lambda: temporary.name,
            )
        assert raised.value.temporary_residue == "locks/.fixed-eutaxis.tmp"
        assert temporary.read_bytes() == b"foreign\n"
        assert not (locks / "generated.json").exists()
    finally:
        workspace.close()


def test_final_unlink_failure_reports_no_cleaned_temporary_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locks = tmp_path / "locks"
    locks.mkdir()
    workspace = _workspace(tmp_path)
    original_verified = publication_module._verified_exact_file
    original_unlink = publication_module._unlink_name
    original_cause = ValueError("original verification cause")
    primary = RuntimeError("injected final verification failure")
    primary.__cause__ = original_cause

    def fail_final(parent, name: str, expected: bytes):
        if name == "generated.json":
            raise primary
        return original_verified(parent, name, expected)

    def fail_destination_unlink(parent, name: str):
        if name == "generated.json":
            raise OSError("injected final-name unlink failure")
        return original_unlink(parent, name)

    monkeypatch.setattr(publication_module, "_verified_exact_file", fail_final)
    monkeypatch.setattr(publication_module, "_unlink_name", fail_destination_unlink)
    try:
        with pytest.raises(
            publication_module._LockPublicationError,
            match="destination may exist",
        ) as raised:
            publication_module._publish_candidate_bytes(
                workspace,
                "locks/generated.json",
                _CANDIDATE,
                temporary_name_factory=lambda: ".fixed-eutaxis.tmp",
            )
        assert raised.value.destination_may_exist
        assert raised.value.temporary_residue is None
        assert raised.value.__cause__ is primary
        assert isinstance(primary.__cause__, OSError)
        assert primary.__cause__.__cause__ is original_cause
        assert (locks / "generated.json").exists()
        assert not (locks / ".fixed-eutaxis.tmp").exists()
    finally:
        workspace.close()


def test_publication_rejects_missing_descriptor_operations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "locks").mkdir()
    workspace = _workspace(tmp_path)
    supported = set(os.supports_dir_fd)
    supported.discard(os.link)
    monkeypatch.setattr(publication_module.os, "supports_dir_fd", supported)
    try:
        with pytest.raises(
            publication_module._LockPublicationError,
            match="unsupported descriptor platform: linkat",
        ):
            publication_module._publish_candidate_bytes(
                workspace,
                "locks/generated.json",
                _CANDIDATE,
            )
        assert not (tmp_path / "locks/generated.json").exists()
    finally:
        workspace.close()


def test_post_commit_descriptor_close_failure_cannot_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locks = tmp_path / "locks"
    locks.mkdir()
    workspace = _workspace(tmp_path)
    captured: dict[str, int] = {}
    original_open = publication_module._open_temporary
    original_unlink = publication_module._unlink_name
    original_close = os.close
    failed = False

    def capture_open(*args, **kwargs):
        outcome = original_open(*args, **kwargs)
        captured["descriptor"] = outcome.descriptor
        return outcome

    def fail_retained_close(descriptor: int) -> None:
        nonlocal failed
        if descriptor == captured.get("descriptor") and not failed:
            failed = True
            raise OSError("injected post-commit descriptor close failure")
        original_close(descriptor)

    def unlink_then_report(parent, name: str):
        outcome = original_unlink(parent, name)
        return publication_module._UnlinkOutcome(
            outcome.removed_or_absent,
            OSError("injected unlink cleanup failure"),
        )

    monkeypatch.setattr(publication_module, "_open_temporary", capture_open)
    monkeypatch.setattr(publication_module.os, "close", fail_retained_close)
    monkeypatch.setattr(publication_module, "_unlink_name", unlink_then_report)
    try:
        outcome = publication_module._publish_candidate_bytes(
            workspace,
            "locks/generated.json",
            _CANDIDATE,
            temporary_name_factory=lambda: ".fixed-eutaxis.tmp",
        )
        assert failed
        assert outcome.temporary_residue is None
        assert "descriptor cleanup failed" in (outcome.cleanup_warning or "")
        assert "unlink cleanup failure" in (outcome.cleanup_warning or "")
        assert (locks / "generated.json").read_bytes() == _CANDIDATE
        assert not (locks / ".fixed-eutaxis.tmp").exists()
    finally:
        monkeypatch.setattr(publication_module.os, "close", original_close)
        descriptor = captured.get("descriptor")
        if descriptor is not None:
            try:
                original_close(descriptor)
            except OSError:
                pass
        workspace.close()


def test_created_temporary_survives_parent_close_report_for_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locks = tmp_path / "locks"
    locks.mkdir()
    workspace = _workspace(tmp_path)
    original_open = publication_module._open_temporary

    def report_parent_close(*args, **kwargs):
        outcome = original_open(*args, **kwargs)
        return publication_module._TemporaryOpenOutcome(
            outcome.name,
            outcome.descriptor,
            outcome.metadata,
            OSError("injected parent-descriptor close failure"),
        )

    monkeypatch.setattr(publication_module, "_open_temporary", report_parent_close)
    try:
        with pytest.raises(OSError, match="parent-descriptor close failure"):
            publication_module._publish_candidate_bytes(
                workspace,
                "locks/generated.json",
                _CANDIDATE,
                temporary_name_factory=lambda: ".fixed-eutaxis.tmp",
            )
        assert not (locks / "generated.json").exists()
        assert not (locks / ".fixed-eutaxis.tmp").exists()
    finally:
        workspace.close()


def test_unlink_success_with_close_report_has_no_false_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locks = tmp_path / "locks"
    locks.mkdir()
    workspace = _workspace(tmp_path)
    original_unlink = publication_module._unlink_name

    def unlink_then_report(parent, name: str):
        outcome = original_unlink(parent, name)
        return publication_module._UnlinkOutcome(
            outcome.removed_or_absent,
            OSError("injected unlink-descriptor close failure"),
        )

    monkeypatch.setattr(publication_module, "_unlink_name", unlink_then_report)
    try:
        outcome = publication_module._publish_candidate_bytes(
            workspace,
            "locks/generated.json",
            _CANDIDATE,
            temporary_name_factory=lambda: ".fixed-eutaxis.tmp",
        )
        assert outcome.temporary_residue is None
        assert "unlink-descriptor close failure" in (outcome.cleanup_warning or "")
        assert (locks / "generated.json").read_bytes() == _CANDIDATE
        assert not (locks / ".fixed-eutaxis.tmp").exists()
    finally:
        workspace.close()


def test_publication_rejects_missing_statat_before_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "locks").mkdir()
    workspace = _workspace(tmp_path)
    supported = set(os.supports_dir_fd)
    supported.discard(os.stat)
    monkeypatch.setattr(publication_module.os, "supports_dir_fd", supported)
    try:
        with pytest.raises(
            publication_module._LockPublicationError,
            match="unsupported descriptor platform: statat",
        ):
            publication_module._publish_candidate_bytes(
                workspace,
                "locks/generated.json",
                _CANDIDATE,
            )
        assert not (tmp_path / "locks/generated.json").exists()
    finally:
        workspace.close()


def test_retained_parent_close_failure_is_post_commit_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locks = tmp_path / "locks"
    locks.mkdir()
    workspace = _workspace(tmp_path)
    original_close = publication_module.RetainedDirectory.close
    captured: list[publication_module.RetainedDirectory] = []
    failed = False

    def fail_parent_close(parent) -> None:
        nonlocal failed
        if parent.path == "locks" and not failed:
            failed = True
            captured.append(parent)
            raise OSError("injected retained-parent close failure")
        original_close(parent)

    monkeypatch.setattr(
        publication_module.RetainedDirectory,
        "close",
        fail_parent_close,
    )
    try:
        outcome = publication_module._publish_candidate_bytes(
            workspace,
            "locks/generated.json",
            _CANDIDATE,
            temporary_name_factory=lambda: ".fixed-eutaxis.tmp",
        )
        assert failed
        assert outcome.temporary_residue is None
        assert "retained parent cleanup failed" in (outcome.cleanup_warning or "")
        assert (locks / "generated.json").read_bytes() == _CANDIDATE
    finally:
        monkeypatch.setattr(
            publication_module.RetainedDirectory,
            "close",
            original_close,
        )
        for parent in captured:
            original_close(parent)
        workspace.close()


def test_post_commit_probe_failure_returns_possible_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locks = tmp_path / "locks"
    locks.mkdir()
    workspace = _workspace(tmp_path)

    def fail_cleanup(*_args, **_kwargs):
        raise OSError("injected temporary cleanup failure")

    def fail_probe(*_args, **_kwargs):
        raise OSError("injected residue probe failure")

    monkeypatch.setattr(publication_module, "_unlink_owned_name", fail_cleanup)
    monkeypatch.setattr(publication_module, "_name_is_absent", fail_probe)
    try:
        outcome = publication_module._publish_candidate_bytes(
            workspace,
            "locks/generated.json",
            _CANDIDATE,
            temporary_name_factory=lambda: ".fixed-eutaxis.tmp",
        )
        assert outcome.temporary_residue == "locks/.fixed-eutaxis.tmp"
        assert "temporary cleanup failed" in (outcome.cleanup_warning or "")
        assert "residue probe failed" in (outcome.cleanup_warning or "")
        assert (locks / "generated.json").read_bytes() == _CANDIDATE
    finally:
        workspace.close()


def test_setup_probe_failure_remains_secondary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    locks = tmp_path / "locks"
    locks.mkdir()
    workspace = _workspace(tmp_path)
    original_metadata = publication_module._file_metadata

    def fail_created_metadata(descriptor: int, path: str):
        if path == ".fixed-eutaxis.tmp":
            raise OSError("injected setup metadata failure")
        return original_metadata(descriptor, path)

    def fail_probe(*_args, **_kwargs):
        raise OSError("injected setup residue probe failure")

    monkeypatch.setattr(publication_module, "_file_metadata", fail_created_metadata)
    monkeypatch.setattr(publication_module, "_name_is_absent", fail_probe)
    try:
        with pytest.raises(
            publication_module._LockPublicationError,
            match="temporary-file setup failed",
        ) as raised:
            publication_module._publish_candidate_bytes(
                workspace,
                "locks/generated.json",
                _CANDIDATE,
                temporary_name_factory=lambda: ".fixed-eutaxis.tmp",
            )
        assert raised.value.temporary_residue == "locks/.fixed-eutaxis.tmp"
        assert isinstance(raised.value.__cause__, OSError)
        assert "setup metadata failure" in str(raised.value.__cause__)
        assert not (locks / "generated.json").exists()
    finally:
        workspace.close()
