"""Model and verify external-acquisition manifests, locks, and revisions."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from collections.abc import Iterable
from typing import NoReturn, cast

from .acquisition_schema import (
    validate_acquisition_lock_document,
    validate_acquisition_manifest_document,
)
from .acquisition_paths import AcquisitionPathError, normalized_relative_path
from .canonical_json import (
    CanonicalJsonError,
    jcs_bytes,
    parse_canonical_json_bytes,
)
from .exceptions import AcquisitionContractError
from .facets import FACET_REGISTRY_FILENAME

_NAMESPACE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
_IDENTIFIER = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?/[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$"
)
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_OID = {"sha1": re.compile(r"^[0-9a-f]{40}$"), "sha256": re.compile(r"^[0-9a-f]{64}$")}

PACKAGED_FACET_PATH = f"registries/{FACET_REGISTRY_FILENAME}"
PACKAGED_DECLARATION_PATHS = (
    "declaration-corpus-contract.yaml",
    "declaration-registry.yaml",
    "load-declaration-registry.yaml",
    "manual-judgment.yaml",
    "validate-declaration-registry.yaml",
)


class AcquisitionKind(StrEnum):
    """Offline transport kinds admitted for external declaration sources."""

    WORKSPACE = "workspace"
    VENDORED = "vendored"
    GIT_SUBMODULE = "git-submodule"


@dataclass(frozen=True)
class FacetExtensionManifest:
    """Name one owner-authorized additive facet registry."""

    namespace: str
    kind: AcquisitionKind
    root: str
    path: str


@dataclass(frozen=True)
class ExternalSourceManifest:
    """Name one ordered external declaration source."""

    namespace: str
    kind: AcquisitionKind
    root: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class AcquisitionManifest:
    """Retain the closed version 1 acquisition manifest."""

    schema_version: int
    facet_extensions: tuple[FacetExtensionManifest, ...]
    sources: tuple[ExternalSourceManifest, ...]


@dataclass(frozen=True)
class LockedFile:
    """Bind one logical source path to exact retained bytes."""

    path: str
    sha256: str


@dataclass(frozen=True)
class GitLock:
    """Retain the closed Git-submodule state recorded by the lock."""

    object_format: str
    commit: str
    gitmodules_path: str
    gitmodules_sha256: str
    registered_name: str
    registered_path: str
    parent_index_mode: str
    parent_index_gitlink: str


@dataclass(frozen=True)
class FacetConstituentLock:
    """Bind one facet-registry constituent to content and transport revisions."""

    acquisition_revision: str
    content_revision: str
    id: str
    kind: str
    namespace: str
    owner: str
    path: str
    sha256: str


@dataclass(frozen=True)
class FacetRegistryLock:
    """Bind the mandatory base and ordered additive facet extensions."""

    base: FacetConstituentLock
    content_revision: str
    extensions: tuple[FacetConstituentLock, ...]


@dataclass(frozen=True)
class InternalSourceLock:
    """Bind the code-owned packaged declaration corpus."""

    acquisition_revision: str
    content_revision: str
    files: tuple[LockedFile, ...]
    kind: str
    namespace: str


@dataclass(frozen=True)
class ExternalSourceLock:
    """Bind one external source's logical content and transport state."""

    acquisition_revision: str
    content_revision: str
    files: tuple[LockedFile, ...]
    kind: AcquisitionKind
    namespace: str
    git: GitLock | None


@dataclass(frozen=True)
class AcquisitionLock:
    """Retain the closed canonical lock value."""

    facet_registry: FacetRegistryLock
    internal_source: InternalSourceLock
    schema_version: int
    sources: tuple[ExternalSourceLock, ...]


