"""Retain and verify files through no-follow directory capabilities."""

from __future__ import annotations

import hashlib
import os
import stat
from _thread import LockType
from dataclasses import dataclass
from threading import Lock
from typing import NoReturn, SupportsIndex, cast

from ._authority import IdentityAuthorityStore
from .acquisition_paths import AcquisitionPathError, normalized_path_components
from .canonical_json import CanonicalJsonError, require_unicode_scalar_text
from .exceptions import ByteCarrierError

_READ_SIZE = 1024 * 1024

_MetadataSnapshot = tuple[int, int, int, int, int, int]
_CarrierSnapshot = tuple[
    str,
    bytes,
    str,
    _MetadataSnapshot,
    _MetadataSnapshot,
]


@dataclass(frozen=True)
class DirectoryIdentity:
    """Identify one retained directory within its filesystem."""

    device: int
    inode: int


@dataclass(frozen=True)
class FileMetadata:
    """Retain the metadata that must remain stable across one file read."""

    device: int
    inode: int
    mode: int
    size: int
    modified_ns: int
    changed_ns: int


class AuthoritativeByteCarrier:
    """Retain one authoritative read and its surrounding metadata."""

    __slots__ = ("__weakref__",)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("AuthoritativeByteCarrier instances must be issued by reading")

    @property
    def path(self) -> str:
        """Return the normalized path captured by the issued read."""
        return _issued_carrier_snapshot(self)[0]

    @property
    def data(self) -> bytes:
        """Return the exact bytes captured by the issued read."""
        return _issued_carrier_snapshot(self)[1]

    @property
    def sha256(self) -> str:
        """Return the digest of the captured bytes."""
        return _issued_carrier_snapshot(self)[2]

    @property
    def before(self) -> FileMetadata:
        """Return metadata captured before reading."""
        return _metadata_from_snapshot(_issued_carrier_snapshot(self)[3])

    @property
    def after(self) -> FileMetadata:
        """Return metadata captured after reading."""
        return _metadata_from_snapshot(_issued_carrier_snapshot(self)[4])

    def __copy__(self) -> NoReturn:
        raise TypeError("AuthoritativeByteCarrier instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("AuthoritativeByteCarrier instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("AuthoritativeByteCarrier instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("AuthoritativeByteCarrier instances cannot be serialized")


class VerifiedByteCarrier:
    """Retain matching authoritative and verification observations."""

    __slots__ = ("__weakref__",)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("VerifiedByteCarrier instances must be issued by verification")

    @property
    def authoritative(self) -> AuthoritativeByteCarrier:
        """Return the authoritative observation admitted by verification."""
        return _issued_verified_state(self)[3]

    @property
    def verification(self) -> AuthoritativeByteCarrier:
        """Return the independent matching observation."""
        return _issued_verified_state(self)[4]

    def __copy__(self) -> NoReturn:
        raise TypeError("VerifiedByteCarrier instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("VerifiedByteCarrier instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("VerifiedByteCarrier instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("VerifiedByteCarrier instances cannot be serialized")


_VerifiedAuthorityState = tuple[
    str,
    int,
    int,
    AuthoritativeByteCarrier,
    AuthoritativeByteCarrier,
    _CarrierSnapshot,
    _CarrierSnapshot,
]


@dataclass(frozen=True)
class _ReadObservation:
    path: str
    data: bytes
    sha256: str
    before: FileMetadata
    after: FileMetadata


class TrustedDirectory:
    """Own a duplicate of an already-trusted directory descriptor."""

    __slots__ = ("_fd", "_identity", "_label", "_lifecycle_lock", "__weakref__")
    _fd: int
    _identity: DirectoryIdentity
    _label: str
    _lifecycle_lock: LockType

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("TrustedDirectory instances must be retained from a descriptor")

    @classmethod
    def from_fd(cls, fd: int, *, label: str) -> TrustedDirectory:
        """Duplicate and retain one exact open directory descriptor."""
        if cls is not TrustedDirectory:
            raise TypeError("TrustedDirectory subclasses cannot issue capabilities")
        _require_platform()
        if type(fd) is not int:
            raise ByteCarrierError(
                label, "directory descriptor must be an exact integer"
            )
        _require_label(label)
        duplicate = _duplicate_fd(fd, label)
        instance: TrustedDirectory | None = None
        try:
            identity = _directory_identity(duplicate, label)
            instance = object.__new__(TrustedDirectory)
            instance._fd = duplicate
            instance._identity = identity
            instance._label = label
            instance._lifecycle_lock = Lock()
            _TRUSTED_AUTHORITIES.issue(instance, _trusted_state(instance))
            return instance
        except BaseException:
            if instance is not None:
                _TRUSTED_AUTHORITIES.retire(instance)
                instance._fd = -1
            try:
                os.close(duplicate)
            except OSError as exc:
                raise ByteCarrierError(label, str(exc)) from exc
            raise

    @property
    def identity(self) -> DirectoryIdentity:
        """Return the retained directory identity."""
        return self._identity

    @property
    def label(self) -> str:
        """Return the diagnostic label of the trusted directory."""
        return self._label

    def retain_directory(self, path: str) -> RetainedDirectory:
        """Open and retain one normalized child directory without following links."""
        components = _path_components(path, allow_dot=True)
        parent_duplicate = _borrow_trusted_descriptor(self)
        root_fd = -1
        retained: RetainedDirectory | None = None
        try:
            root_fd = _open_directory_at(parent_duplicate, components, path)
            identity = _directory_identity(root_fd, path)
            retained = object.__new__(RetainedDirectory)
            retained._parent_fd = parent_duplicate
            retained._root_fd = root_fd
            retained._identity = identity
            retained._path = path
            retained._lifecycle_lock = Lock()
            _RETAINED_AUTHORITIES.issue(
                retained,
                _retained_state(retained),
            )
            return retained
        except BaseException:
            if retained is not None:
                _RETAINED_AUTHORITIES.retire(retained)
                retained._root_fd = -1
                retained._parent_fd = -1
            first_error: BaseException | None = None
            if root_fd >= 0:
                try:
                    os.close(root_fd)
                except BaseException as exc:
                    first_error = exc
            if parent_duplicate >= 0:
                try:
                    os.close(parent_duplicate)
                except BaseException as exc:
                    if first_error is None:
                        first_error = exc
            if isinstance(first_error, OSError):
                raise ByteCarrierError(path, str(first_error)) from first_error
            if first_error is not None:
                raise first_error
            raise

    def close(self) -> None:
        """Release the retained descriptor; repeated calls are harmless."""
        _release_trusted_directory(self, strict=True)

    def _require_open(self) -> int:
        descriptor = _borrow_trusted_descriptor(self)
        try:
            os.close(descriptor)
        except OSError as exc:
            raise ByteCarrierError(self.label, str(exc)) from exc
        return self._fd

    def __enter__(self) -> TrustedDirectory:
        self._require_open()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def __copy__(self) -> NoReturn:
        raise TypeError("TrustedDirectory instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("TrustedDirectory instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("TrustedDirectory instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("TrustedDirectory instances cannot be serialized")

    def __del__(self) -> None:
        try:
            _release_trusted_directory(self, strict=False)
        except Exception:
            pass


class RetainedDirectory:
    """Retain a source root and the parent capability used to revalidate it."""

    __slots__ = (
        "_parent_fd",
        "_root_fd",
        "_identity",
        "_path",
        "_lifecycle_lock",
        "__weakref__",
    )
    _parent_fd: int
    _root_fd: int
    _identity: DirectoryIdentity
    _path: str
    _lifecycle_lock: LockType

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("RetainedDirectory instances must be opened from a capability")

    @property
    def identity(self) -> DirectoryIdentity:
        """Return the retained source-root identity."""
        return self._identity

    @property
    def path(self) -> str:
        """Return the normalized source-root path."""
        return self._path

    def read_authoritative(self, path: str) -> AuthoritativeByteCarrier:
        """Read one regular file once through the retained source root."""
        root_path, root_identity = _issued_retained_context(self)
        root = _borrow_retained_descriptor(self, parent=False)
        try:
            observation = _read_file_at(root, path)
        finally:
            try:
                os.close(root)
            except OSError as exc:
                raise ByteCarrierError(root_path, str(exc)) from exc
        return _issue_byte_carrier(
            observation,
            role="authoritative",
            root_path=root_path,
            root_identity=root_identity,
        )

    def verify(self, carrier: AuthoritativeByteCarrier) -> VerifiedByteCarrier:
        """Revalidate the root, reopen the logical path, and compare observations."""
        root_path, root_identity = _issued_retained_context(self)
        authoritative_snapshot = _require_authoritative_carrier(
            carrier,
            root_path=root_path,
            root_identity=root_identity,
        )
        authoritative_path = authoritative_snapshot[0]
        parent = _borrow_retained_descriptor(self, parent=True)
        components = _path_components(root_path, allow_dot=True)
        try:
            verification_root = _open_directory_at(parent, components, root_path)
            try:
                identity = _directory_identity(verification_root, root_path)
                if identity != root_identity:
                    raise ByteCarrierError(
                        root_path, "source root identity changed before verification"
                    )
                observation = _read_file_at(verification_root, authoritative_path)
            finally:
                try:
                    os.close(verification_root)
                except OSError as exc:
                    raise ByteCarrierError(root_path, str(exc)) from exc
            final_root = _open_directory_at(parent, components, root_path)
            try:
                final_identity = _directory_identity(final_root, root_path)
            finally:
                try:
                    os.close(final_root)
                except OSError as exc:
                    raise ByteCarrierError(root_path, str(exc)) from exc
        finally:
            try:
                os.close(parent)
            except OSError as exc:
                raise ByteCarrierError(root_path, str(exc)) from exc
        if final_identity != root_identity:
            raise ByteCarrierError(
                root_path, "source root identity changed during verification"
            )
        if observation.data != authoritative_snapshot[1]:
            raise ByteCarrierError(authoritative_path, "verification bytes differ")
        if _metadata_snapshot(observation.before) != authoritative_snapshot[3]:
            raise ByteCarrierError(authoritative_path, "verification metadata differ")
        verification_snapshot = _observation_snapshot(observation)
        verification = _issue_byte_carrier(
            observation,
            role="verification",
            root_path=root_path,
            root_identity=root_identity,
        )
        return _issue_verified_carrier(
            carrier,
            authoritative_snapshot,
            verification,
            verification_snapshot,
            root_path,
            root_identity,
        )

    def close(self) -> None:
        """Release the source-root and parent descriptors."""
        _release_retained_directory(self, strict=True)

    def _require_root(self) -> int:
        descriptor = _borrow_retained_descriptor(self, parent=False)
        try:
            os.close(descriptor)
        except OSError as exc:
            raise ByteCarrierError(self.path, str(exc)) from exc
        return self._root_fd

    def __enter__(self) -> RetainedDirectory:
        self._require_root()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def __copy__(self) -> NoReturn:
        raise TypeError("RetainedDirectory instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("RetainedDirectory instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("RetainedDirectory instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("RetainedDirectory instances cannot be serialized")

    def __del__(self) -> None:
        try:
            _release_retained_directory(self, strict=False)
        except Exception:
            pass


_TRUSTED_AUTHORITIES: IdentityAuthorityStore[TrustedDirectory] = (
    IdentityAuthorityStore()
)
_RETAINED_AUTHORITIES: IdentityAuthorityStore[RetainedDirectory] = (
    IdentityAuthorityStore()
)
_BYTE_AUTHORITIES: IdentityAuthorityStore[AuthoritativeByteCarrier] = (
    IdentityAuthorityStore()
)
_VERIFIED_AUTHORITIES: IdentityAuthorityStore[VerifiedByteCarrier] = (
    IdentityAuthorityStore()
)


def _trusted_state(value: TrustedDirectory) -> tuple[object, ...]:
    identity = value._identity
    return (
        value._lifecycle_lock,
        type(value._fd),
        value._fd,
        type(value._label),
        value._label,
        type(identity),
        id(identity),
        type(identity.device),
        identity.device,
        type(identity.inode),
        identity.inode,
    )


def _retained_state(value: RetainedDirectory) -> tuple[object, ...]:
    identity = value._identity
    return (
        value._lifecycle_lock,
        type(value._parent_fd),
        value._parent_fd,
        type(value._root_fd),
        value._root_fd,
        type(value._path),
        value._path,
        type(identity),
        id(identity),
        type(identity.device),
        identity.device,
        type(identity.inode),
        identity.inode,
    )


def _borrow_trusted_descriptor(value: TrustedDirectory) -> int:
    authority = _TRUSTED_AUTHORITIES.lookup(value)
    if authority is None:
        label = getattr(value, "_label", "<directory>")
        raise ByteCarrierError(label, "directory capability is closed")
    state = authority[1]
    lock = cast(LockType, state[0])
    label = cast(str, state[4])
    with lock:
        current = _TRUSTED_AUTHORITIES.lookup(value)
        if current is None:
            raise ByteCarrierError(label, "directory capability is closed")
        if current[1] != _trusted_state(value):
            raise ByteCarrierError(label, "directory capability state changed")
        return _duplicate_fd(cast(int, state[2]), label)


def _borrow_retained_descriptor(value: RetainedDirectory, *, parent: bool) -> int:
    authority = _RETAINED_AUTHORITIES.lookup(value)
    if authority is None:
        path = getattr(value, "_path", "<directory>")
        raise ByteCarrierError(path, "retained directory is closed")
    state = authority[1]
    lock = cast(LockType, state[0])
    path = cast(str, state[6])
    with lock:
        current = _RETAINED_AUTHORITIES.lookup(value)
        if current is None:
            raise ByteCarrierError(path, "retained directory is closed")
        if current[1] != _retained_state(value):
            raise ByteCarrierError(path, "retained directory state changed")
        descriptor = cast(int, state[2] if parent else state[4])
        return _duplicate_fd(descriptor, path)


def _issued_retained_context(
    value: RetainedDirectory,
) -> tuple[str, DirectoryIdentity]:
    state = _RETAINED_AUTHORITIES.state(value)
    if state is None:
        path = getattr(value, "_path", "<directory>")
        raise ByteCarrierError(path, "retained directory is closed")
    path = cast(str, state[6])
    identity = DirectoryIdentity(cast(int, state[10]), cast(int, state[12]))
    return path, identity


def _release_trusted_directory(value: TrustedDirectory, *, strict: bool) -> None:
    state = _TRUSTED_AUTHORITIES.state(value)
    current = getattr(value, "_fd", -1)
    if state is None:
        value._fd = -1
        if strict and current >= 0:
            raise ByteCarrierError("<unknown>", "directory capability was not issued")
        return
    lock = cast(LockType, state[0])
    descriptor = cast(int, state[2])
    label = cast(str, state[4])
    with lock:
        retired = _TRUSTED_AUTHORITIES.retire(value)
        value._fd = -1
    if retired is None:
        return
    try:
        os.close(descriptor)
    except OSError as exc:
        raise ByteCarrierError(label, str(exc)) from exc


def _release_retained_directory(value: RetainedDirectory, *, strict: bool) -> None:
    state = _RETAINED_AUTHORITIES.state(value)
    current_root = getattr(value, "_root_fd", -1)
    current_parent = getattr(value, "_parent_fd", -1)
    if state is None:
        value._root_fd = -1
        value._parent_fd = -1
        if strict and (current_root >= 0 or current_parent >= 0):
            raise ByteCarrierError("<unknown>", "retained directory was not issued")
        return
    lock = cast(LockType, state[0])
    parent = cast(int, state[2])
    root = cast(int, state[4])
    path = cast(str, state[6])
    with lock:
        retired = _RETAINED_AUTHORITIES.retire(value)
        value._root_fd = -1
        value._parent_fd = -1
    if retired is None:
        return
    first_error: BaseException | None = None
    try:
        os.close(root)
    except BaseException as exc:
        first_error = exc
    try:
        os.close(parent)
    except BaseException as exc:
        if first_error is None:
            first_error = exc
    if isinstance(first_error, OSError):
        raise ByteCarrierError(path, str(first_error)) from first_error
    if first_error is not None:
        raise first_error


def _metadata_snapshot(value: FileMetadata) -> _MetadataSnapshot:
    return (
        value.device,
        value.inode,
        value.mode,
        value.size,
        value.modified_ns,
        value.changed_ns,
    )


def _metadata_from_snapshot(value: _MetadataSnapshot) -> FileMetadata:
    return FileMetadata(*value)


def _observation_snapshot(observation: _ReadObservation) -> _CarrierSnapshot:
    return (
        observation.path,
        observation.data,
        observation.sha256,
        _metadata_snapshot(observation.before),
        _metadata_snapshot(observation.after),
    )


def _issue_byte_carrier(
    observation: _ReadObservation,
    *,
    role: str,
    root_path: str,
    root_identity: DirectoryIdentity,
) -> AuthoritativeByteCarrier:
    carrier = object.__new__(AuthoritativeByteCarrier)
    state = (
        role,
        root_path,
        root_identity.device,
        root_identity.inode,
        _observation_snapshot(observation),
    )
    _BYTE_AUTHORITIES.issue(carrier, state)
    return carrier


def _issued_carrier_snapshot(value: AuthoritativeByteCarrier) -> _CarrierSnapshot:
    state = _BYTE_AUTHORITIES.state(value)
    if state is None:
        raise ByteCarrierError("<carrier>", "byte carrier is not issued here")
    return cast(_CarrierSnapshot, state[4])


def _require_authoritative_carrier(
    carrier: object,
    *,
    root_path: str,
    root_identity: DirectoryIdentity,
) -> _CarrierSnapshot:
    if type(carrier) is not AuthoritativeByteCarrier:
        raise ByteCarrierError(root_path, "carrier has the wrong exact type")
    typed = carrier
    authority = _BYTE_AUTHORITIES.lookup(typed)
    expected_prefix = (
        "authoritative",
        root_path,
        root_identity.device,
        root_identity.inode,
    )
    if authority is None or authority[1][:-1] != expected_prefix:
        raise ByteCarrierError(root_path, "authoritative carrier is not issued here")
    snapshot = cast(_CarrierSnapshot, authority[1][4])
    expected_digest = "sha256:" + hashlib.sha256(snapshot[1]).hexdigest()
    if snapshot[2] != expected_digest or snapshot[3] != snapshot[4]:
        raise ByteCarrierError(snapshot[0], "authoritative carrier state is invalid")
    return snapshot


def _issue_verified_carrier(
    authoritative: AuthoritativeByteCarrier,
    authoritative_snapshot: _CarrierSnapshot,
    verification: AuthoritativeByteCarrier,
    verification_snapshot: _CarrierSnapshot,
    root_path: str,
    root_identity: DirectoryIdentity,
) -> VerifiedByteCarrier:
    carrier = object.__new__(VerifiedByteCarrier)
    _VERIFIED_AUTHORITIES.issue(
        carrier,
        (
            root_path,
            root_identity.device,
            root_identity.inode,
            authoritative,
            verification,
            authoritative_snapshot,
            verification_snapshot,
        ),
    )
    return carrier


def _issued_verified_state(value: VerifiedByteCarrier) -> _VerifiedAuthorityState:
    state = _VERIFIED_AUTHORITIES.state(value)
    if state is None:
        raise ByteCarrierError("<carrier>", "verified carrier is not issued here")
    return cast(_VerifiedAuthorityState, state)


def _read_file_at(root_fd: int, path: str) -> _ReadObservation:
    components = _path_components(path, allow_dot=False)
    descriptor = _open_file_at(root_fd, components, path)
    try:
        before = _file_metadata(descriptor, path)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, _READ_SIZE)
            if not chunk:
                break
            chunks.append(chunk)
        data = b"".join(chunks)
        after = _file_metadata(descriptor, path)
    except Exception as exc:
        raise ByteCarrierError(path, str(exc)) from exc
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            raise ByteCarrierError(path, str(exc)) from exc
    if before != after:
        raise ByteCarrierError(path, "file metadata changed during reading")
    if len(data) != before.size:
        raise ByteCarrierError(path, "read byte count differs from retained size")
    return _ReadObservation(
        path=path,
        data=data,
        sha256="sha256:" + hashlib.sha256(data).hexdigest(),
        before=before,
        after=after,
    )


def _open_directory_at(root_fd: int, components: tuple[str, ...], path: str) -> int:
    directory_flags, _file_flags = _descriptor_flags()
    current = _duplicate_fd(root_fd, path)
    try:
        for component in components:
            next_fd = os.open(component, directory_flags, dir_fd=current)
            previous = current
            current = next_fd
            try:
                os.close(previous)
            except OSError as exc:
                raise ByteCarrierError(path, str(exc)) from exc
        result = current
        current = -1
        return result
    except Exception as exc:
        raise ByteCarrierError(path, str(exc)) from exc
    finally:
        if current >= 0:
            try:
                os.close(current)
            except OSError as exc:
                raise ByteCarrierError(path, str(exc)) from exc


def _open_file_at(root_fd: int, components: tuple[str, ...], path: str) -> int:
    directory_flags, file_flags = _descriptor_flags()
    current = _duplicate_fd(root_fd, path)
    try:
        for component in components[:-1]:
            next_fd = os.open(component, directory_flags, dir_fd=current)
            previous = current
            current = next_fd
            try:
                os.close(previous)
            except OSError as exc:
                raise ByteCarrierError(path, str(exc)) from exc
        result = os.open(components[-1], file_flags, dir_fd=current)
        previous = current
        current = result
        try:
            os.close(previous)
        except OSError as exc:
            raise ByteCarrierError(path, str(exc)) from exc
        current = -1
        return result
    except OSError as exc:
        raise ByteCarrierError(path, str(exc)) from exc
    finally:
        if current >= 0:
            try:
                os.close(current)
            except OSError as exc:
                raise ByteCarrierError(path, str(exc)) from exc


def _directory_identity(fd: int, path: str) -> DirectoryIdentity:
    try:
        observed = os.fstat(fd)
    except OSError as exc:
        raise ByteCarrierError(path, str(exc)) from exc
    if not stat.S_ISDIR(observed.st_mode):
        raise ByteCarrierError(path, "descriptor does not name a directory")
    return DirectoryIdentity(observed.st_dev, observed.st_ino)


def _file_metadata(fd: int, path: str) -> FileMetadata:
    try:
        observed = os.fstat(fd)
    except OSError as exc:
        raise ByteCarrierError(path, str(exc)) from exc
    if not stat.S_ISREG(observed.st_mode):
        raise ByteCarrierError(path, "path does not name a regular file")
    return FileMetadata(
        device=observed.st_dev,
        inode=observed.st_ino,
        mode=observed.st_mode,
        size=observed.st_size,
        modified_ns=observed.st_mtime_ns,
        changed_ns=observed.st_ctime_ns,
    )


def _duplicate_fd(fd: int, path: str) -> int:
    try:
        duplicate = os.dup(fd)
    except OSError as exc:
        raise ByteCarrierError(path, str(exc)) from exc
    configured = False
    try:
        os.set_inheritable(duplicate, False)
        configured = True
        return duplicate
    except Exception as exc:
        raise ByteCarrierError(path, str(exc)) from exc
    finally:
        if not configured:
            try:
                os.close(duplicate)
            except OSError as exc:
                raise ByteCarrierError(path, str(exc)) from exc


def _path_components(value: object, *, allow_dot: bool) -> tuple[str, ...]:
    try:
        return normalized_path_components(value, allow_dot=allow_dot)
    except AcquisitionPathError as exc:
        raise ByteCarrierError(str(value), str(exc)) from exc


def _require_label(label: object) -> None:
    if type(label) is not str or not label:
        raise ByteCarrierError(str(label), "label must be non-empty exact text")
    try:
        require_unicode_scalar_text(label)
    except CanonicalJsonError as exc:
        raise ByteCarrierError(label, str(exc)) from exc


def _require_platform() -> None:
    required = ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC", "O_NONBLOCK")
    missing = [name for name in required if not hasattr(os, name)]
    supports_dir_fd: set[object] = getattr(os, "supports_dir_fd", set())
    if missing or os.open not in supports_dir_fd:
        detail = ", ".join(missing) if missing else "openat"
        raise ByteCarrierError(
            "<platform>", f"unsupported descriptor platform: {detail}"
        )


def _descriptor_flags() -> tuple[int, int]:
    _require_platform()
    directory = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY")
        | getattr(os, "O_CLOEXEC")
        | getattr(os, "O_NOFOLLOW")
    )
    file = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC")
        | getattr(os, "O_NOFOLLOW")
        | getattr(os, "O_NONBLOCK")
    )
    return directory, file
