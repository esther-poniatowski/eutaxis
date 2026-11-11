"""Check or create generated lock bytes through retained directory descriptors."""

from __future__ import annotations

import os
import secrets
import stat
from collections.abc import Callable
from dataclasses import dataclass

from .acquisition_paths import AcquisitionPathError, normalized_path_components
from .byte_carriers import (
    FileMetadata,
    RetainedDirectory,
    TrustedDirectory,
    VerifiedByteCarrier,
    _borrow_retained_descriptor,
    _file_metadata,
)

_TEMPORARY_ATTEMPTS = 128
_WRITE_MODE = 0o600


class _LockPublicationError(Exception):
    """Report one failed checked-lock or create-only publication operation."""

    def __init__(
        self,
        path: str,
        message: str,
        *,
        destination_may_exist: bool = False,
        temporary_residue: str | None = None,
    ) -> None:
        super().__init__(f"Lock publication failed at {path!r}: {message}")
        self.path = path
        self.detail = message
        self.destination_may_exist = destination_may_exist
        self.temporary_residue = temporary_residue


@dataclass(frozen=True)
class _LockPublicationOutcome:
    """Describe a committed publication and any post-commit temporary residue."""

    temporary_residue: str | None = None
    cleanup_warning: str | None = None


@dataclass(frozen=True)
class _LinkOutcome:
    """Record hard-link creation independently of descriptor cleanup."""

    created: bool
    cleanup_error: BaseException | None = None


@dataclass(frozen=True)
class _TemporaryOpenOutcome:
    """Transfer a created temporary inode despite parent-descriptor cleanup."""

    name: str
    descriptor: int
    metadata: FileMetadata
    cleanup_error: BaseException | None = None


@dataclass(frozen=True)
class _UnlinkOutcome:
    """Record name removal independently of descriptor cleanup."""

    removed_or_absent: bool
    cleanup_error: BaseException | None = None


@dataclass(frozen=True)
class _AbsenceOutcome:
    """Record absent, present, or unknown state without throwing from cleanup."""

    absent: bool | None
    error: BaseException | None = None


def _check_candidate_bytes(
    workspace: TrustedDirectory,
    path: str,
    candidate_bytes: bytes,
) -> bool:
    """Compare exact bytes after two reads under one retained parent identity."""
    parent_path, name = _publication_target(path)
    _require_candidate_bytes(candidate_bytes, path)
    with workspace.retain_directory(parent_path) as parent:
        authoritative = parent.read_authoritative(name)
        verified = parent.verify(authoritative)
        return verified.authoritative.data == candidate_bytes


def _publish_candidate_bytes(
    workspace: TrustedDirectory,
    path: str,
    candidate_bytes: bytes,
    *,
    temporary_name_factory: Callable[[], str] | None = None,
) -> _LockPublicationOutcome:
    """Create an absent lock path without replacement and verify its exact bytes."""
    parent_path, name = _publication_target(path)
    _require_candidate_bytes(candidate_bytes, path)
    _require_publication_platform(path)
    name_factory = temporary_name_factory or _temporary_name
    parent = workspace.retain_directory(parent_path)
    try:
        outcome = _publish_under_parent(
            parent,
            path,
            name,
            candidate_bytes,
            name_factory,
        )
    except BaseException as primary_error:
        try:
            parent.close()
        except BaseException as cleanup_error:
            _attach_cleanup_cause(primary_error, cleanup_error)
        raise
    try:
        parent.close()
    except BaseException as cleanup_error:
        return _LockPublicationOutcome(
            temporary_residue=outcome.temporary_residue,
            cleanup_warning=_combined_warning(
                outcome.cleanup_warning,
                f"retained parent cleanup failed: {cleanup_error}",
            ),
        )
    return outcome