def parse_acquisition_manifest(document: object) -> AcquisitionManifest:
    """Validate and detach one manifest document into immutable values."""
    source = validate_acquisition_manifest_document(document)
    _exact_version(source.get("schema-version"), "$.schema-version")
    sources = tuple(
        _manifest_source(item, index)
        for index, item in enumerate(cast(list[object], source["sources"]))
    )
    _unique(
        (item.namespace for item in sources),
        "$.sources",
        "namespace",
        field="namespace",
    )
    for index, item in enumerate(sources):
        if item.namespace == "eutaxis":
            _fail(
                f"$.sources[{index}].namespace",
                "the reserved namespace 'eutaxis' is packaged only",
            )

    extensions = tuple(
        _facet_extension(item, index)
        for index, item in enumerate(cast(list[object], source["facet-extensions"]))
    )
    _unique(
        (item.namespace for item in extensions),
        "$.facet-extensions",
        "namespace",
        field="namespace",
    )
    source_by_namespace = {item.namespace: item for item in sources}
    for index, extension in enumerate(extensions):
        owner = source_by_namespace.get(extension.namespace)
        location = f"$.facet-extensions[{index}]"
        if owner is None:
            _fail(location + ".namespace", "namespace has no external source entry")
        if owner.kind is not extension.kind:
            _fail(location + ".kind", "kind must match its source entry")
        if owner.root != extension.root:
            _fail(location + ".root", "root must match its source entry")
        if extension.path in owner.files:
            _fail(location + ".path", "facet path must differ from declaration files")
    return AcquisitionManifest(1, extensions, sources)


def _parse_acquisition_lock_document(document: object) -> AcquisitionLock:
    """Validate and detach one already-retained lock document."""
    source = validate_acquisition_lock_document(document)
    _exact_version(source.get("schema-version"), "$.schema-version")
    facet_source = _mapping(source["facet-registry"], "$.facet-registry")
    extensions = tuple(
        _facet_lock(item, f"$.facet-registry.extensions[{index}]")
        for index, item in enumerate(cast(list[object], facet_source["extensions"]))
    )
    _unique(
        (item.namespace for item in extensions),
        "$.facet-registry.extensions",
        "namespace",
        field="namespace",
    )
    facet_registry = FacetRegistryLock(
        _facet_lock(facet_source["base"], "$.facet-registry.base"),
        _digest_value(
            facet_source["content-revision"],
            "$.facet-registry.content-revision",
        ),
        extensions,
    )
    internal_source = _internal_lock(source["internal-source"])
    sources = tuple(
        _external_lock(item, index)
        for index, item in enumerate(cast(list[object], source["sources"]))
    )
    _unique(
        (item.namespace for item in sources),
        "$.sources",
        "namespace",
        field="namespace",
    )
    return AcquisitionLock(facet_registry, internal_source, 1, sources)


def parse_acquisition_lock_bytes(source: bytes) -> AcquisitionLock:
    """Parse a lock only when its bytes are exact canonical I-JSON."""
    try:
        document = parse_canonical_json_bytes(source)
    except CanonicalJsonError as exc:
        raise AcquisitionContractError("$", str(exc)) from exc
    return _parse_acquisition_lock_document(document)


def validated_packaged_lock(
    lock: AcquisitionLock,
) -> tuple[FacetConstituentLock, InternalSourceLock]:
    """Detach and validate the code-owned components of one closed lock."""
    _require_lock_state(lock)
    detached = _parse_acquisition_lock_document(_lock_document(lock))
    _validate_base_facets(detached.facet_registry)
    _validate_internal_source(detached.internal_source)
    return detached.facet_registry.base, detached.internal_source


def validate_acquisition_contract(
    manifest: AcquisitionManifest, lock: AcquisitionLock
) -> None:
    """Require one lock to match its manifest and every computed revision."""
    _require_manifest_state(manifest)
    _require_lock_state(lock)
    if lock.schema_version != manifest.schema_version:
        _fail("$.schema-version", "lock and manifest versions differ")
    _validate_base_facets(lock.facet_registry)
    _validate_internal_source(lock.internal_source)
    if len(lock.sources) != len(manifest.sources):
        _fail("$.sources", "lock source count differs from manifest")
    source_pairs = tuple(zip(manifest.sources, lock.sources, strict=True))
    for index, (source_manifest, source_lock) in enumerate(source_pairs):
        _validate_external_source(source_manifest, source_lock, index)

    if len(lock.facet_registry.extensions) != len(manifest.facet_extensions):
        _fail(
            "$.facet-registry.extensions",
            "lock extension count differs from manifest",
        )
    lock_by_namespace = {item.namespace: item for item in lock.sources}
    for index, (extension, extension_lock) in enumerate(
        zip(
            manifest.facet_extensions,
            lock.facet_registry.extensions,
            strict=True,
        )
    ):
        owner_source = lock_by_namespace.get(extension.namespace)
        if owner_source is None:
            _fail(
                f"$.facet-registry.extensions[{index}].namespace",
                "extension namespace has no locked source",
            )
        _validate_facet_extension(
            extension,
            extension_lock,
            owner_source,
            index,
        )
    expected_composite = composite_facet_content_revision(
        lock.facet_registry.base.content_revision,
        tuple(item.content_revision for item in lock.facet_registry.extensions),
    )
    _require_revision(
        lock.facet_registry.content_revision,
        expected_composite,
        "$.facet-registry.content-revision",
    )


