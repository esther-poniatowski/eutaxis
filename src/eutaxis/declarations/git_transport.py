"""Authenticate one closed local Git-submodule transport without publishing it."""

from __future__ import annotations

import os
import resource
import stat
import tempfile
import time
from dataclasses import dataclass
from threading import Lock
from types import TracebackType
from typing import NamedTuple, NoReturn, SupportsIndex, cast

from ._authority import IdentityAuthorityStore, identity_value_state
from ._git_formats import (
    GitConfigEntry,
    GitRepositoryConfig,
    GitTreeEntry,
    ParsedGitIndex,
    gitmodules_registrations,
    parse_git_config_output,
    parse_git_index,
    parse_git_reference,
    parse_ls_tree_record,
    parse_packed_refs,
    regular_blob_modes,
    require_index_entry,
    resolve_git_pointer,
    validate_git_repository_config,
)
from .acquisition_contract import (
    AcquisitionKind,
    AcquisitionLock,
    AcquisitionManifest,
    ExternalSourceLock,
    ExternalSourceManifest,
    FacetConstituentLock,
    FacetExtensionManifest,
    GitLock,
    LockedFile,
    validate_acquisition_contract,
)
from .acquisition_paths import AcquisitionPathError, normalized_relative_path
from .byte_carriers import (
    AuthoritativeByteCarrier,
    DirectoryIdentity,
    RetainedDirectory,
    TrustedDirectory,
    VerifiedByteCarrier,
    _authoritative_carrier_context,
    _borrow_retained_descriptor,
    _borrow_trusted_descriptor,
    _issued_retained_context,
)
from .exceptions import AcquisitionContractError, ByteCarrierError

_GIT_CANDIDATES = ("/usr/bin/git",)
_GIT_TIMEOUT_SECONDS = 10.0
_MAX_INPUT_BYTES = 8 * 1024 * 1024
_MAX_OUTPUT_BYTES = 8 * 1024 * 1024
_MAX_OBJECT_STORE_ENTRIES = 100_000


class _ExecutableIdentity(NamedTuple):
    device: int
    inode: int
    mode: int
    size: int
    modified_ns: int
    changed_ns: int


class _GitExecutable(NamedTuple):
    path: str
    identity: _ExecutableIdentity


class _MetadataCarrier(NamedTuple):
    root: str
    path: str
    carrier: AuthoritativeByteCarrier


class _AbsentMetadata(NamedTuple):
    root: str
    path: str


class _CommittedBlob(NamedTuple):
    path: str
    entry: GitTreeEntry
    data: bytes


class _ObjectStoreEntry(NamedTuple):
    path: str
    kind: str
    device: int
    inode: int
    mode: int
    size: int
    modified_ns: int
    changed_ns: int


class _GitObservation(NamedTuple):
    parent_config: GitRepositoryConfig
    nested_config: GitRepositoryConfig
    parent_config_entries: tuple[GitConfigEntry, ...]
    nested_config_entries: tuple[GitConfigEntry, ...]
    parent_index: ParsedGitIndex
    parent_objects: tuple[_ObjectStoreEntry, ...]
    nested_objects: tuple[_ObjectStoreEntry, ...]
    packed_refs: tuple[tuple[str, str], ...] | None
    head_commit: str
    parent_gitlink: str
    indexed_gitmodules: bytes
    commit_type: bytes
    blobs: tuple[_CommittedBlob, ...]


class _GitLockSnapshot(NamedTuple):
    object_format: str
    commit: str
    gitmodules_path: str
    gitmodules_sha256: str
    registered_name: str
    registered_path: str
    parent_index_mode: str
    parent_index_gitlink: str


class _OwnedExtension(NamedTuple):
    position: int
    manifest: FacetExtensionManifest
    lock: FacetConstituentLock


class _SessionState(NamedTuple):
    lock: Lock
    phase: str
    acquisition_manifest: AcquisitionManifest
    acquisition_lock: AcquisitionLock
    source_position: int
    source_manifest: ExternalSourceManifest
    source_lock: ExternalSourceLock
    extensions: tuple[_OwnedExtension, ...]
    contract_state: object
    git_lock: GitLock
    git_lock_state: object
    git: _GitLockSnapshot
    expected_files: tuple[tuple[str, str], ...]
    executable: _GitExecutable
    workspace_capability: TrustedDirectory
    workspace: RetainedDirectory
    source: RetainedDirectory
    parent_git: RetainedDirectory
    nested_git: RetainedDirectory
    metadata: tuple[_MetadataCarrier, ...]
    absences: tuple[_AbsentMetadata, ...]
    observation: _GitObservation
    worktree_carriers: tuple[AuthoritativeByteCarrier, ...] | None


class _EvidenceState(NamedTuple):
    acquisition_manifest: AcquisitionManifest
    acquisition_lock: AcquisitionLock
    source_position: int
    source_manifest: ExternalSourceManifest
    source_lock: ExternalSourceLock
    extensions: tuple[_OwnedExtension, ...]
    contract_state: object
    git_lock: GitLock
    git_lock_state: object
    git: _GitLockSnapshot
    expected_files: tuple[tuple[str, str], ...]
    observation: _GitObservation
    metadata: tuple[VerifiedByteCarrier, ...]
    worktree: tuple[VerifiedByteCarrier, ...]