def _publish_under_parent(
    parent: RetainedDirectory,
    path: str,
    name: str,
    candidate_bytes: bytes,
    name_factory: Callable[[], str],
) -> _LockPublicationOutcome:
    """Own the temporary inode, link commit point, and cleanup transaction."""
    temporary_name: str | None = None
    temporary_metadata: FileMetadata | None = None
    linked = False
    committed = False
    temporary_descriptor = -1
    try:
        open_outcome = _open_temporary(
            parent,
            name_factory,
            forbidden_name=name,
        )
        temporary_name = open_outcome.name
        temporary_descriptor = open_outcome.descriptor
        temporary_metadata = open_outcome.metadata
        if open_outcome.cleanup_error is not None:
            raise open_outcome.cleanup_error
        temporary_metadata = _write_temporary(
            temporary_descriptor,
            temporary_name,
            candidate_bytes,
        )
        temporary = _verified_exact_file(parent, temporary_name, candidate_bytes)
        _require_same_metadata(
            temporary.authoritative.before,
            temporary_metadata,
            path,
        )

        # This final pre-link read also revalidates the retained parent identity.
        temporary = parent.verify(temporary.authoritative)
        _require_same_metadata(
            temporary.authoritative.before,
            temporary_metadata,
            path,
        )
        link_outcome = _link_names(parent, temporary_name, name, path)
        linked = link_outcome.created
        if link_outcome.cleanup_error is not None:
            raise link_outcome.cleanup_error

        post_link_metadata = _file_metadata(temporary_descriptor, temporary_name)

        published = _verified_exact_file(parent, name, candidate_bytes)
        _require_same_metadata(
            published.authoritative.before,
            post_link_metadata,
            path,
        )
        committed = True
    except BaseException as primary_error:
        if temporary_descriptor >= 0:
            descriptor_to_close = temporary_descriptor
            temporary_descriptor = -1
            try:
                os.close(descriptor_to_close)
            except BaseException as cleanup_error:
                _attach_cleanup_cause(primary_error, cleanup_error)
        _rollback_uncommitted(
            parent,
            path,
            name,
            temporary_name,
            temporary_metadata,
            linked=linked,
            primary_error=primary_error,
        )
        raise

    assert temporary_name is not None
    cleanup_warning: str | None = None
    if temporary_descriptor >= 0:
        descriptor_to_close = temporary_descriptor
        temporary_descriptor = -1
        try:
            os.close(descriptor_to_close)
        except BaseException as exc:
            cleanup_warning = f"temporary descriptor cleanup failed: {exc}"
    try:
        if temporary_metadata is None:
            return _LockPublicationOutcome(
                temporary_residue=_joined_path(parent.path, temporary_name),
                cleanup_warning=cleanup_warning,
            )
        unlink_outcome = _unlink_owned_name(
            parent,
            temporary_name,
            temporary_metadata,
        )
        if unlink_outcome.cleanup_error is not None:
            cleanup_warning = _combined_warning(
                cleanup_warning,
                f"temporary cleanup failed: {unlink_outcome.cleanup_error}",
            )
        if not unlink_outcome.removed_or_absent:
            return _LockPublicationOutcome(
                temporary_residue=_joined_path(parent.path, temporary_name),
                cleanup_warning=cleanup_warning,
            )
    except BaseException as exc:
        absence = _observe_absence(parent, temporary_name)
        return _LockPublicationOutcome(
            temporary_residue=(
                None
                if absence.absent is True
                else _joined_path(parent.path, temporary_name)
            ),
            cleanup_warning=_combined_warning(
                cleanup_warning,
                _combined_warning(
                    f"temporary cleanup failed: {exc}",
                    (
                        f"temporary residue probe failed: {absence.error}"
                        if absence.error is not None
                        else None
                    ),
                ),
            ),
        )
    if not committed:
        raise AssertionError("lock publication did not reach its commit point")
    return _LockPublicationOutcome(cleanup_warning=cleanup_warning)