def source_content_revision(namespace: str, files: tuple[LockedFile, ...]) -> str:
    """Return one transport-independent ordered source revision."""
    _namespace_value(namespace, "$.namespace")
    _require_locked_files(files, "$.files")
    if not files:
        _fail("$.files", "source file sequence must be non-empty")
    return _revision(
        {
            "namespace": namespace,
            "files": [{"path": item.path, "sha256": item.sha256} for item in files],
        }
    )


def facet_content_revision(
    identifier: str, namespace: str, owner: str, path: str, sha256: str
) -> str:
    """Return one transport-independent facet-constituent revision."""
    _identifier_value(identifier, "$.id")
    _namespace_value(namespace, "$.namespace")
    _namespace_value(owner, "$.owner")
    _normalized_path(path, allow_dot=False, location="$.path")
    _digest_value(sha256, "$.sha256")
    return _revision(
        {
            "id": identifier,
            "namespace": namespace,
            "owner": owner,
            "path": path,
            "sha256": sha256,
        }
    )


def composite_facet_content_revision(base: str, extensions: tuple[str, ...]) -> str:
    """Return the ordered composite facet-content revision."""
    _digest_value(base, "$.base")
    if type(extensions) is not tuple:
        _fail("$.extensions", "extensions must be an exact tuple")
    for index, revision in enumerate(extensions):
        _digest_value(revision, f"$.extensions[{index}]")
    return _revision({"base": base, "extensions": list(extensions)})


def _manifest_source(value: object, index: int) -> ExternalSourceManifest:
    location = f"$.sources[{index}]"
    source = _mapping(value, location)
    namespace = _namespace_value(source["namespace"], location + ".namespace")
    kind = AcquisitionKind(cast(str, source["kind"]))
    root = _normalized_path(source["root"], allow_dot=True, location=location + ".root")
    files = tuple(
        _normalized_path(item, allow_dot=False, location=f"{location}.files[{offset}]")
        for offset, item in enumerate(cast(list[object], source["files"]))
    )
    _unique(files, location + ".files", "path")
    return ExternalSourceManifest(namespace, kind, root, files)


def _facet_extension(value: object, index: int) -> FacetExtensionManifest:
    location = f"$.facet-extensions[{index}]"
    source = _mapping(value, location)
    return FacetExtensionManifest(
        _namespace_value(source["namespace"], location + ".namespace"),
        AcquisitionKind(cast(str, source["kind"])),
        _normalized_path(source["root"], allow_dot=True, location=location + ".root"),
        _normalized_path(source["path"], allow_dot=False, location=location + ".path"),
    )


def _facet_lock(value: object, location: str) -> FacetConstituentLock:
    source = _mapping(value, location)
    kind = _text(source["kind"], location + ".kind")
    if kind not in {"packaged", *(item.value for item in AcquisitionKind)}:
        _fail(location + ".kind", "unsupported facet transport kind")
    return FacetConstituentLock(
        _digest_value(
            source["acquisition-revision"], location + ".acquisition-revision"
        ),
        _digest_value(source["content-revision"], location + ".content-revision"),
        _identifier_value(source["id"], location + ".id"),
        kind,
        _namespace_value(source["namespace"], location + ".namespace"),
        _namespace_value(source["owner"], location + ".owner"),
        _normalized_path(source["path"], allow_dot=False, location=location + ".path"),
        _digest_value(source["sha256"], location + ".sha256"),
    )


def _internal_lock(value: object) -> InternalSourceLock:
    location = "$.internal-source"
    source = _mapping(value, location)
    files = _locked_files(source["files"], location + ".files")
    return InternalSourceLock(
        _digest_value(
            source["acquisition-revision"], location + ".acquisition-revision"
        ),
        _digest_value(source["content-revision"], location + ".content-revision"),
        files,
        _text(source["kind"], location + ".kind"),
        _namespace_value(source["namespace"], location + ".namespace"),
    )


