"""Persist draft release history and materialize exact consumer bytes."""

from __future__ import annotations

import fcntl
import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from unicodedata import normalize

from eutaxis.commands.synchronization import _atomic_rename_noreplace
from eutaxis.declarations.acquisition_paths import normalized_relative_path
from eutaxis.declarations.byte_carriers import _trusted_directory_from_workspace_path
from eutaxis.declarations.canonical_json import jcs_bytes, parse_canonical_json_bytes

from .approve_release_capsule import ExpectedActive
from .verify_release_capsule import (
    _digest,
    _load_record,
    _object,
    _open_bundle_blobs,
    _read,
    verify_capsule,
)

TargetBytes = dict[str, bytes | None]


@dataclass(frozen=True)
class Release:
    """Bundle bytes checked against the selected capsule."""

    address: str
    predecessor: str | None
    baseline: TargetBytes
    targets: TargetBytes
    blobs: tuple[bytes, ...]


@dataclass(frozen=True)
class Head:
    """Last committed position and its content-addressed record."""

    active: ExpectedActive = ExpectedActive(None, None)
    record_digest: str | None = None

    @property
    def next_number(self) -> int:
        """Return the next contiguous sequence number."""
        return 0 if self.active.record is None else self.active.record + 1


def read_release(bundle: Path, address: str) -> Release:
    """Verify one capsule and retain its exact artifacts and reachable history."""
    with _open_bundle_blobs(bundle) as blobs:
        verify_capsule(blobs, address)
        capsule = _load_record(blobs, address, "release")
        review = _load_record(blobs, capsule["review-packet"], "review")
        baseline = _object(_read(blobs, review["artifacts"]["baseline"]))
        before, after = (
            {
                name: None if digest is None else _read(blobs, digest)
                for name, digest in entries.items()
            }
            for entries in (baseline, capsule["managed-targets"])
        )
        blobs.verify()
        return Release(
            address,
            capsule["predecessor"],
            before,
            after,
            tuple(blobs.observed_bytes()),
        )


def digest_name(value: object) -> str:
    """Return the filename component of a SHA-256 address."""
    if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        raise ValueError(f"Invalid release store digest: {value!r}")
    return value.removeprefix("sha256:")


def read_file(path: Path) -> bytes | None:
    """Read a stable regular file, preserving the distinction from absence."""
    with _trusted_directory_from_workspace_path(str(path.parent)) as root:
        with root.retain_directory(".") as directory:
            observed = directory.read_optional_authoritative(path.name)
            if observed is None:
                return None
            directory.verify(observed)
            return observed.data