def _open_temporary(
    parent: RetainedDirectory,
    name_factory: Callable[[], str],
    *,
    forbidden_name: str,
) -> _TemporaryOpenOutcome:
    """Open and retain one exclusively created sibling inode for writing."""
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC")
        | getattr(os, "O_NOFOLLOW")
    )
    descriptor = _borrow_retained_descriptor(parent, parent=False)
    outcome: _TemporaryOpenOutcome | None = None
    try:
        for _attempt in range(_TEMPORARY_ATTEMPTS):
            name = _normalized_temporary_name(name_factory())
            if name == forbidden_name:
                raise _LockPublicationError(
                    name,
                    "temporary name equals the destination",
                )
            try:
                temporary = os.open(name, flags, _WRITE_MODE, dir_fd=descriptor)
            except FileExistsError:
                continue
            metadata: FileMetadata | None = None
            try:
                metadata = _file_metadata(temporary, name)
                os.set_inheritable(temporary, False)
            except BaseException as primary_error:
                setup_cleanup_error: BaseException | None = None
                try:
                    os.close(temporary)
                except BaseException as exc:
                    setup_cleanup_error = exc
                if metadata is not None:
                    try:
                        removal = _unlink_owned_name(parent, name, metadata)
                        if not removal.removed_or_absent:
                            raise _LockPublicationError(
                                name,
                                "temporary setup failed; temporary name may remain",
                                temporary_residue=_joined_path(parent.path, name),
                            )
                        if removal.cleanup_error is not None:
                            raise removal.cleanup_error
                    except BaseException as exc:
                        if setup_cleanup_error is None:
                            setup_cleanup_error = exc
                if setup_cleanup_error is not None:
                    _attach_cleanup_cause(primary_error, setup_cleanup_error)
                absence = _observe_absence(parent, name)
                if absence.error is not None:
                    _attach_cleanup_cause(primary_error, absence.error)
                error = _LockPublicationError(
                    name,
                    "temporary-file setup failed",
                    temporary_residue=(
                        None
                        if metadata is not None and absence.absent is True
                        else _joined_path(parent.path, name)
                    ),
                )
                error.__cause__ = primary_error
                raise error
            outcome = _TemporaryOpenOutcome(name, temporary, metadata)
            break
    except BaseException as primary_error:
        try:
            os.close(descriptor)
        except BaseException as descriptor_cleanup_error:
            _attach_cleanup_cause(primary_error, descriptor_cleanup_error)
        if isinstance(primary_error, OSError):
            raise _LockPublicationError(
                parent.path, str(primary_error)
            ) from primary_error
        raise
    parent_cleanup_error: BaseException | None = None
    try:
        os.close(descriptor)
    except BaseException as exc:
        parent_cleanup_error = exc
    if outcome is None:
        error = _LockPublicationError(
            parent.path,
            "temporary-name attempts exhausted",
        )
        if parent_cleanup_error is not None:
            error.__cause__ = parent_cleanup_error
        raise error
    return _TemporaryOpenOutcome(
        outcome.name,
        outcome.descriptor,
        outcome.metadata,
        parent_cleanup_error,
    )


def _write_temporary(
    descriptor: int,
    name: str,
    candidate_bytes: bytes,
) -> FileMetadata:
    """Write complete candidate bytes through the retained temporary descriptor."""
    try:
        offset = 0
        while offset < len(candidate_bytes):
            written = os.write(descriptor, candidate_bytes[offset:])
            if written <= 0:
                raise OSError("temporary-file write made no progress")
            offset += written
        metadata = _file_metadata(descriptor, name)
        if metadata.size != len(candidate_bytes):
            raise OSError("temporary-file size differs from candidate bytes")
        return metadata
    except OSError as exc:
        raise _LockPublicationError(name, str(exc)) from exc


def _verified_exact_file(
    parent: RetainedDirectory,
    name: str,
    expected: bytes,
) -> VerifiedByteCarrier:
    """Return two-read evidence for one exact regular file."""
    authoritative = parent.read_authoritative(name)
    verified = parent.verify(authoritative)
    if verified.authoritative.data != expected:
        raise _LockPublicationError(name, "published bytes differ from candidate")
    return verified


def _link_names(
    parent: RetainedDirectory,
    source: str,
    destination: str,
    path: str,
) -> _LinkOutcome:
    """Create the final name by no-replace hard link under one parent descriptor."""
    descriptor = _borrow_retained_descriptor(parent, parent=False)
    created = False
    primary_error: BaseException | None = None
    try:
        os.link(
            source,
            destination,
            src_dir_fd=descriptor,
            dst_dir_fd=descriptor,
            follow_symlinks=False,
        )
        created = True
    except FileExistsError as exc:
        primary_error = _LockPublicationError(path, "destination already exists")
        primary_error.__cause__ = exc
    except (OSError, TypeError, NotImplementedError) as exc:
        primary_error = _LockPublicationError(path, str(exc))
        primary_error.__cause__ = exc
    cleanup_error: BaseException | None = None
    try:
        os.close(descriptor)
    except BaseException as exc:
        cleanup_error = exc
    if primary_error is not None:
        if cleanup_error is not None:
            _attach_cleanup_cause(primary_error, cleanup_error)
        raise primary_error
    return _LinkOutcome(created, cleanup_error)