def _external_lock(value: object, index: int) -> ExternalSourceLock:
    location = f"$.sources[{index}]"
    source = _mapping(value, location)
    kind = AcquisitionKind(cast(str, source["kind"]))
    git = _git_lock(source["git"], location + ".git") if "git" in source else None
    return ExternalSourceLock(
        _digest_value(
            source["acquisition-revision"], location + ".acquisition-revision"
        ),
        _digest_value(source["content-revision"], location + ".content-revision"),
        _locked_files(source["files"], location + ".files"),
        kind,
        _namespace_value(source["namespace"], location + ".namespace"),
        git,
    )


def _git_lock(value: object, location: str) -> GitLock:
    source = _mapping(value, location)
    object_format = _text(source["object-format"], location + ".object-format")
    commit = _object_id(source["commit"], object_format, location + ".commit")
    gitlink = _object_id(
        source["parent-index-gitlink"],
        object_format,
        location + ".parent-index-gitlink",
    )
    return GitLock(
        object_format,
        commit,
        _text(source["gitmodules-path"], location + ".gitmodules-path"),
        _digest_value(source["gitmodules-sha256"], location + ".gitmodules-sha256"),
        _normalized_path(
            source["registered-name"],
            allow_dot=False,
            location=location + ".registered-name",
        ),
        _normalized_path(
            source["registered-path"],
            allow_dot=False,
            location=location + ".registered-path",
        ),
        _text(source["parent-index-mode"], location + ".parent-index-mode"),
        gitlink,
    )


def _locked_files(value: object, location: str) -> tuple[LockedFile, ...]:
    files = tuple(
        LockedFile(
            _normalized_path(
                _mapping(item, f"{location}[{index}]")["path"],
                allow_dot=False,
                location=f"{location}[{index}].path",
            ),
            _digest_value(
                _mapping(item, f"{location}[{index}]")["sha256"],
                f"{location}[{index}].sha256",
            ),
        )
        for index, item in enumerate(cast(list[object], value))
    )
    _unique((item.path for item in files), location, "path", field="path")
    return files


def _validate_base_facets(
    registry: FacetRegistryLock,
    *,
    packaged_path: str = PACKAGED_FACET_PATH,
) -> None:
    base = registry.base
    location = "$.facet-registry.base"
    expected_fields = {
        "kind": "packaged",
        "namespace": "eutaxis",
        "owner": "eutaxis",
        "id": "eutaxis/context-facets",
        "path": packaged_path,
    }
    for field, expected in expected_fields.items():
        if getattr(base, field) != expected:
            _fail(location + f".{field}", "packaged facet-base value is not canonical")
    content = facet_content_revision(
        base.id, base.namespace, base.owner, base.path, base.sha256
    )
    _require_revision(base.content_revision, content, location + ".content-revision")
    acquisition = _revision(
        {
            "schema-version": 1,
            "namespace": "eutaxis",
            "kind": "packaged",
            "distribution": "eutaxis",
            "resource-root": "data",
            "path": packaged_path,
            "content-revision": content,
        }
    )
    _require_revision(
        base.acquisition_revision,
        acquisition,
        location + ".acquisition-revision",
    )


def _validate_internal_source(
    source: InternalSourceLock,
    *,
    packaged_paths: tuple[str, ...] = PACKAGED_DECLARATION_PATHS,
) -> None:
    location = "$.internal-source"
    if source.kind != "packaged":
        _fail(location + ".kind", "packaged internal-source kind is not canonical")
    if source.namespace != "eutaxis":
        _fail(
            location + ".namespace",
            "packaged internal-source namespace is not canonical",
        )
    if len(source.files) != len(packaged_paths):
        _fail(location + ".files", "packaged declaration file count is not canonical")
    for index, (file, expected_path) in enumerate(
        zip(source.files, packaged_paths, strict=True)
    ):
        if file.path != expected_path:
            _fail(
                f"{location}.files[{index}].path",
                "packaged declaration path is not canonical",
            )
    content = source_content_revision("eutaxis", source.files)
    _require_revision(source.content_revision, content, location + ".content-revision")
    acquisition = _revision(
        {
            "schema-version": 1,
            "namespace": "eutaxis",
            "kind": "packaged",
            "distribution": "eutaxis",
            "resource-root": "data/declarations/v1",
            "content-revision": content,
        }
    )
    _require_revision(
        source.acquisition_revision,
        acquisition,
        location + ".acquisition-revision",
    )