@dataclass(frozen=True)
class _InitialRead:
    metadata: tuple[_MetadataCarrier, ...]
    absences: tuple[_AbsentMetadata, ...]
    observation: _GitObservation


class _GitSubmoduleSession:
    """Hold a private Git proof open across declaration parsing."""

    __slots__ = ("_lock", "__weakref__")
    _lock: Lock

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("Git submodule sessions must be issued by the transport")

    def bind_worktree_carriers(
        self, carriers: tuple[AuthoritativeByteCarrier, ...]
    ) -> None:
        """Bind ordered descriptor reads to the locked commit blobs."""
        state = _session_state(self)
        with state.lock:
            state = _session_state(self)
            if state.phase != "open" or state.worktree_carriers is not None:
                _fail("$.git", "Git session cannot accept worktree carriers")
            if type(carriers) is not tuple or len(carriers) != len(
                state.expected_files
            ):
                _fail("$.git.files", "worktree carrier sequence differs")
            root_path, root_identity = _issued_retained_context(state.source)
            blobs = state.observation.blobs
            for index, (carrier, expected, blob) in enumerate(
                zip(carriers, state.expected_files, blobs, strict=True)
            ):
                carrier_root, carrier_identity, snapshot = (
                    _authoritative_carrier_context(carrier)
                )
                if carrier_root != root_path or carrier_identity != root_identity:
                    _fail(
                        f"$.git.files[{index}]",
                        "worktree carrier belongs to another source root",
                    )
                path, digest = expected
                if snapshot[0] != path or snapshot[2] != digest:
                    _fail(
                        f"$.git.files[{index}]",
                        "worktree carrier differs from the locked file",
                    )
                if blob.path != path or blob.data != snapshot[1]:
                    _fail(
                        f"$.git.files[{index}]",
                        "worktree bytes differ from the locked commit blob",
                    )
            _SESSION_AUTHORITIES.issue(
                self,
                _SessionState(*state[:-1], carriers),
            )

    def finish(self) -> _GitTransportEvidence:
        """Repeat the proof, close every descriptor, and issue final evidence."""
        state = _session_state(self)
        with state.lock:
            state = _session_state(self)
            if state.phase != "open" or state.worktree_carriers is None:
                _fail("$.git", "Git session is not ready for verification")
            finishing = _SessionState(
                state.lock,
                "finishing",
                *state[2:],
            )
            _SESSION_AUTHORITIES.issue(self, finishing)
            try:
                evidence_state = _verify_session(finishing)
            except BaseException as primary:
                try:
                    _retire_and_close(self, finishing)
                except BaseException as cleanup:
                    raise primary from cleanup
                raise
            _SESSION_AUTHORITIES.retire(self)
            _close_roots(finishing)
            return _issue_git_evidence(evidence_state)

    def close(self) -> None:
        """Abort the session and release every retained descriptor."""
        state = _session_state(self)
        with state.lock:
            current = _SESSION_AUTHORITIES.retire(self)
            if current is None:
                return
            _close_roots(cast(_SessionState, current))

    def __enter__(self) -> _GitSubmoduleSession:
        _session_state(self)
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        if _SESSION_AUTHORITIES.state(self) is not None:
            self.close()

    def __copy__(self) -> NoReturn:
        raise TypeError("Git submodule sessions cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("Git submodule sessions cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("Git submodule sessions cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("Git submodule sessions cannot be serialized")

    def __del__(self) -> None:
        try:
            state = _SESSION_AUTHORITIES.retire(self)
            if state is not None:
                _close_roots(cast(_SessionState, state))
        except Exception:
            pass


class _GitTransportEvidence:
    """Retain verified Git proof without exposing it to semantic consumers."""

    __slots__ = ("__weakref__",)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("Git transport evidence must be issued by a closed session")

    def __copy__(self) -> NoReturn:
        raise TypeError("Git transport evidence cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("Git transport evidence cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("Git transport evidence cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("Git transport evidence cannot be serialized")


_SESSION_AUTHORITIES: IdentityAuthorityStore[object] = IdentityAuthorityStore()
_EVIDENCE_AUTHORITIES: IdentityAuthorityStore[object] = IdentityAuthorityStore()


def _open_git_submodule_session(
    workspace: TrustedDirectory,
    manifest: AcquisitionManifest,
    acquisition_lock: AcquisitionLock,
    source_position: int,
) -> _GitSubmoduleSession:
    """Open and authoritatively observe one locked Git submodule."""
    validate_acquisition_contract(manifest, acquisition_lock)
    if (
        type(source_position) is not int
        or source_position < 0
        or source_position >= len(manifest.sources)
    ):
        _fail("$.source-position", "source position does not select a source")
    source_manifest = manifest.sources[source_position]
    source_lock = acquisition_lock.sources[source_position]
    extensions = tuple(
        (
            position,
            extension,
            acquisition_lock.facet_registry.extensions[position],
        )
        for position, extension in enumerate(manifest.facet_extensions)
        if extension.namespace == source_manifest.namespace
    )
    owned_extensions, expected_files = _validate_source_contract(
        source_position,
        source_manifest,
        source_lock,
        extensions,
    )
    git_lock = source_lock.git
    assert git_lock is not None
    git = _snapshot_git_lock(git_lock)
    files = _validate_expected_files(expected_files)
    if git.registered_path == ".git" or git.registered_path.startswith(".git/"):
        _fail("$.git.registered-path", "source root cannot be inside parent Git data")
    executable = _select_git_executable()
    roots: list[RetainedDirectory] = []
    try:
        workspace_root = workspace.retain_directory(".")
        roots.append(workspace_root)
        source = workspace.retain_directory(git.registered_path)
        roots.append(source)
        parent_git = workspace.retain_directory(".git")
        roots.append(parent_git)
        nested_path = f".git/modules/{git.registered_name}"
        nested_git = workspace.retain_directory(nested_path)
        roots.append(nested_git)
        initial = _initial_read(
            workspace,
            workspace_root,
            source,
            parent_git,
            nested_git,
            git,
            files,
            executable,
        )
        result = object.__new__(_GitSubmoduleSession)
        result._lock = Lock()
        state = _SessionState(
            result._lock,
            "open",
            manifest,
            acquisition_lock,
            source_position,
            source_manifest,
            source_lock,
            owned_extensions,
            _contract_state(
                manifest,
                acquisition_lock,
                source_position,
                source_manifest,
                source_lock,
                owned_extensions,
            ),
            git_lock,
            identity_value_state(git_lock),
            git,
            files,
            executable,
            workspace,
            workspace_root,
            source,
            parent_git,
            nested_git,
            initial.metadata,
            initial.absences,
            initial.observation,
            None,
        )
        _SESSION_AUTHORITIES.issue(result, state)
        return result
    except BaseException as primary:
        try:
            _close_partial_roots(roots)
        except BaseException as cleanup:
            raise primary from cleanup
        raise


def _initial_read(
    workspace_capability: TrustedDirectory,
    workspace: RetainedDirectory,
    source: RetainedDirectory,
    parent_git: RetainedDirectory,
    nested_git: RetainedDirectory,
    git: _GitLockSnapshot,
    files: tuple[tuple[str, str], ...],
    executable: _GitExecutable,
) -> _InitialRead:
    metadata: list[_MetadataCarrier] = []
    absences: list[_AbsentMetadata] = []
    _required(workspace, "workspace", git.gitmodules_path, metadata)
    _required(source, "source", ".git", metadata)
    _required(parent_git, "parent", "index", metadata)
    _required(parent_git, "parent", "config", metadata)
    _required(nested_git, "nested", "config", metadata)
    head = _required(nested_git, "nested", "HEAD", metadata)
    for root_name, root in (("parent", parent_git), ("nested", nested_git)):
        for path in (
            "commondir",
            "objects/info/alternates",
            "objects/info/grafts",
            "config.worktree",
        ):
            _absent(root, root_name, path, absences)
    _optional(nested_git, "nested", "packed-refs", metadata, absences)
    reference = parse_git_reference(
        head.data, object_format=git.object_format, location="$.git.HEAD"
    )
    if reference.kind == "symbolic":
        _optional(nested_git, "nested", reference.value, metadata, absences)
    observation = _observe(
        workspace_capability,
        parent_git,
        nested_git,
        tuple(metadata),
        git,
        files,
        executable,
    )
    return _InitialRead(tuple(metadata), tuple(absences), observation)


def _observe(
    workspace: TrustedDirectory,
    parent_git: RetainedDirectory,
    nested_git: RetainedDirectory,
    metadata: tuple[_MetadataCarrier, ...],
    git: _GitLockSnapshot,
    files: tuple[tuple[str, str], ...],
    executable: _GitExecutable,
) -> _GitObservation:
    values = {(item.root, item.path): item.carrier.data for item in metadata}
    parent_objects = _snapshot_object_store(parent_git, "$.git.parent-objects")
    nested_objects = _snapshot_object_store(nested_git, "$.git.nested-objects")
    parent_config_entries = _parse_config(
        workspace,
        executable,
        values[("parent", "config")],
        "$.git.parent-config",
    )
    nested_config_entries = _parse_config(
        workspace,
        executable,
        values[("nested", "config")],
        "$.git.nested-config",
    )
    parent_config = validate_git_repository_config(
        parent_config_entries,
        expected_worktree=None,
        git_directory=".git",
        location="$.git.parent-config",
    )
    nested_git_directory = f".git/modules/{git.registered_name}"
    nested_config = validate_git_repository_config(
        nested_config_entries,
        expected_worktree=git.registered_path,
        git_directory=nested_git_directory,
        location="$.git.nested-config",
    )
    if (
        parent_config.object_format != git.object_format
        or nested_config.object_format != git.object_format
    ):
        _fail("$.git.object-format", "repository object formats differ from the lock")

    gitmodules = values[("workspace", git.gitmodules_path)]
    if "sha256:" + _sha256(gitmodules) != git.gitmodules_sha256:
        _fail("$.git.gitmodules-sha256", "worktree `.gitmodules` digest differs")
    registrations = gitmodules_registrations(
        _parse_config(workspace, executable, gitmodules, "$.git.gitmodules"),
        location="$.git.gitmodules",
    )
    matching_name = tuple(
        item for item in registrations if item.name == git.registered_name
    )
    matching_path = tuple(
        item for item in registrations if item.path == git.registered_path
    )
    if (
        len(matching_name) != 1
        or matching_name[0].path != git.registered_path
        or matching_path != matching_name
    ):
        _fail("$.git.gitmodules", "submodule registration differs from the lock")
    resolve_git_pointer(
        values[("source", ".git")],
        source_root=git.registered_path,
        expected_target=nested_git_directory,
        location="$.git.pointer",
    )

    index = parse_git_index(
        values[("parent", "index")],
        object_format=git.object_format,
        location="$.git.parent-index",
    )
    gitmodules_entry = require_index_entry(
        index,
        path=git.gitmodules_path,
        admitted_modes=regular_blob_modes(),
        location="$.git.parent-index.gitmodules",
    )
    gitlink = require_index_entry(
        index,
        path=git.registered_path,
        admitted_modes=frozenset({0o160000}),
        location="$.git.parent-index.gitlink",
    )
    if gitlink.object_id != git.parent_index_gitlink:
        _fail("$.git.parent-index-gitlink", "parent index gitlink differs")
    packed_source = values.get(("nested", "packed-refs"))
    packed_refs = (
        None
        if packed_source is None
        else parse_packed_refs(
            packed_source,
            object_format=git.object_format,
            location="$.git.packed-refs",
        )
    )
    head_commit = _resolve_head(values, git.object_format, packed_refs)
    if head_commit != git.commit or head_commit != gitlink.object_id:
        _fail("$.git.commit", "nested HEAD, gitlink, and locked commit differ")

    parent_prefix = _repository_prefix(".git", ".")
    nested_prefix = _repository_prefix(nested_git_directory, git.registered_path)
    if (
        _run_git(
            workspace,
            executable,
            parent_prefix + ("cat-file", "-t", gitmodules_entry.object_id),
        )
        != b"blob\n"
    ):
        _fail("$.git.gitmodules", "indexed `.gitmodules` object is not a blob")
    indexed_gitmodules = _run_git(
        workspace,
        executable,
        parent_prefix + ("cat-file", "blob", gitmodules_entry.object_id),
    )
    if indexed_gitmodules != gitmodules:
        _fail("$.git.gitmodules", "worktree bytes differ from the indexed blob")
    commit_type = _run_git(
        workspace,
        executable,
        nested_prefix + ("cat-file", "-t", head_commit),
    )
    if commit_type != b"commit\n":
        _fail("$.git.commit", "locked nested object is not a commit")

    blobs: list[_CommittedBlob] = []
    for index_position, (path, _digest) in enumerate(files):
        entry = parse_ls_tree_record(
            _run_git(
                workspace,
                executable,
                nested_prefix + ("ls-tree", "-z", head_commit, "--", path),
            ),
            object_format=git.object_format,
            expected_path=path,
            location=f"$.git.files[{index_position}]",
        )
        if entry.object_type != "blob" or entry.mode not in regular_blob_modes():
            _fail(
                f"$.git.files[{index_position}]",
                "committed path must be a regular blob",
            )
        data = _run_git(
            workspace,
            executable,
            nested_prefix + ("cat-file", "blob", entry.object_id),
        )
        if "sha256:" + _sha256(data) != files[index_position][1]:
            _fail(f"$.git.files[{index_position}]", "committed blob digest differs")
        blobs.append(_CommittedBlob(path, entry, data))
    return _GitObservation(
        parent_config,
        nested_config,
        parent_config_entries,
        nested_config_entries,
        index,
        parent_objects,
        nested_objects,
        packed_refs,
        head_commit,
        gitlink.object_id,
        indexed_gitmodules,
        commit_type,
        tuple(blobs),
    )


def _verify_session(state: _SessionState) -> _EvidenceState:
    if (
        _contract_state(
            state.acquisition_manifest,
            state.acquisition_lock,
            state.source_position,
            state.source_manifest,
            state.source_lock,
            state.extensions,
        )
        != state.contract_state
    ):
        _fail("$.git", "source contract state changed during acquisition")
    if identity_value_state(state.git_lock) != state.git_lock_state:
        _fail("$.git", "Git lock state changed during acquisition")
    metadata_evidence: list[VerifiedByteCarrier] = []
    verification_metadata: list[_MetadataCarrier] = []
    roots = _root_mapping(state)
    for item in state.metadata:
        evidence = roots[item.root].verify(item.carrier)
        metadata_evidence.append(evidence)
        verification_metadata.append(
            _MetadataCarrier(item.root, item.path, evidence.verification)
        )
    for absence in state.absences:
        if roots[absence.root].read_optional_authoritative(absence.path) is not None:
            _fail(
                f"$.git.{absence.root}.{absence.path}",
                "previously absent metadata appeared",
            )
    repeated = _observe(
        state.workspace_capability,
        state.parent_git,
        state.nested_git,
        tuple(verification_metadata),
        state.git,
        state.expected_files,
        state.executable,
    )
    if repeated != state.observation:
        _fail("$.git", "repeated Git transport observation differs")
    assert state.worktree_carriers is not None
    worktree_evidence = tuple(
        state.source.verify(carrier) for carrier in state.worktree_carriers
    )
    return _EvidenceState(
        state.acquisition_manifest,
        state.acquisition_lock,
        state.source_position,
        state.source_manifest,
        state.source_lock,
        state.extensions,
        state.contract_state,
        state.git_lock,
        state.git_lock_state,
        state.git,
        state.expected_files,
        state.observation,
        tuple(metadata_evidence),
        worktree_evidence,
    )


def _resolve_head(
    values: dict[tuple[str, str], bytes],
    object_format: str,
    packed_refs: tuple[tuple[str, str], ...] | None,
) -> str:
    head = parse_git_reference(
        values[("nested", "HEAD")],
        object_format=object_format,
        location="$.git.HEAD",
    )
    if head.kind == "object":
        return head.value
    loose = values.get(("nested", head.value))
    if loose is not None:
        result = parse_git_reference(
            loose,
            object_format=object_format,
            location="$.git.loose-reference",
        )
        if result.kind != "object":
            _fail("$.git.loose-reference", "nested symbolic references are unsupported")
        return result.value
    if packed_refs is None:
        _fail("$.git.HEAD", "symbolic HEAD has no local reference carrier")
    matches = tuple(
        value for reference, value in packed_refs if reference == head.value
    )
    if len(matches) != 1:
        _fail("$.git.HEAD", "symbolic HEAD has no unique packed reference")
    return matches[0]


def _parse_config(
    workspace: TrustedDirectory,
    executable: _GitExecutable,
    source: bytes,
    location: str,
) -> tuple[GitConfigEntry, ...]:
    output = _run_git(
        workspace,
        executable,
        (
            "--no-optional-locks",
            "config",
            "--no-includes",
            "--null",
            "--file",
            "-",
            "--list",
        ),
        stdin=source,
    )
    return parse_git_config_output(output, location=location)


def _repository_prefix(git_directory: str, worktree: str) -> tuple[str, ...]:
    return (
        "--no-pager",
        "--literal-pathspecs",
        "--no-optional-locks",
        f"--git-dir={git_directory}",
        f"--work-tree={worktree}",
    )


def _snapshot_object_store(
    root: RetainedDirectory, location: str
) -> tuple[_ObjectStoreEntry, ...]:
    root_fd = _borrow_retained_descriptor(root, parent=False)
    objects_fd = -1
    flags = _directory_open_flags()
    try:
        objects_fd = os.open("objects", flags, dir_fd=root_fd)
    except OSError as exc:
        _fail(location, f"object directory cannot be retained: {exc}")
    finally:
        os.close(root_fd)
    entries: list[_ObjectStoreEntry] = []
    try:
        _walk_object_store(objects_fd, (), entries, location)
    finally:
        os.close(objects_fd)
    return tuple(entries)


def _walk_object_store(
    directory: int,
    prefix: tuple[str, ...],
    entries: list[_ObjectStoreEntry],
    location: str,
) -> None:
    flags = _directory_open_flags()
    before = os.fstat(directory)
    path = "/".join(prefix) if prefix else "."
    entries.append(_object_store_entry(path, "directory", before))
    if len(entries) > _MAX_OBJECT_STORE_ENTRIES:
        _fail(location, "object-store entry count exceeds the closed limit")
    try:
        names = sorted(os.listdir(directory))
    except OSError as exc:
        _fail(location, f"object directory cannot be listed: {exc}")
    for name in names:
        entry_path = "/".join((*prefix, name))
        try:
            details = os.stat(name, dir_fd=directory, follow_symlinks=False)
        except OSError as exc:
            _fail(location + "." + entry_path, str(exc))
        if stat.S_ISLNK(details.st_mode):
            _fail(location + "." + entry_path, "symbolic links are forbidden")
        if stat.S_ISREG(details.st_mode):
            entries.append(_object_store_entry(entry_path, "file", details))
            if len(entries) > _MAX_OBJECT_STORE_ENTRIES:
                _fail(location, "object-store entry count exceeds the closed limit")
            continue
        if not stat.S_ISDIR(details.st_mode):
            _fail(location + "." + entry_path, "object-store entry type is forbidden")
        child = -1
        try:
            child = os.open(name, flags, dir_fd=directory)
            opened = os.fstat(child)
            if (
                opened.st_dev != details.st_dev
                or opened.st_ino != details.st_ino
                or opened.st_mode != details.st_mode
            ):
                _fail(location + "." + entry_path, "directory identity changed")
            _walk_object_store(child, (*prefix, name), entries, location)
        except OSError as exc:
            _fail(location + "." + entry_path, str(exc))
        finally:
            if child >= 0:
                os.close(child)
    after = os.fstat(directory)
    if _object_store_entry(path, "directory", before) != _object_store_entry(
        path, "directory", after
    ):
        _fail(location + "." + path, "object directory changed during traversal")


def _object_store_entry(
    path: str, kind: str, details: os.stat_result
) -> _ObjectStoreEntry:
    return _ObjectStoreEntry(
        path,
        kind,
        details.st_dev,
        details.st_ino,
        details.st_mode,
        details.st_size,
        details.st_mtime_ns,
        details.st_ctime_ns,
    )


def _directory_open_flags() -> int:
    return os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW


def _run_git(
    workspace: TrustedDirectory,
    executable: _GitExecutable,
    arguments: tuple[str, ...],
    *,
    stdin: bytes = b"",
) -> bytes:
    if type(arguments) is not tuple or any(type(item) is not str for item in arguments):
        _fail("$.git.command", "Git arguments must be exact strings")
    if len(stdin) > _MAX_INPUT_BYTES:
        _fail("$.git.command", "Git input exceeds the closed size limit")
    _verify_git_executable(executable)
    environment = {
        "HOME": "/nonexistent",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_LITERAL_PATHSPECS": "1",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
    }
    with (
        tempfile.TemporaryFile() as input_file,
        tempfile.TemporaryFile() as output_file,
        tempfile.TemporaryFile() as error_file,
    ):
        input_file.write(stdin)
        input_file.seek(0)
        root_fd = _borrow_trusted_descriptor(workspace)
        process = -1
        try:
            descriptor_upper_bound = _descriptor_upper_bound()
            process = os.fork()
            if process == 0:
                try:
                    os.fchdir(root_fd)
                    os.dup2(input_file.fileno(), 0)
                    os.dup2(output_file.fileno(), 1)
                    os.dup2(error_file.fileno(), 2)
                    _close_child_descriptors(descriptor_upper_bound)
                    _soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
                    limit = (
                        min(_MAX_OUTPUT_BYTES, hard) if hard >= 0 else _MAX_OUTPUT_BYTES
                    )
                    resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))
                    os.execve(
                        executable.path,
                        (executable.path, *arguments),
                        environment,
                    )
                except BaseException as exc:
                    try:
                        os.write(
                            2,
                            (type(exc).__name__ + ": " + str(exc)).encode()[:4096],
                        )
                    finally:
                        os._exit(127)
            try:
                status = _wait_for_process(process)
            except BaseException:
                _kill_and_reap(process)
                raise
        finally:
            os.close(root_fd)
        output_file.seek(0)
        error_file.seek(0)
        output = output_file.read(_MAX_OUTPUT_BYTES + 1)
        error = error_file.read(_MAX_OUTPUT_BYTES + 1)
    if len(output) > _MAX_OUTPUT_BYTES or len(error) > _MAX_OUTPUT_BYTES:
        _fail("$.git.command", "Git output exceeds the closed size limit")
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        detail = error.decode("utf-8", errors="replace").strip()
        _fail("$.git.command", f"local Git query failed: {detail or 'no diagnostic'}")
    return output


def _wait_for_process(process: int) -> int:
    deadline = time.monotonic() + _GIT_TIMEOUT_SECONDS
    while True:
        result, status = os.waitpid(process, os.WNOHANG)
        if result == process:
            return status
        if time.monotonic() >= deadline:
            _kill_and_reap(process)
            _fail("$.git.command", "local Git query timed out")
        time.sleep(0.01)


def _kill_and_reap(process: int) -> None:
    if process <= 0:
        return
    try:
        os.kill(process, 9)
    except ProcessLookupError:
        pass
    while True:
        try:
            os.waitpid(process, 0)
            return
        except ChildProcessError:
            return
        except InterruptedError:
            continue


def _descriptor_upper_bound() -> int:
    try:
        descriptors = tuple(
            int(name) for name in os.listdir("/dev/fd") if name.isdecimal()
        )
    except OSError as exc:
        _fail("$.git.command", f"open descriptors cannot be enumerated: {exc}")
    return max(descriptors, default=2) + 1


def _close_child_descriptors(upper_bound: int) -> None:
    os.closerange(3, upper_bound)


def _select_git_executable() -> _GitExecutable:
    for path in _GIT_CANDIDATES:
        try:
            details = os.lstat(path)
        except FileNotFoundError:
            continue
        if stat.S_ISREG(details.st_mode) and details.st_mode & 0o111:
            return _GitExecutable(path, _executable_identity(details))
    _fail("$.git.executable", "no code-owned Git executable is available")


def _verify_git_executable(executable: _GitExecutable) -> None:
    try:
        details = os.lstat(executable.path)
    except OSError as exc:
        _fail("$.git.executable", str(exc))
    if _executable_identity(details) != executable.identity:
        _fail("$.git.executable", "Git executable identity changed")


def _executable_identity(details: os.stat_result) -> _ExecutableIdentity:
    return _ExecutableIdentity(
        details.st_dev,
        details.st_ino,
        details.st_mode,
        details.st_size,
        details.st_mtime_ns,
        details.st_ctime_ns,
    )


def _required(
    root: RetainedDirectory,
    root_name: str,
    path: str,
    metadata: list[_MetadataCarrier],
) -> AuthoritativeByteCarrier:
    carrier = root.read_authoritative(path)
    metadata.append(_MetadataCarrier(root_name, path, carrier))
    return carrier


def _optional(
    root: RetainedDirectory,
    root_name: str,
    path: str,
    metadata: list[_MetadataCarrier],
    absences: list[_AbsentMetadata],
) -> AuthoritativeByteCarrier | None:
    carrier = root.read_optional_authoritative(path)
    if carrier is None:
        absences.append(_AbsentMetadata(root_name, path))
    else:
        metadata.append(_MetadataCarrier(root_name, path, carrier))
    return carrier


def _absent(
    root: RetainedDirectory,
    root_name: str,
    path: str,
    absences: list[_AbsentMetadata],
) -> None:
    if root.read_optional_authoritative(path) is not None:
        _fail(f"$.git.{root_name}.{path}", "redirecting metadata is forbidden")
    absences.append(_AbsentMetadata(root_name, path))


def _root_mapping(state: _SessionState) -> dict[str, RetainedDirectory]:
    return {
        "workspace": state.workspace,
        "source": state.source,
        "parent": state.parent_git,
        "nested": state.nested_git,
    }


def _validate_source_contract(
    source_position: int,
    source_manifest: ExternalSourceManifest,
    source_lock: ExternalSourceLock,
    extensions: tuple[tuple[int, FacetExtensionManifest, FacetConstituentLock], ...],
) -> tuple[tuple[_OwnedExtension, ...], tuple[tuple[str, str], ...]]:
    if type(source_position) is not int or source_position < 0:
        _fail("$.source-position", "source position must be a non-negative integer")
    if type(source_manifest) is not ExternalSourceManifest:
        _fail("$.source", "source manifest has the wrong exact type")
    if type(source_lock) is not ExternalSourceLock:
        _fail("$.source", "source lock has the wrong exact type")
    if type(source_manifest.files) is not tuple or type(source_lock.files) is not tuple:
        _fail("$.source.files", "source files must be exact tuples")
    for index, locked_file in enumerate(source_lock.files):
        if type(locked_file) is not LockedFile:
            _fail(f"$.source.files[{index}]", "locked file has the wrong exact type")
    if (
        source_manifest.kind is not AcquisitionKind.GIT_SUBMODULE
        or source_lock.kind is not AcquisitionKind.GIT_SUBMODULE
        or source_lock.git is None
    ):
        _fail("$.source.kind", "source contract is not Git-submodule acquisition")
    if (
        source_manifest.namespace != source_lock.namespace
        or source_manifest.root != source_lock.git.registered_path
        or source_manifest.files != tuple(item.path for item in source_lock.files)
    ):
        _fail("$.source", "source manifest and lock differ")

    if type(extensions) is not tuple:
        _fail("$.facet-extensions", "owned extensions must be an exact tuple")
    owned: list[_OwnedExtension] = []
    seen_positions: set[int] = set()
    seen_paths = set(source_manifest.files)
    for index, extension_item in enumerate(extensions):
        location = f"$.facet-extensions[{index}]"
        if type(extension_item) is not tuple or len(extension_item) != 3:
            _fail(location, "owned extension has the wrong shape")
        position, manifest, lock = extension_item
        if type(position) is not int or position < 0 or position in seen_positions:
            _fail(location + ".position", "extension position is invalid or repeated")
        if type(manifest) is not FacetExtensionManifest:
            _fail(location, "extension manifest has the wrong exact type")
        if type(lock) is not FacetConstituentLock:
            _fail(location, "extension lock has the wrong exact type")
        if (
            manifest.namespace != source_manifest.namespace
            or manifest.kind is not AcquisitionKind.GIT_SUBMODULE
            or manifest.root != source_manifest.root
            or lock.namespace != manifest.namespace
            or lock.owner != manifest.namespace
            or lock.kind != manifest.kind.value
            or lock.path != manifest.path
            or lock.id.split("/", 1)[0] != manifest.namespace
            or lock.sha256 == ""
        ):
            _fail(location, "owned extension contract differs from its source")
        if manifest.path in seen_paths:
            _fail(location + ".path", "extension path is repeated")
        seen_positions.add(position)
        seen_paths.add(manifest.path)
        owned.append(_OwnedExtension(position, manifest, lock))
    if tuple(item.position for item in owned) != tuple(
        sorted(item.position for item in owned)
    ):
        _fail("$.facet-extensions", "extension positions are not ordered")
    files = tuple((item.lock.path, item.lock.sha256) for item in owned) + tuple(
        (item.path, item.sha256) for item in source_lock.files
    )
    return tuple(owned), files


def _contract_state(
    manifest: AcquisitionManifest,
    acquisition_lock: AcquisitionLock,
    source_position: int,
    source_manifest: ExternalSourceManifest,
    source_lock: ExternalSourceLock,
    extensions: tuple[_OwnedExtension, ...],
) -> object:
    return (
        identity_value_state(manifest),
        identity_value_state(acquisition_lock),
        type(source_position),
        source_position,
        identity_value_state(source_manifest),
        identity_value_state(source_lock),
        identity_value_state(extensions),
    )


def _snapshot_git_lock(value: GitLock) -> _GitLockSnapshot:
    if type(value) is not GitLock:
        _fail("$.git", "Git lock has the wrong exact type")
    try:
        registered_name = normalized_relative_path(
            value.registered_name, allow_dot=False
        )
        registered_path = normalized_relative_path(
            value.registered_path, allow_dot=False
        )
    except AcquisitionPathError as exc:
        _fail("$.git", str(exc))
    if value.object_format not in {"sha1", "sha256"}:
        _fail("$.git.object-format", "object format must be sha1 or sha256")
    size = 40 if value.object_format == "sha1" else 64
    for location, object_id in (
        ("$.git.commit", value.commit),
        ("$.git.parent-index-gitlink", value.parent_index_gitlink),
    ):
        if (
            type(object_id) is not str
            or len(object_id) != size
            or any(character not in "0123456789abcdef" for character in object_id)
        ):
            _fail(location, "object identifier has the wrong format")
    if value.commit != value.parent_index_gitlink:
        _fail("$.git.parent-index-gitlink", "value must equal the locked commit")
    if value.gitmodules_path != ".gitmodules":
        _fail("$.git.gitmodules-path", "path must be '.gitmodules'")
    if value.parent_index_mode != "160000":
        _fail("$.git.parent-index-mode", "mode must be '160000'")
    if not _is_sha256_digest(value.gitmodules_sha256):
        _fail("$.git.gitmodules-sha256", "digest has the wrong format")
    return _GitLockSnapshot(
        value.object_format,
        value.commit,
        value.gitmodules_path,
        value.gitmodules_sha256,
        registered_name,
        registered_path,
        value.parent_index_mode,
        value.parent_index_gitlink,
    )


def _validate_expected_files(
    value: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    if type(value) is not tuple or not value:
        _fail("$.git.files", "expected files must be a non-empty exact tuple")
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if type(item) is not tuple or len(item) != 2:
            _fail(f"$.git.files[{index}]", "expected file has the wrong shape")
        path, digest = item
        try:
            normalized = normalized_relative_path(path, allow_dot=False)
        except AcquisitionPathError as exc:
            _fail(f"$.git.files[{index}].path", str(exc))
        if normalized in seen:
            _fail(f"$.git.files[{index}].path", "path is repeated")
        if not _is_sha256_digest(digest):
            _fail(f"$.git.files[{index}].sha256", "digest has the wrong format")
        seen.add(normalized)
        result.append((normalized, digest))
    return tuple(result)


def _session_state(value: object) -> _SessionState:
    if type(value) is not _GitSubmoduleSession:
        _fail("$.git", "Git session has the wrong exact type")
    state = _SESSION_AUTHORITIES.state(value)
    if state is None:
        _fail("$.git", "Git session is closed or was not issued here")
    result = cast(_SessionState, state)
    if value._lock is not result.lock:
        _fail("$.git", "Git session state changed")
    return result


def _issue_git_evidence(state: _EvidenceState) -> _GitTransportEvidence:
    result = object.__new__(_GitTransportEvidence)
    _EVIDENCE_AUTHORITIES.issue(result, state)
    _issued_git_transport_state(result)
    return result


def _issued_git_transport_state(value: object) -> _EvidenceState:
    if type(value) is not _GitTransportEvidence:
        _fail("$.git", "Git evidence has the wrong exact type")
    state = _EVIDENCE_AUTHORITIES.state(value)
    if state is None:
        _fail("$.git", "Git evidence was not issued here")
    result = cast(_EvidenceState, state)
    if (
        _contract_state(
            result.acquisition_manifest,
            result.acquisition_lock,
            result.source_position,
            result.source_manifest,
            result.source_lock,
            result.extensions,
        )
        != result.contract_state
    ):
        _fail("$.git", "Git evidence source contract state changed")
    if identity_value_state(result.git_lock) != result.git_lock_state:
        _fail("$.git", "Git evidence lock state changed")
    return result


def _retire_and_close(value: _GitSubmoduleSession, state: _SessionState) -> None:
    _SESSION_AUTHORITIES.retire(value)
    _close_roots(state)


def _close_roots(state: _SessionState) -> None:
    _close_partial_roots(
        [state.workspace, state.source, state.parent_git, state.nested_git]
    )


def _close_partial_roots(roots: list[RetainedDirectory]) -> None:
    first_error: BaseException | None = None
    for root in reversed(roots):
        try:
            root.close()
        except BaseException as exc:
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise first_error


def _is_sha256_digest(value: object) -> bool:
    return (
        type(value) is str
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _sha256(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()


def _fail(location: str, message: str) -> NoReturn:
    raise AcquisitionContractError(location, message)