def sync_directory(directory: Path) -> None:
    """Make directory entries durable."""
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def stage_file(path: Path, content: bytes) -> Iterator[Path]:
    """Write exact private bytes and flush the inode before publication."""
    with NamedTemporaryFile(dir=path.parent, prefix=".stage-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            yield temporary
        finally:
            temporary.unlink(missing_ok=True)


def publish(path: Path, content: bytes) -> None:
    """Link an absent record, verify its bytes and flush its parent."""
    with stage_file(path, content) as temporary:
        os.link(temporary, path, follow_symlinks=False)
        if read_file(path) != content:
            raise ValueError(f"Published bytes differ at {path}")
        sync_directory(path.parent)


def publish_once(path: Path, content: bytes) -> None:
    """Reuse an inert content-addressed file only if its bytes match."""
    existing = read_file(path)
    if existing is None:
        publish(path, content)
    elif existing != content:
        raise ValueError(f"Stored bytes differ at {path}")
    else:
        sync_directory(path.parent)


@contextmanager
def locked_store(root: Path, targets: Path) -> Iterator[bytes]:
    """Serialize writers and bind the store to one existing target root."""
    store_syntax = Path(normalize("NFD", str(root)).casefold())
    target_syntax = Path(normalize("NFD", str(targets)).casefold())
    if (
        store_syntax == target_syntax
        or store_syntax in target_syntax.parents
        or target_syntax in store_syntax.parents
    ):
        raise ValueError("Release store and target root must be disjoint directories")
    with _trusted_directory_from_workspace_path(str(root)) as store:
        with _trusted_directory_from_workspace_path(str(targets)) as target:
            if store.identity == target.identity:
                raise ValueError("Release store and target root have the same identity")
            fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                info = os.fstat(fd)
                if (info.st_dev, info.st_ino) != (
                    store.identity.device,
                    store.identity.inode,
                ):
                    raise ValueError("Release store changed while acquiring the lock")
                fcntl.flock(fd, fcntl.LOCK_EX)
                binding = jcs_bytes(
                    {
                        "path": str(targets),
                        "device": str(target.identity.device),
                        "inode": str(target.identity.inode),
                    }
                )
                existing = read_file(root / "target-root")
                if existing is not None and existing != binding:
                    raise ValueError("Release store belongs to a different target root")
                if existing is None and (
                    sequence_paths(root, "commit") or sequence_paths(root, "pending")
                ):
                    raise ValueError("Release store history has no target-root binding")
                yield binding
            finally:
                os.close(fd)


def sequence_paths(root: Path, prefix: str) -> dict[int, Path]:
    """Find sequence entries, failing closed on malformed names."""
    entries = {}
    for path in root.glob(f"{prefix}-*"):
        suffix = path.name.removeprefix(f"{prefix}-")
        if not re.fullmatch(r"0|[1-9][0-9]*", suffix):
            raise ValueError(f"Invalid {prefix} sequence name: {path.name}")
        entries[int(suffix)] = path
    return entries


def marker_digest(path: Path) -> str:
    """Read a canonical digest from a sequence marker."""
    content = read_file(path)
    if content is None:
        raise ValueError(f"Missing sequence marker: {path}")
    digest = parse_canonical_json_bytes(content)
    digest_name(digest)
    assert isinstance(digest, str)
    return digest


def record_path(root: Path, prefix: str, digest: str) -> Path:
    """Locate a record by its validated content address."""
    return root / f"{prefix}-{digest_name(digest)}"


def read_record(root: Path, prefix: str, digest: str) -> dict[str, object]:
    """Verify and parse a canonical content-addressed record."""
    data = read_file(record_path(root, prefix, digest))
    if data is None or _digest(data) != digest:
        raise ValueError(f"Missing or changed {prefix} record: {digest}")
    return _object(data)


def activation_record(head: Head, selected: str) -> dict[str, object]:
    """Bind a forward transition to its exact position in history."""
    return {
        "_schema": "eutaxis:declaration-activation@1",
        "number": head.next_number,
        "predecessor-record": head.record_digest,
        "expected-active": head.active.release,
        "selected-release": selected,
    }


def read_head(root: Path) -> Head:
    """Verify the contiguous chain and each capsule it selects."""
    head = Head()
    for number, path in sorted(sequence_paths(root, "commit").items()):
        if number != head.next_number:
            raise ValueError(f"Gap in activation history at record {head.next_number}")
        digest = marker_digest(path)
        record = read_record(root, "record", digest)
        address = record.get("selected-release")
        if not isinstance(address, str) or jcs_bytes(record) != jcs_bytes(
            activation_record(head, address)
        ):
            raise ValueError(f"Invalid activation record at sequence {number}")
        release = read_release(record_path(root, "release", address), address)
        if release.predecessor != head.active.release:
            raise ValueError(f"Capsule predecessor mismatch at record {number}")
        head = Head(ExpectedActive(number, address), digest)
    return head


def retain_release(root: Path, release: Release) -> None:
    """Publish a durable bundle directory at the capsule address."""
    destination = record_path(root, "release", release.address)
    if not destination.exists() and not destination.is_symlink():
        with TemporaryDirectory(prefix=".bundle-", dir=root) as temporary:
            staged = Path(temporary) / "release"
            blobs = staged / "blobs" / "sha256"
            blobs.mkdir(parents=True)
            for data in release.blobs:
                path = blobs / digest_name(_digest(data))
                with path.open("xb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
            for directory in (blobs, blobs.parent, staged):
                sync_directory(directory)
            _atomic_rename_noreplace(staged, destination)
    read_release(destination, release.address)
    sync_directory(root)


def validate_targets(names: set[str]) -> None:
    """Reject aliased paths and file-to-directory transitions in one plan."""
    seen = set()
    for name in sorted(names):
        path = normalized_relative_path(name, allow_dot=False)
        key = normalize("NFD", path).casefold()
        if key in seen:
            raise ValueError(f"Aliased consumer target: {path}")
        seen.add(key)
    for key in seen:
        if any(parent.as_posix() in seen for parent in Path(key).parents):
            raise ValueError(
                f"Consumer target also serves as a parent directory: {key}"
            )


def target_path(root: Path, name: str, *, create: bool = False) -> Path | None:
    """Walk parent directories without following symlinks."""
    path = root
    parts = normalized_relative_path(name, allow_dot=False).split("/")
    for part in parts[:-1]:
        child = path / part
        try:
            info = child.lstat()
        except FileNotFoundError:
            if not create:
                return None
            child.mkdir(mode=0o700)
            sync_directory(path)
        else:
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError(f"Invalid consumer target parent: {child}")
        path = child
    return path / parts[-1]


def consumer_bytes(root: Path, name: str) -> bytes | None:
    """Read the present target bytes or return explicit absence."""
    path = target_path(root, name)
    return None if path is None else read_file(path)


def update_target(
    root: Path, name: str, expected: bytes | None, selected: bytes | None
) -> None:
    """Replace or retire a target only from the expected byte state."""
    if consumer_bytes(root, name) != expected:
        raise ValueError(f"Concurrent or unexpected consumer state: {name}")
    if expected == selected:
        return
    path = target_path(root, name, create=selected is not None)
    assert path is not None
    if selected is None:
        path.unlink()
    else:
        with stage_file(path, selected) as temporary:
            if expected is None:
                os.link(temporary, path, follow_symlinks=False)
            else:
                os.replace(temporary, path)
    if consumer_bytes(root, name) != selected:
        raise ValueError(f"Written consumer bytes differ: {name}")
    sync_directory(path.parent)


def sync_target(root: Path, name: str) -> None:
    """Flush a verified target state before retiring an interrupted intent."""
    path = target_path(root, name)
    if path is None:
        return
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        pass
    else:
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    sync_directory(path.parent)