def _validate_external_source(
    manifest: ExternalSourceManifest, lock: ExternalSourceLock, index: int
) -> None:
    location = f"$.sources[{index}]"
    if manifest.namespace != lock.namespace:
        _fail(location + ".namespace", "namespace differs from manifest")
    if manifest.kind is not lock.kind:
        _fail(location + ".kind", "kind differs from manifest")
    if len(manifest.files) != len(lock.files):
        _fail(location + ".files", "file count differs from manifest")
    for offset, (manifest_path, locked_file) in enumerate(
        zip(manifest.files, lock.files, strict=True)
    ):
        if manifest_path != locked_file.path:
            _fail(
                f"{location}.files[{offset}].path",
                "logical path or order differs from manifest",
            )
    if (manifest.kind is AcquisitionKind.GIT_SUBMODULE) != (lock.git is not None):
        _fail(location + ".git", "Git state presence differs from transport kind")
    if lock.git is not None and lock.git.registered_path != manifest.root:
        _fail(location + ".git.registered-path", "registered path differs from root")
    if lock.git is not None:
        _validate_git_lock(lock.git, location + ".git")
    content = source_content_revision(lock.namespace, lock.files)
    _require_revision(lock.content_revision, content, location + ".content-revision")
    payload: dict[str, object] = {
        "schema-version": 1,
        "namespace": manifest.namespace,
        "kind": manifest.kind.value,
        "root": manifest.root,
        "content-revision": content,
    }
    if lock.git is not None:
        payload["git"] = _git_payload(lock.git)
    _require_revision(
        lock.acquisition_revision,
        _revision(payload),
        location + ".acquisition-revision",
    )


def _validate_facet_extension(
    manifest: FacetExtensionManifest,
    lock: FacetConstituentLock,
    source: ExternalSourceLock,
    index: int,
) -> None:
    location = f"$.facet-registry.extensions[{index}]"
    if lock.namespace != manifest.namespace:
        _fail(location + ".namespace", "namespace differs from manifest")
    if lock.owner != manifest.namespace:
        _fail(location + ".owner", "owner differs from manifest namespace")
    if lock.kind != manifest.kind.value:
        _fail(location + ".kind", "kind differs from manifest")
    if lock.path != manifest.path:
        _fail(location + ".path", "path differs from manifest")
    if lock.id.split("/", 1)[0] != manifest.namespace:
        _fail(location + ".id", "identifier namespace differs from manifest")
    content = facet_content_revision(
        lock.id, lock.namespace, lock.owner, lock.path, lock.sha256
    )
    _require_revision(lock.content_revision, content, location + ".content-revision")
    payload: dict[str, object] = {
        "schema-version": 1,
        "namespace": manifest.namespace,
        "kind": manifest.kind.value,
        "root": manifest.root,
        "path": manifest.path,
        "content-revision": content,
    }
    if source.git is not None:
        payload["git"] = _git_payload(source.git)
    _require_revision(
        lock.acquisition_revision,
        _revision(payload),
        location + ".acquisition-revision",
    )


def _git_payload(git: GitLock) -> dict[str, object]:
    return {
        "object-format": git.object_format,
        "commit": git.commit,
        "gitmodules-path": git.gitmodules_path,
        "gitmodules-sha256": git.gitmodules_sha256,
        "registered-name": git.registered_name,
        "registered-path": git.registered_path,
        "parent-index-mode": git.parent_index_mode,
        "parent-index-gitlink": git.parent_index_gitlink,
    }


def _validate_git_lock(git: GitLock, location: str) -> None:
    if git.gitmodules_path != ".gitmodules":
        _fail(location + ".gitmodules-path", "path must be '.gitmodules'")
    if git.parent_index_mode != "160000":
        _fail(location + ".parent-index-mode", "mode must be '160000'")
    if git.commit != git.parent_index_gitlink:
        _fail(
            location + ".parent-index-gitlink",
            "value must be identical to the locked commit",
        )