def _unlink_name(parent: RetainedDirectory, name: str) -> _UnlinkOutcome:
    """Remove one exact sibling name through the retained parent descriptor."""
    descriptor = _borrow_retained_descriptor(parent, parent=False)
    removed = False
    primary_error: BaseException | None = None
    try:
        os.unlink(name, dir_fd=descriptor)
        removed = True
    except (TypeError, NotImplementedError) as exc:
        primary_error = _LockPublicationError(name, str(exc))
        primary_error.__cause__ = exc
    except BaseException as exc:
        primary_error = exc
    cleanup_error: BaseException | None = None
    try:
        os.close(descriptor)
    except BaseException as exc:
        cleanup_error = exc
    if primary_error is not None:
        if cleanup_error is not None:
            _attach_cleanup_cause(primary_error, cleanup_error)
        raise primary_error
    return _UnlinkOutcome(removed, cleanup_error)


def _rollback_uncommitted(
    parent: RetainedDirectory,
    path: str,
    destination: str,
    temporary: str | None,
    temporary_metadata: FileMetadata | None,
    *,
    linked: bool,
    primary_error: BaseException,
) -> None:
    """Remove only names still proven to identify the transaction's inode."""
    cleanup_error: BaseException | None = None
    destination_may_exist = False
    temporary_remains = False
    if linked:
        try:
            if temporary_metadata is None or not _name_has_identity(
                parent,
                destination,
                temporary_metadata,
            ):
                destination_may_exist = True
            else:
                destination_unlink = _unlink_name(parent, destination)
                if destination_unlink.cleanup_error is not None:
                    cleanup_error = destination_unlink.cleanup_error
                destination_may_exist = not destination_unlink.removed_or_absent
        except BaseException as exc:
            absence = _observe_absence(parent, destination)
            destination_may_exist = absence.absent is not True
            cleanup_error = exc
            if absence.error is not None:
                _attach_cleanup_cause(cleanup_error, absence.error)
    if temporary is not None:
        try:
            if temporary_metadata is None:
                raise _LockPublicationError(
                    temporary,
                    "temporary name no longer identifies the created inode",
                    temporary_residue=_joined_path(parent.path, temporary),
                )
            temporary_unlink = _unlink_owned_name(
                parent,
                temporary,
                temporary_metadata,
            )
            if temporary_unlink.cleanup_error is not None:
                if cleanup_error is None:
                    cleanup_error = temporary_unlink.cleanup_error
            if not temporary_unlink.removed_or_absent:
                raise _LockPublicationError(
                    temporary,
                    "temporary name no longer identifies the created inode",
                    temporary_residue=_joined_path(parent.path, temporary),
                )
        except BaseException as exc:
            if cleanup_error is None:
                cleanup_error = exc
            temporary_remains = True
    if destination_may_exist:
        error = _LockPublicationError(
            path,
            "publication failed; destination may exist",
            destination_may_exist=True,
            temporary_residue=(
                _joined_path(parent.path, temporary)
                if temporary is not None and temporary_remains
                else None
            ),
        )
        error.__cause__ = primary_error
        if cleanup_error is not None:
            _attach_cleanup_cause(primary_error, cleanup_error)
        raise error
    if cleanup_error is not None:
        _attach_cleanup_cause(primary_error, cleanup_error)


def _name_has_identity(
    parent: RetainedDirectory,
    name: str,
    expected: FileMetadata,
) -> bool:
    """Return whether one sibling still identifies the transaction's inode."""
    descriptor = _borrow_retained_descriptor(parent, parent=False)
    try:
        observed = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
    finally:
        os.close(descriptor)
    return (
        stat.S_ISREG(observed.st_mode)
        and observed.st_dev == expected.device
        and observed.st_ino == expected.inode
    )


