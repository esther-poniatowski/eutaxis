"""Build the exact packaged composite authority for declaration tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

from eutaxis import data_path
from eutaxis.declarations import (
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
from eutaxis.declarations.acquisition_contract import (
    PACKAGED_DECLARATION_PATHS,
    PACKAGED_FACET_PATH,
)
from eutaxis.declarations.canonical_json import jcs_bytes
from eutaxis.declarations.composite_facets import (
    CompositeFacetRegistry,
    acquire_packaged_composite_facet_registry,
)
from eutaxis.declarations.packaged_source import (
    PackagedInternalSource,
    acquire_packaged_internal_source,
)


def _revision(value: object) -> str:
    return "sha256:" + hashlib.sha256(jcs_bytes(value)).hexdigest()


def _digest_path(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def packaged_lock() -> AcquisitionLock:
    """Return the exact canonical lock for the running package."""
    root = data_path()
    facet_sha = _digest_path(root / PACKAGED_FACET_PATH)
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
        LockedFile(path, _digest_path(root / "declarations" / "v1" / path))
        for path in PACKAGED_DECLARATION_PATHS
    )
    internal_content = source_content_revision("eutaxis", files)
    internal = InternalSourceLock(
        _revision(
            {
                "schema-version": 1,
                "namespace": "eutaxis",
                "kind": "packaged",
                "distribution": "eutaxis",
                "resource-root": "data/declarations/v1",
                "content-revision": internal_content,
            }
        ),
        internal_content,
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


def packaged_source() -> PackagedInternalSource:
    """Acquire the running package through its exact canonical lock."""
    return acquire_packaged_internal_source(packaged_lock())


def issue_test_composite() -> CompositeFacetRegistry:
    """Issue one test composite from the verified packaged facet base."""
    return acquire_packaged_composite_facet_registry(packaged_lock())