def _require_manifest_state(manifest: AcquisitionManifest) -> None:
    if type(manifest) is not AcquisitionManifest:
        _fail("$", "manifest must be an exact AcquisitionManifest")
    if type(manifest.schema_version) is not int or manifest.schema_version != 1:
        _fail("$.schema-version", "schema version must be the exact integer 1")
    if type(manifest.facet_extensions) is not tuple:
        _fail("$.facet-extensions", "facet extensions must be an exact tuple")
    if type(manifest.sources) is not tuple:
        _fail("$.sources", "sources must be an exact tuple")
    for index, extension in enumerate(manifest.facet_extensions):
        if type(extension) is not FacetExtensionManifest:
            _fail(
                f"$.facet-extensions[{index}]",
                "facet extension has the wrong exact type",
            )
        if type(extension.kind) is not AcquisitionKind:
            _fail(f"$.facet-extensions[{index}].kind", "kind has the wrong type")
    for index, source in enumerate(manifest.sources):
        if type(source) is not ExternalSourceManifest:
            _fail(f"$.sources[{index}]", "source has the wrong exact type")
        if type(source.kind) is not AcquisitionKind:
            _fail(f"$.sources[{index}].kind", "kind has the wrong type")
        if type(source.files) is not tuple:
            _fail(f"$.sources[{index}].files", "files must be an exact tuple")
    parse_acquisition_manifest(_manifest_document(manifest))


def _require_lock_state(lock: AcquisitionLock) -> None:
    if type(lock) is not AcquisitionLock:
        _fail("$", "lock must be an exact AcquisitionLock")
    if type(lock.schema_version) is not int or lock.schema_version != 1:
        _fail("$.schema-version", "schema version must be the exact integer 1")
    if type(lock.facet_registry) is not FacetRegistryLock:
        _fail("$.facet-registry", "facet registry has the wrong exact type")
    if type(lock.facet_registry.base) is not FacetConstituentLock:
        _fail("$.facet-registry.base", "facet base has the wrong exact type")
    if type(lock.facet_registry.extensions) is not tuple:
        _fail("$.facet-registry.extensions", "extensions must be an exact tuple")
    for index, extension in enumerate(lock.facet_registry.extensions):
        if type(extension) is not FacetConstituentLock:
            _fail(
                f"$.facet-registry.extensions[{index}]",
                "facet extension lock has the wrong exact type",
            )
    if type(lock.internal_source) is not InternalSourceLock:
        _fail("$.internal-source", "internal source has the wrong exact type")
    _require_locked_files(lock.internal_source.files, "$.internal-source.files")
    if type(lock.sources) is not tuple:
        _fail("$.sources", "sources must be an exact tuple")
    for index, source in enumerate(lock.sources):
        if type(source) is not ExternalSourceLock:
            _fail(f"$.sources[{index}]", "source lock has the wrong exact type")
        if type(source.kind) is not AcquisitionKind:
            _fail(f"$.sources[{index}].kind", "kind has the wrong type")
        _require_locked_files(source.files, f"$.sources[{index}].files")
        if source.git is not None and type(source.git) is not GitLock:
            _fail(f"$.sources[{index}].git", "Git lock has the wrong exact type")
    _parse_acquisition_lock_document(_lock_document(lock))


def _manifest_document(manifest: AcquisitionManifest) -> dict[str, object]:
    return {
        "schema-version": manifest.schema_version,
        "facet-extensions": [
            {
                "namespace": item.namespace,
                "kind": item.kind.value,
                "root": item.root,
                "path": item.path,
            }
            for item in manifest.facet_extensions
        ],
        "internal-source": {"namespace": "eutaxis", "kind": "packaged"},
        "sources": [
            {
                "namespace": item.namespace,
                "kind": item.kind.value,
                "root": item.root,
                "files": list(item.files),
            }
            for item in manifest.sources
        ],
    }


def _lock_document(lock: AcquisitionLock) -> dict[str, object]:
    return {
        "facet-registry": {
            "base": _facet_lock_document(lock.facet_registry.base),
            "content-revision": lock.facet_registry.content_revision,
            "extensions": [
                _facet_lock_document(item) for item in lock.facet_registry.extensions
            ],
        },
        "internal-source": {
            "acquisition-revision": lock.internal_source.acquisition_revision,
            "content-revision": lock.internal_source.content_revision,
            "files": [
                _locked_file_document(item, f"$.internal-source.files[{index}]")
                for index, item in enumerate(lock.internal_source.files)
            ],
            "kind": lock.internal_source.kind,
            "namespace": lock.internal_source.namespace,
        },
        "schema-version": lock.schema_version,
        "sources": [
            _source_lock_document(item, f"$.sources[{index}]")
            for index, item in enumerate(lock.sources)
        ],
    }