def _unlink_owned_name(
    parent: RetainedDirectory,
    name: str,
    expected: FileMetadata,
) -> _UnlinkOutcome:
    """Remove a sibling only while it still identifies the owned inode."""
    try:
        if not _name_has_identity(parent, name, expected):
            return _UnlinkOutcome(False)
    except FileNotFoundError:
        return _UnlinkOutcome(True)
    return _unlink_name(parent, name)


def _require_same_metadata(
    actual: FileMetadata,
    expected: FileMetadata,
    path: str,
) -> None:
    """Require final file identity and metadata to match the post-link snapshot."""
    if actual != expected:
        raise _LockPublicationError(path, "published metadata differs from temporary")


def _name_is_absent(parent: RetainedDirectory, name: str) -> bool:
    """Measure whether one sibling name is absent after cleanup."""
    descriptor = _borrow_retained_descriptor(parent, parent=False)
    try:
        try:
            os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return True
        return False
    finally:
        os.close(descriptor)


def _observe_absence(parent: RetainedDirectory, name: str) -> _AbsenceOutcome:
    """Measure name absence without allowing a cleanup probe to escape."""
    try:
        return _AbsenceOutcome(_name_is_absent(parent, name))
    except BaseException as error:
        return _AbsenceOutcome(None, error)


def _attach_cleanup_cause(
    primary_error: BaseException,
    cleanup_error: BaseException,
) -> None:
    """Attach cleanup failure without discarding an existing cause chain."""
    if cleanup_error is primary_error:
        return
    prior_cause = primary_error.__cause__
    cursor = cleanup_error
    seen: set[int] = set()
    contains_prior = False
    while True:
        if cursor is primary_error or id(cursor) in seen:
            return
        if cursor is prior_cause:
            contains_prior = True
        seen.add(id(cursor))
        if cursor.__cause__ is None:
            break
        cursor = cursor.__cause__
    if prior_cause is not None and not contains_prior:
        cursor.__cause__ = prior_cause
    primary_error.__cause__ = cleanup_error


def _combined_warning(first: str | None, second: str | None) -> str | None:
    """Combine independent post-commit cleanup diagnostics without loss."""
    if first is None:
        return second
    if second is None:
        return first
    return f"{first}; {second}"


def _require_publication_platform(path: str) -> None:
    """Require descriptor-relative link and unlink operations before writing."""
    supported: set[object] = getattr(os, "supports_dir_fd", set())
    missing = [
        name
        for name, operation in (
            ("linkat", os.link),
            ("unlinkat", os.unlink),
            ("statat", os.stat),
        )
        if operation not in supported
    ]
    follow_supported: set[object] = getattr(os, "supports_follow_symlinks", set())
    if os.stat not in follow_supported:
        missing.append("statat-nofollow")
    if missing:
        raise _LockPublicationError(
            path,
            "unsupported descriptor platform: " + ", ".join(missing),
        )


def _publication_target(value: object) -> tuple[str, str]:
    """Return the normalized destination parent and basename."""
    try:
        components = normalized_path_components(value, allow_dot=False)
    except AcquisitionPathError as exc:
        raise _LockPublicationError(str(value), str(exc)) from exc
    path = str(value)
    parent = "/".join(components[:-1]) or "."
    return parent, components[-1]


def _require_candidate_bytes(value: object, path: str) -> None:
    """Require exact immutable candidate bytes at the publication boundary."""
    if type(value) is not bytes:
        raise _LockPublicationError(path, "candidate must be exact bytes")


def _normalized_temporary_name(value: object) -> str:
    """Admit one generated sibling basename and no path traversal."""
    try:
        components = normalized_path_components(value, allow_dot=False)
    except AcquisitionPathError as exc:
        raise _LockPublicationError(str(value), str(exc)) from exc
    if len(components) != 1:
        raise _LockPublicationError(str(value), "temporary name must be a basename")
    return components[0]


def _temporary_name() -> str:
    """Return one bounded random sibling name for exclusive creation."""
    return f".eutaxis-lock-{secrets.token_hex(12)}.tmp"


def _joined_path(parent: str, name: str) -> str:
    """Render one workspace-relative sibling path for diagnostics."""
    return name if parent == "." else f"{parent}/{name}"
