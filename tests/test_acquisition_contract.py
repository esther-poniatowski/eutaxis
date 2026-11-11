"""Exercise immutable acquisition contracts and their revision algebra."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator
import eutaxis.declarations as declarations_api

from eutaxis.declarations.acquisition_contract import (
    PACKAGED_DECLARATION_PATHS,
    AcquisitionKind,
    ExternalSourceManifest,
    FacetExtensionManifest,
    GitLock,
    LockedFile,
    _external_source_acquisition_revision,
    _facet_extension_acquisition_revision,
    acquisition_lock_json_bytes,
    _parse_acquisition_lock_document,
    composite_facet_content_revision,
    facet_content_revision,
    parse_acquisition_lock_bytes,
    parse_acquisition_manifest,
    source_content_revision,
    validate_acquisition_contract,
)
from eutaxis.declarations.acquisition_schema import (
    acquisition_lock_schema,
    acquisition_manifest_schema,
)
from eutaxis.declarations.canonical_json import jcs_bytes
from eutaxis.declarations.exceptions import AcquisitionContractError

ZERO = "sha256:" + "0" * 64
parse_acquisition_lock = _parse_acquisition_lock_document


class _Text(str):
    pass


class _Integer(int):
    pass


def _digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def _revision(value: object) -> str:
    return "sha256:" + hashlib.sha256(jcs_bytes(value)).hexdigest()


def _manifest(*, kind: str = "workspace", root: str = ".") -> dict[str, object]:
    return {
        "schema-version": 1,
        "facet-extensions": [
            {
                "namespace": "oikos",
                "kind": kind,
                "root": root,
                "path": "declarations/context-facets.yaml",
            }
        ],
        "internal-source": {"namespace": "eutaxis", "kind": "packaged"},
        "sources": [
            {
                "namespace": "oikos",
                "kind": kind,
                "root": root,
                "files": ["declarations/process-core.yaml"],
            }
        ],
    }


def _git(root: str) -> dict[str, object]:
    commit = "a" * 40
    return {
        "object-format": "sha1",
        "commit": commit,
        "gitmodules-path": ".gitmodules",
        "gitmodules-sha256": _digest("gitmodules"),
        "registered-name": "oikos",
        "registered-path": root,
        "parent-index-mode": "160000",
        "parent-index-gitlink": commit,
    }


def _lock(*, kind: str = "workspace", root: str = ".") -> dict[str, object]:
    base_sha = _digest("base")
    base_content = facet_content_revision(
        "eutaxis/context-facets",
        "eutaxis",
        "eutaxis",
        "registries/context-facets-v1.yaml",
        base_sha,
    )
    base_acquisition = _revision(
        {
            "schema-version": 1,
            "namespace": "eutaxis",
            "kind": "packaged",
            "distribution": "eutaxis",
            "resource-root": "data",
            "path": "registries/context-facets-v1.yaml",
            "content-revision": base_content,
        }
    )
    extension_sha = _digest("extension")
    extension_content = facet_content_revision(
        "oikos/context-facets",
        "oikos",
        "oikos",
        "declarations/context-facets.yaml",
        extension_sha,
    )
    extension_payload: dict[str, object] = {
        "schema-version": 1,
        "namespace": "oikos",
        "kind": kind,
        "root": root,
        "path": "declarations/context-facets.yaml",
        "content-revision": extension_content,
    }
    source_file = {
        "path": "declarations/process-core.yaml",
        "sha256": _digest("source"),
    }
    source_content = _revision({"namespace": "oikos", "files": [source_file]})
    source_payload: dict[str, object] = {
        "schema-version": 1,
        "namespace": "oikos",
        "kind": kind,
        "root": root,
        "content-revision": source_content,
    }
    if kind == "git-submodule":
        git = _git(root)
        extension_payload["git"] = git
        source_payload["git"] = git
    internal_files = [
        {"path": path, "sha256": _digest("internal:" + path)}
        for path in PACKAGED_DECLARATION_PATHS
    ]
    internal_content = _revision({"namespace": "eutaxis", "files": internal_files})
    internal_acquisition = _revision(
        {
            "schema-version": 1,
            "namespace": "eutaxis",
            "kind": "packaged",
            "distribution": "eutaxis",
            "resource-root": "data/declarations/v1",
            "content-revision": internal_content,
        }
    )
    source: dict[str, object] = {
        "acquisition-revision": _revision(source_payload),
        "content-revision": source_content,
        "files": [source_file],
        "kind": kind,
        "namespace": "oikos",
    }
    if kind == "git-submodule":
        source["git"] = _git(root)
    return {
        "facet-registry": {
            "base": {
                "acquisition-revision": base_acquisition,
                "content-revision": base_content,
                "id": "eutaxis/context-facets",
                "kind": "packaged",
                "namespace": "eutaxis",
                "owner": "eutaxis",
                "path": "registries/context-facets-v1.yaml",
                "sha256": base_sha,
            },
            "content-revision": composite_facet_content_revision(
                base_content, (extension_content,)
            ),
            "extensions": [
                {
                    "acquisition-revision": _revision(extension_payload),
                    "content-revision": extension_content,
                    "id": "oikos/context-facets",
                    "kind": kind,
                    "namespace": "oikos",
                    "owner": "oikos",
                    "path": "declarations/context-facets.yaml",
                    "sha256": extension_sha,
                }
            ],
        },
        "internal-source": {
            "acquisition-revision": internal_acquisition,
            "content-revision": internal_content,
            "files": internal_files,
            "kind": "packaged",
            "namespace": "eutaxis",
        },
        "schema-version": 1,
        "sources": [source],
    }


def _append_second_contract(
    manifest: dict[str, object], lock: dict[str, object]
) -> None:
    namespace = "hermeneia"
    kind = "vendored"
    root = "vendor/hermeneia"
    path = "declarations/context-facets.yaml"
    file = {"path": "declarations/prose.yaml", "sha256": _digest("hermeneia")}
    source_content = _revision({"namespace": namespace, "files": [file]})
    source_acquisition = _revision(
        {
            "schema-version": 1,
            "namespace": namespace,
            "kind": kind,
            "root": root,
            "content-revision": source_content,
        }
    )
    facet_sha = _digest("hermeneia-facets")
    facet_content = facet_content_revision(
        f"{namespace}/context-facets", namespace, namespace, path, facet_sha
    )
    facet_acquisition = _revision(
        {
            "schema-version": 1,
            "namespace": namespace,
            "kind": kind,
            "root": root,
            "path": path,
            "content-revision": facet_content,
        }
    )
    manifest["sources"].append(  # type: ignore[union-attr]
        {
            "namespace": namespace,
            "kind": kind,
            "root": root,
            "files": [file["path"]],
        }
    )
    manifest["facet-extensions"].append(  # type: ignore[union-attr]
        {"namespace": namespace, "kind": kind, "root": root, "path": path}
    )
    source = {
        "acquisition-revision": source_acquisition,
        "content-revision": source_content,
        "files": [file],
        "kind": kind,
        "namespace": namespace,
    }
    lock["sources"].append(source)  # type: ignore[union-attr]
    registry = lock["facet-registry"]
    extension = {
        "acquisition-revision": facet_acquisition,
        "content-revision": facet_content,
        "id": f"{namespace}/context-facets",
        "kind": kind,
        "namespace": namespace,
        "owner": namespace,
        "path": path,
        "sha256": facet_sha,
    }
    registry["extensions"].append(extension)  # type: ignore[index]
    registry["content-revision"] = composite_facet_content_revision(  # type: ignore[index]
        registry["base"]["content-revision"],  # type: ignore[index]
        tuple(item["content-revision"] for item in registry["extensions"]),  # type: ignore[index]
    )


def test_packaged_schemas_are_valid_and_return_isolated_values() -> None:
    manifest_schema = acquisition_manifest_schema()
    lock_schema = acquisition_lock_schema()
    Draft202012Validator.check_schema(manifest_schema)
    Draft202012Validator.check_schema(lock_schema)
    manifest_schema["title"] = "changed"
    assert acquisition_manifest_schema()["title"] != "changed"


@pytest.mark.parametrize(
    ("kind", "root"),
    [
        ("workspace", "."),
        ("vendored", "vendor/oikos"),
        ("git-submodule", "vendor/oikos"),
    ],
)
def test_manifest_and_lock_form_one_valid_immutable_contract(
    kind: str, root: str
) -> None:
    manifest_document = _manifest(kind=kind, root=root)
    lock_document = _lock(kind=kind, root=root)
    manifest = parse_acquisition_manifest(manifest_document)
    lock = parse_acquisition_lock(lock_document)
    validate_acquisition_contract(manifest, lock)
    assert manifest.sources[0].files == ("declarations/process-core.yaml",)
    assert lock.sources[0].kind is AcquisitionKind(kind)
    manifest_document["sources"] = []
    assert manifest.sources
    assert parse_acquisition_lock_bytes(jcs_bytes(lock_document)) == lock
    assert acquisition_lock_json_bytes(manifest, lock) == jcs_bytes(lock_document)
    assert (
        parse_acquisition_lock_bytes(acquisition_lock_json_bytes(manifest, lock))
        == lock
    )


def test_lock_serialization_rejects_a_forged_lock_value() -> None:
    manifest = parse_acquisition_manifest(_manifest())
    lock = parse_acquisition_lock(_lock())
    forged = replace(lock, schema_version=True)
    with pytest.raises(AcquisitionContractError, match="schema version"):
        acquisition_lock_json_bytes(manifest, forged)


def test_lock_serialization_rejects_revision_inconsistency() -> None:
    manifest = parse_acquisition_manifest(_manifest())
    lock = parse_acquisition_lock(_lock())
    forged_source = replace(lock.sources[0], acquisition_revision=ZERO)
    forged = replace(lock, sources=(forged_source,))
    with pytest.raises(AcquisitionContractError) as raised:
        acquisition_lock_json_bytes(manifest, forged)
    assert raised.value.location == "$.sources[0].acquisition-revision"


def test_source_revision_rejects_forged_manifest_collection_state() -> None:
    source = parse_acquisition_manifest(_manifest()).sources[0]
    forged = replace(source, files=[*source.files])  # type: ignore[arg-type]
    with pytest.raises(AcquisitionContractError, match="exact tuple"):
        _external_source_acquisition_revision(forged, _digest("content"), None)


@pytest.mark.parametrize(
    "source",
    [
        ExternalSourceManifest(
            "oikos",
            AcquisitionKind.WORKSPACE,
            ".",
            (),
        ),
        ExternalSourceManifest(
            "eutaxis",
            AcquisitionKind.WORKSPACE,
            ".",
            ("declarations/process-core.yaml",),
        ),
    ],
)
def test_source_revision_rejects_manifest_semantic_invalidity(
    source: ExternalSourceManifest,
) -> None:
    with pytest.raises(AcquisitionContractError):
        _external_source_acquisition_revision(source, _digest("content"), None)


def test_facet_revision_sentinel_does_not_collide_with_valid_facet_path() -> None:
    manifest = FacetExtensionManifest(
        "oikos",
        AcquisitionKind.WORKSPACE,
        ".",
        "declarations/.revision-input.yaml",
    )
    revision = _facet_extension_acquisition_revision(
        manifest,
        _digest("content"),
        None,
    )
    assert revision.startswith("sha256:")


@pytest.mark.parametrize(
    ("field", "value", "location"),
    [
        ("object_format", "md5", "$.git.object-format"),
        ("object_format", [], "$.git.object-format"),
        ("commit", "a" * 39, "$.git.commit"),
        ("gitmodules_path", "modules", "$.git.gitmodules-path"),
        ("gitmodules_sha256", "sha256:ABC", "$.git.gitmodules-sha256"),
        ("registered_name", "../oikos", "$.git.registered-name"),
        ("registered_path", "vendor/other", "$.git.registered-path"),
        ("parent_index_mode", "100644", "$.git.parent-index-mode"),
        ("parent_index_gitlink", "b" * 40, "$.git.parent-index-gitlink"),
    ],
)
def test_source_revision_rejects_incomplete_direct_git_state(
    field: str,
    value: object,
    location: str,
) -> None:
    source = ExternalSourceManifest(
        "oikos",
        AcquisitionKind.GIT_SUBMODULE,
        "vendor/oikos",
        ("declarations/process-core.yaml",),
    )
    document = _git("vendor/oikos")
    git = GitLock(
        document["object-format"],
        document["commit"],
        document["gitmodules-path"],
        document["gitmodules-sha256"],
        document["registered-name"],
        document["registered-path"],
        document["parent-index-mode"],
        document["parent-index-gitlink"],
    )
    forged = replace(git, **{field: value})
    with pytest.raises(AcquisitionContractError) as raised:
        _external_source_acquisition_revision(source, _digest("content"), forged)
    assert raised.value.location == location


@pytest.mark.parametrize(
    ("mutation", "expected_location"),
    [
        (lambda document: document.update({"unexpected": True}), "$.unexpected"),
        (
            lambda document: document["sources"][0].update({"unexpected": True}),
            "$.sources[0].unexpected",
        ),
        (
            lambda document: document["sources"][0].pop("content-revision"),
            "$.sources[0]",
        ),
        (
            lambda document: document["sources"][0].update(
                {"content-revision": "sha256:ABC"}
            ),
            "$.sources[0].content-revision",
        ),
    ],
)
def test_lock_rejects_closed_shape_and_digest_grammar(
    mutation, expected_location: str
) -> None:
    document = _lock()
    mutation(document)
    with pytest.raises(AcquisitionContractError) as raised:
        parse_acquisition_lock(document)
    assert raised.value.location == expected_location


@pytest.mark.parametrize(
    ("field", "value", "expected_location"),
    [
        ("object-format", "sha256", "$.sources[0].git.commit"),
        ("gitmodules-path", "metadata", "$.sources[0].git.gitmodules-path"),
        ("parent-index-mode", "100644", "$.sources[0].git.parent-index-mode"),
    ],
)
def test_git_lock_rejects_oid_and_fixed_field_violations(
    field: str, value: str, expected_location: str
) -> None:
    document = _lock(kind="git-submodule", root="vendor/oikos")
    document["sources"][0]["git"][field] = value  # type: ignore[index]
    with pytest.raises(AcquisitionContractError) as raised:
        parse_acquisition_lock(document)
    assert raised.value.location == expected_location


def test_git_state_presence_is_exactly_kind_specific() -> None:
    missing = _lock(kind="git-submodule", root="vendor/oikos")
    missing["sources"][0].pop("git")  # type: ignore[index]
    with pytest.raises(AcquisitionContractError):
        parse_acquisition_lock(missing)

    extraneous = _lock()
    extraneous["sources"][0]["git"] = _git(".")  # type: ignore[index]
    with pytest.raises(AcquisitionContractError):
        parse_acquisition_lock(extraneous)


@pytest.mark.parametrize(
    ("part", "field", "value", "expected_location"),
    [
        ("base", "namespace", "other", "$.facet-registry.base.namespace"),
        (
            "extension",
            "id",
            "other/context-facets",
            "$.facet-registry.extensions[0].id",
        ),
        (
            "extension",
            "namespace",
            "other",
            "$.facet-registry.extensions[0].namespace",
        ),
        (
            "extension",
            "owner",
            "other",
            "$.facet-registry.extensions[0].owner",
        ),
        (
            "extension",
            "path",
            "declarations/other-facets.yaml",
            "$.facet-registry.extensions[0].path",
        ),
    ],
)
def test_contract_rejects_facet_identity_impersonation(
    part: str, field: str, value: str, expected_location: str
) -> None:
    manifest = parse_acquisition_manifest(_manifest())
    document = _lock()
    registry = document["facet-registry"]
    target = registry["base"] if part == "base" else registry["extensions"][0]  # type: ignore[index]
    target[field] = value
    lock = parse_acquisition_lock(document)
    with pytest.raises(AcquisitionContractError) as raised:
        validate_acquisition_contract(manifest, lock)
    assert raised.value.location == expected_location


def test_contract_rejects_packaged_internal_file_list_mismatch() -> None:
    manifest = parse_acquisition_manifest(_manifest())
    document = _lock()
    document["internal-source"]["files"].pop()  # type: ignore[index]
    lock = parse_acquisition_lock(document)
    with pytest.raises(AcquisitionContractError) as raised:
        validate_acquisition_contract(manifest, lock)
    assert raised.value.location == "$.internal-source.files"


def test_contract_locates_packaged_internal_path_mismatch() -> None:
    manifest = parse_acquisition_manifest(_manifest())
    document = _lock()
    document["internal-source"]["files"][1]["path"] = "other.yaml"  # type: ignore[index]
    lock = parse_acquisition_lock(document)
    with pytest.raises(AcquisitionContractError) as raised:
        validate_acquisition_contract(manifest, lock)
    assert raised.value.location == "$.internal-source.files[1].path"


def test_contract_rejects_source_file_and_order_mismatch() -> None:
    manifest_document = _manifest()
    manifest_document["sources"][0]["files"] = [  # type: ignore[index]
        "declarations/other.yaml"
    ]
    manifest = parse_acquisition_manifest(manifest_document)
    lock = parse_acquisition_lock(_lock())
    with pytest.raises(AcquisitionContractError) as raised:
        validate_acquisition_contract(manifest, lock)
    assert raised.value.location == "$.sources[0].files[0].path"


def test_contract_rejects_source_entry_order_mismatch() -> None:
    manifest_document = _manifest()
    lock_document = _lock()
    _append_second_contract(manifest_document, lock_document)
    manifest_document["sources"].reverse()  # type: ignore[union-attr]
    manifest = parse_acquisition_manifest(manifest_document)
    lock = parse_acquisition_lock(lock_document)
    with pytest.raises(AcquisitionContractError) as raised:
        validate_acquisition_contract(manifest, lock)
    assert raised.value.location == "$.sources[0].namespace"


def test_contract_rejects_facet_extension_order_mismatch() -> None:
    manifest_document = _manifest()
    lock_document = _lock()
    _append_second_contract(manifest_document, lock_document)
    manifest_document["facet-extensions"].reverse()  # type: ignore[union-attr]
    manifest = parse_acquisition_manifest(manifest_document)
    lock = parse_acquisition_lock(lock_document)
    with pytest.raises(AcquisitionContractError) as raised:
        validate_acquisition_contract(manifest, lock)
    assert raised.value.location == "$.facet-registry.extensions[0].namespace"


def test_contract_rejects_git_registered_root_mismatch() -> None:
    manifest = parse_acquisition_manifest(
        _manifest(kind="git-submodule", root="vendor/oikos")
    )
    document = _lock(kind="git-submodule", root="vendor/oikos")
    document["sources"][0]["git"]["registered-path"] = "vendor/other"  # type: ignore[index]
    lock = parse_acquisition_lock(document)
    with pytest.raises(AcquisitionContractError) as raised:
        validate_acquisition_contract(manifest, lock)
    assert raised.value.location == "$.sources[0].git.registered-path"


@pytest.mark.parametrize("version", [True, 1.0, _Integer(1)])
@pytest.mark.parametrize("factory", [_manifest, _lock])
def test_schema_version_is_the_exact_integer_one(factory, version: object) -> None:
    document = factory()
    document["schema-version"] = version
    parser = (
        parse_acquisition_manifest if factory is _manifest else parse_acquisition_lock
    )
    with pytest.raises(AcquisitionContractError, match="exact integer 1|exact JSON"):
        parser(document)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("root", "/absolute"),
        ("root", "a\\b"),
        ("root", "a//b"),
        ("root", "a/./b"),
        ("root", "a/../b"),
        ("root", "a\x00b"),
        ("root", ""),
        ("files", ["."]),
    ],
)
def test_manifest_rejects_every_non_normalized_path_form(
    field: str, value: object
) -> None:
    document = _manifest()
    source = document["sources"][0]  # type: ignore[index]
    source[field] = value  # type: ignore[index]
    if field == "root":
        document["facet-extensions"][0]["root"] = value  # type: ignore[index]
    with pytest.raises(AcquisitionContractError):
        parse_acquisition_manifest(document)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda document: document.update({"unknown": 1}),
        lambda document: document["sources"].append(deepcopy(document["sources"][0])),
        lambda document: document["facet-extensions"].append(
            deepcopy(document["facet-extensions"][0])
        ),
        lambda document: document["sources"][0]["files"].append(
            "declarations/process-core.yaml"
        ),
        lambda document: document["sources"][0].update({"namespace": "eutaxis"}),
        lambda document: document["facet-extensions"][0].update(
            {"namespace": "unowned"}
        ),
        lambda document: document["facet-extensions"][0].update(
            {"path": "declarations/process-core.yaml"}
        ),
    ],
)
def test_manifest_rejects_closed_shape_and_ownership_violations(mutation) -> None:
    document = _manifest()
    mutation(document)
    with pytest.raises(AcquisitionContractError):
        parse_acquisition_manifest(document)


@pytest.mark.parametrize(
    "source",
    [
        b'{"a":1}\n',
        b'{ "a":1}',
        b'{"a":1,"a":1}',
    ],
)
def test_lock_byte_parser_rejects_noncanonical_json(source: bytes) -> None:
    with pytest.raises(AcquisitionContractError):
        parse_acquisition_lock_bytes(source)


def test_git_submodule_contract_binds_identical_commit_and_gitlink() -> None:
    manifest = parse_acquisition_manifest(
        _manifest(kind="git-submodule", root="vendor/oikos")
    )
    lock = parse_acquisition_lock(_lock(kind="git-submodule", root="vendor/oikos"))
    validate_acquisition_contract(manifest, lock)
    git = lock.sources[0].git
    assert git is not None
    forged = replace(
        lock,
        sources=(
            replace(
                lock.sources[0],
                git=replace(git, parent_index_gitlink="b" * 40),
            ),
        ),
    )
    with pytest.raises(AcquisitionContractError, match="must be identical") as raised:
        validate_acquisition_contract(manifest, forged)
    assert raised.value.location == "$.sources[0].git.parent-index-gitlink"


@pytest.mark.parametrize(
    ("field", "value"),
    [("kind", "vendored"), ("root", "other")],
)
def test_manifest_extension_mismatch_names_the_deepest_field(
    field: str, value: str
) -> None:
    document = _manifest()
    document["facet-extensions"][0][field] = value  # type: ignore[index]
    with pytest.raises(AcquisitionContractError) as raised:
        parse_acquisition_manifest(document)
    assert raised.value.location == f"$.facet-extensions[0].{field}"


@pytest.mark.parametrize(
    ("field", "value"),
    [("namespace", "other"), ("kind", "vendored")],
)
def test_locked_source_mismatch_names_the_deepest_field(field: str, value: str) -> None:
    manifest = parse_acquisition_manifest(_manifest())
    document = _lock()
    document["sources"][0][field] = value  # type: ignore[index]
    lock = parse_acquisition_lock(document)
    with pytest.raises(AcquisitionContractError) as raised:
        validate_acquisition_contract(manifest, lock)
    assert raised.value.location == f"$.sources[0].{field}"


def test_normative_path_grammar_admits_internal_newlines() -> None:
    manifest = parse_acquisition_manifest(_manifest(root="root\ncomponent"))
    assert manifest.sources[0].root == "root\ncomponent"

    document = _lock()
    document["facet-registry"]["extensions"][0]["path"] = (  # type: ignore[index]
        "declarations/context\nfacets.yaml"
    )
    lock = parse_acquisition_lock(document)
    assert lock.facet_registry.extensions[0].path == "declarations/context\nfacets.yaml"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda lock: replace(lock, schema_version=True),
        lambda lock: replace(lock, sources=list(lock.sources)),
        lambda lock: replace(
            lock,
            internal_source=replace(lock.internal_source, namespace=_Text("eutaxis")),
        ),
        lambda lock: replace(
            lock,
            sources=(replace(lock.sources[0], files=list(lock.sources[0].files)),),
        ),
    ],
)
def test_direct_model_construction_cannot_bypass_exact_carrier_checks(mutate) -> None:
    manifest = parse_acquisition_manifest(_manifest())
    lock = parse_acquisition_lock(_lock())
    with pytest.raises(AcquisitionContractError):
        validate_acquisition_contract(manifest, mutate(lock))


def test_object_lock_parser_is_not_a_public_api() -> None:
    assert not hasattr(declarations_api, "parse_acquisition_lock")


@pytest.mark.parametrize(
    ("field", "expected_location"),
    [
        ("facet_extensions", "$.facet-extensions"),
        ("sources", "$.sources"),
    ],
)
def test_direct_manifest_collection_forgery_retains_field_location(
    field: str, expected_location: str
) -> None:
    manifest = parse_acquisition_manifest(_manifest())
    lock = parse_acquisition_lock(_lock())
    forged = replace(manifest, **{field: list(getattr(manifest, field))})
    with pytest.raises(AcquisitionContractError) as raised:
        validate_acquisition_contract(forged, lock)
    assert raised.value.location == expected_location


@pytest.mark.parametrize(
    ("mutate", "expected_location"),
    [
        (
            lambda lock: replace(
                lock,
                internal_source=replace(
                    lock.internal_source, files=list(lock.internal_source.files)
                ),
            ),
            "$.internal-source.files",
        ),
        (
            lambda lock: replace(
                lock,
                internal_source=replace(
                    lock.internal_source,
                    files=(object(), *lock.internal_source.files[1:]),
                ),
            ),
            "$.internal-source.files[0]",
        ),
        (
            lambda lock: replace(
                lock,
                sources=(replace(lock.sources[0], files=list(lock.sources[0].files)),),
            ),
            "$.sources[0].files",
        ),
        (
            lambda lock: replace(
                lock,
                sources=(
                    replace(
                        lock.sources[0],
                        files=(object(), *lock.sources[0].files[1:]),
                    ),
                ),
            ),
            "$.sources[0].files[0]",
        ),
    ],
)
def test_direct_file_model_forgery_retains_full_lock_location(
    mutate, expected_location: str
) -> None:
    manifest = parse_acquisition_manifest(_manifest())
    lock = parse_acquisition_lock(_lock())
    with pytest.raises(AcquisitionContractError) as raised:
        validate_acquisition_contract(manifest, mutate(lock))
    assert raised.value.location == expected_location


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("sources", 0, "content-revision"), ZERO),
        (("sources", 0, "acquisition-revision"), ZERO),
        (("facet-registry", "base", "content-revision"), ZERO),
        (("facet-registry", "base", "acquisition-revision"), ZERO),
        (("facet-registry", "extensions", 0, "content-revision"), ZERO),
        (("facet-registry", "extensions", 0, "acquisition-revision"), ZERO),
        (("facet-registry", "content-revision"), ZERO),
        (("internal-source", "content-revision"), ZERO),
        (("internal-source", "acquisition-revision"), ZERO),
    ],
)
def test_every_revision_class_is_recomputed(
    path: tuple[object, ...], value: str
) -> None:
    manifest = parse_acquisition_manifest(_manifest())
    document = _lock()
    target = document
    for component in path[:-1]:
        target = target[component]  # type: ignore[index,assignment]
    target[path[-1]] = value  # type: ignore[index]
    lock = parse_acquisition_lock(document)
    with pytest.raises(AcquisitionContractError, match="computed value"):
        validate_acquisition_contract(manifest, lock)


def test_content_revision_excludes_transport_but_acquisition_revision_binds_it() -> (
    None
):
    workspace = parse_acquisition_lock(_lock(kind="workspace", root="source"))
    vendored = parse_acquisition_lock(_lock(kind="vendored", root="vendor/source"))
    assert workspace.sources[0].content_revision == vendored.sources[0].content_revision
    assert (
        workspace.sources[0].acquisition_revision
        != vendored.sources[0].acquisition_revision
    )


def test_composite_facet_revision_binds_extension_order() -> None:
    first = _digest("first")
    second = _digest("second")
    assert composite_facet_content_revision(ZERO, (first, second)) != (
        composite_facet_content_revision(ZERO, (second, first))
    )


def test_source_content_revision_rejects_duplicate_paths() -> None:
    lock = parse_acquisition_lock(_lock())
    file = lock.sources[0].files[0]
    with pytest.raises(AcquisitionContractError, match="duplicates") as raised:
        source_content_revision("oikos", (file, file))
    assert raised.value.location == "$.files[1].path"


def test_manifest_locates_reserved_and_duplicate_namespaces() -> None:
    reserved = _manifest()
    reserved["sources"][0]["namespace"] = "eutaxis"  # type: ignore[index]
    with pytest.raises(AcquisitionContractError) as reserved_error:
        parse_acquisition_manifest(reserved)
    assert reserved_error.value.location == "$.sources[0].namespace"

    duplicate = _manifest()
    duplicate["sources"].append(deepcopy(duplicate["sources"][0]))  # type: ignore[union-attr,index]
    with pytest.raises(AcquisitionContractError) as duplicate_error:
        parse_acquisition_manifest(duplicate)
    assert duplicate_error.value.location == "$.sources[1].namespace"

    duplicate_extensions = _manifest()
    duplicate_extensions["facet-extensions"].append(  # type: ignore[union-attr]
        deepcopy(duplicate_extensions["facet-extensions"][0])  # type: ignore[index]
    )
    with pytest.raises(AcquisitionContractError) as extension_error:
        parse_acquisition_manifest(duplicate_extensions)
    assert extension_error.value.location == "$.facet-extensions[1].namespace"

    duplicate_files = _manifest()
    duplicate_files["sources"][0]["files"].append(  # type: ignore[index]
        "declarations/process-core.yaml"
    )
    with pytest.raises(AcquisitionContractError) as file_error:
        parse_acquisition_manifest(duplicate_files)
    assert file_error.value.location == "$.sources[0].files[1]"


def test_lock_locates_duplicate_namespaces_and_paths() -> None:
    duplicate_sources = _lock()
    duplicate_sources["sources"].append(  # type: ignore[union-attr]
        deepcopy(duplicate_sources["sources"][0])  # type: ignore[index]
    )
    with pytest.raises(AcquisitionContractError) as source_error:
        parse_acquisition_lock(duplicate_sources)
    assert source_error.value.location == "$.sources[1].namespace"

    duplicate_extensions = _lock()
    registry = duplicate_extensions["facet-registry"]
    registry["extensions"].append(deepcopy(registry["extensions"][0]))  # type: ignore[index]
    with pytest.raises(AcquisitionContractError) as extension_error:
        parse_acquisition_lock(duplicate_extensions)
    assert extension_error.value.location == "$.facet-registry.extensions[1].namespace"

    duplicate_paths = _lock()
    files = duplicate_paths["sources"][0]["files"]  # type: ignore[index]
    files.append(deepcopy(files[0]))
    with pytest.raises(AcquisitionContractError) as path_error:
        parse_acquisition_lock(duplicate_paths)
    assert path_error.value.location == "$.sources[0].files[1].path"


def test_source_content_revision_rejects_empty_source() -> None:
    with pytest.raises(AcquisitionContractError, match="non-empty"):
        source_content_revision("oikos", ())


@pytest.mark.parametrize("factory", [_manifest, _lock])
def test_direct_documents_reject_lone_surrogates_at_their_location(factory) -> None:
    document = factory()
    document["sources"][0]["namespace"] = "bad\ud800"  # type: ignore[index]
    parser = (
        parse_acquisition_manifest if factory is _manifest else parse_acquisition_lock
    )
    with pytest.raises(
        AcquisitionContractError,
        match=r"\$\.sources\[0\]\.namespace.*lone surrogate",
    ):
        parser(document)


@pytest.mark.parametrize("factory", [_manifest, _lock])
def test_direct_documents_reject_cyclic_aliases_at_their_location(factory) -> None:
    document = factory()
    sources = document["sources"]
    sources.append(sources)  # type: ignore[union-attr]
    parser = (
        parse_acquisition_manifest if factory is _manifest else parse_acquisition_lock
    )
    with pytest.raises(AcquisitionContractError, match="cyclic JSON containers"):
        parser(document)


def test_direct_documents_allow_shared_acyclic_values() -> None:
    document = _manifest()
    shared_files = ["declarations/process-core.yaml"]
    document["sources"][0]["files"] = shared_files  # type: ignore[index]
    document["sources"].append(  # type: ignore[union-attr]
        {
            "namespace": "other",
            "kind": "workspace",
            "root": "other",
            "files": shared_files,
        }
    )
    manifest = parse_acquisition_manifest(document)
    assert manifest.sources[0].files == manifest.sources[1].files


def test_public_revision_apis_reject_surrogate_paths_with_acquisition_errors() -> None:
    bad_path = "bad\ud800"
    digest = _digest("carrier")
    with pytest.raises(AcquisitionContractError) as source_error:
        source_content_revision("oikos", (LockedFile(bad_path, digest),))
    assert source_error.value.location == "$.files[0].path"
    with pytest.raises(AcquisitionContractError) as facet_error:
        facet_content_revision(
            "oikos/context-facets", "oikos", "oikos", bad_path, digest
        )
    assert facet_error.value.location == "$.path"