def _facet_lock_document(lock: FacetConstituentLock) -> dict[str, object]:
    return {
        "acquisition-revision": lock.acquisition_revision,
        "content-revision": lock.content_revision,
        "id": lock.id,
        "kind": lock.kind,
        "namespace": lock.namespace,
        "owner": lock.owner,
        "path": lock.path,
        "sha256": lock.sha256,
    }


def _source_lock_document(lock: ExternalSourceLock, location: str) -> dict[str, object]:
    document: dict[str, object] = {
        "acquisition-revision": lock.acquisition_revision,
        "content-revision": lock.content_revision,
        "files": [
            _locked_file_document(item, f"{location}.files[{index}]")
            for index, item in enumerate(lock.files)
        ],
        "kind": lock.kind.value,
        "namespace": lock.namespace,
    }
    if lock.git is not None:
        document["git"] = _git_payload(lock.git)
    return document


def _locked_file_document(file: LockedFile, location: str) -> dict[str, object]:
    if type(file) is not LockedFile:
        _fail(location, "file has the wrong exact type")
    return {"path": file.path, "sha256": file.sha256}


def _require_locked_files(files: tuple[LockedFile, ...], location: str) -> None:
    if type(files) is not tuple:
        _fail(location, "files must be an exact tuple")
    for index, item in enumerate(files):
        if type(item) is not LockedFile:
            _fail(f"{location}[{index}]", "file has the wrong exact type")
        _normalized_path(
            item.path, allow_dot=False, location=f"{location}[{index}].path"
        )
        _digest_value(item.sha256, f"{location}[{index}].sha256")
    _unique((item.path for item in files), location, "path", field="path")


def _mapping(value: object, location: str) -> dict[str, object]:
    if type(value) is not dict:
        _fail(location, "value must be an exact object")
    return cast(dict[str, object], value)


def _text(value: object, location: str) -> str:
    if type(value) is not str:
        _fail(location, "value must be exact text")
    return cast(str, value)


def _namespace_value(value: object, location: str) -> str:
    text = _text(value, location)
    if _NAMESPACE.fullmatch(text) is None:
        _fail(location, "value does not use the namespace grammar")
    return text


def _identifier_value(value: object, location: str) -> str:
    text = _text(value, location)
    if _IDENTIFIER.fullmatch(text) is None:
        _fail(location, "value does not use the external identifier grammar")
    return text


def _digest_value(value: object, location: str) -> str:
    text = _text(value, location)
    if _DIGEST.fullmatch(text) is None:
        _fail(location, "value is not a canonical SHA-256 digest")
    return text


def _object_id(value: object, object_format: str, location: str) -> str:
    text = _text(value, location)
    expression = _OID.get(object_format)
    if expression is None or expression.fullmatch(text) is None:
        _fail(location, f"value does not match the {object_format!r} object format")
    return text


def _normalized_path(value: object, *, allow_dot: bool, location: str) -> str:
    try:
        return normalized_relative_path(value, allow_dot=allow_dot)
    except AcquisitionPathError as exc:
        _fail(location, str(exc))


def _exact_version(value: object, location: str) -> None:
    if type(value) is not int or value != 1:
        _fail(location, "schema version must be the exact integer 1")


def _unique(
    values: Iterable[str],
    location: str,
    noun: str,
    *,
    field: str | None = None,
) -> None:
    seen: set[str] = set()
    for index, value in enumerate(values):
        if value in seen:
            suffix = f"[{index}]" + ("" if field is None else f".{field}")
            _fail(location + suffix, f"{noun} duplicates an earlier value")
        seen.add(value)


def _revision(payload: dict[str, object]) -> str:
    return "sha256:" + hashlib.sha256(jcs_bytes(payload)).hexdigest()


def _require_revision(actual: str, expected: str, location: str) -> None:
    if actual != expected:
        _fail(location, f"revision differs from computed value {expected!r}")


def _fail(location: str, message: str) -> NoReturn:
    raise AcquisitionContractError(location, message)
