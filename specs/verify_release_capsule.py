"""Verify the draft release records against a read-only byte store."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from eutaxis.declarations.acquisition_contract import (
    AcquisitionKind,
    AcquisitionLock,
    AcquisitionManifest,
    _parse_acquisition_manifest_bytes,
    parse_acquisition_lock_bytes,
    validate_acquisition_contract,
)
from eutaxis.declarations.acquisition_paths import normalized_relative_path
from eutaxis.declarations.byte_carriers import (
    AuthoritativeByteCarrier,
    RetainedDirectory,
    _trusted_directory_from_workspace_path,
)
from eutaxis.declarations.canonical_json import jcs_bytes, parse_canonical_json_bytes
from eutaxis.declarations.exceptions import AcquisitionContractError, ByteCarrierError

from .release_semantics import encode_differences

ACQUISITION_FIELDS = (
    "acquisition-manifest",
    "acquisition-lock",
    "workspace-files",
    "packaged-source-revision",
    "distribution-revision",
)


class ByteStore(Protocol):
    """Read a blob by its content address."""

    def __getitem__(self, address: str) -> bytes:
        """Return the bytes stored under the address."""


class _BundleBlobs:
    """Read digest-named files through a retained directory descriptor."""

    def __init__(self, directory: RetainedDirectory) -> None:
        """Start one observation of the bundle."""
        self._directory = directory
        self._observations: dict[str, AuthoritativeByteCarrier] = {}

    def __getitem__(self, address: str) -> bytes:
        """Read each referenced blob once before the final verification pass."""
        match = re.fullmatch(r"sha256:([0-9a-f]{64})", address)
        if match is None:
            raise ValueError(f"Invalid blob address: {address!r}")
        if address not in self._observations:
            observation = self._directory.read_optional_authoritative(match[1])
            if observation is None:
                raise KeyError(address)
            self._observations[address] = observation
        return self._observations[address].data

    def verify(self) -> None:
        """Reopen each referenced blob and verify the retained observation."""
        for observation in self._observations.values():
            self._directory.verify(observation)

    def observed_bytes(self) -> Iterator[bytes]:
        """Yield only the blobs reached by the verification pass."""
        return (observation.data for observation in self._observations.values())


def _digest(content: bytes) -> str:
    """Address one exact byte sequence."""
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _read(blobs: ByteStore, address: str) -> bytes:
    """Read bytes and check their address."""
    try:
        content = blobs[address]
    except KeyError as error:
        raise ValueError(f"Missing stored bytes for {address}") from error
    if type(content) is not bytes or _digest(content) != address:
        raise ValueError(f"Stored bytes differ from {address}")
    return content


def _object(content: bytes) -> dict[str, Any]:
    """Require a canonical JSON object."""
    value = parse_canonical_json_bytes(content)
    if not isinstance(value, dict):
        raise ValueError("Expected a canonical JSON object")
    return value


def _load_record(blobs: ByteStore, address: str, record: str) -> dict[str, Any]:
    """Validate a content-addressed draft record."""
    name = f"declaration-{record}-v1.draft.schema.json"
    schema = json.loads(Path(__file__).with_name(name).read_text(encoding="utf-8"))
    value = _object(_read(blobs, address))
    Draft202012Validator(schema).validate(value)
    return value


def _read_targets(
    blobs: ByteStore, address: str, *, require_present: bool
) -> dict[str, str | None]:
    """Verify target names and each present artifact reference."""
    targets = _object(_read(blobs, address))
    for target, state in targets.items():
        normalized_relative_path(target, allow_dot=False)
        if isinstance(state, str):
            _read(blobs, state)
        elif state is not None or require_present:
            raise ValueError(f"Invalid artifact state for {target}")
    return targets


def _verify_acquisition(
    blobs: ByteStore, capsule: dict[str, Any], address: str
) -> None:
    """Bind the reviewed acquisition record to the capsule and its bytes."""
    authorization = {field: capsule[field] for field in ACQUISITION_FIELDS}
    if _read(blobs, address) != jcs_bytes(authorization):
        raise ValueError("Review acquisition does not bind the capsule sources")
    manifest_entry = capsule["acquisition-manifest"]
    manifest_path = normalized_relative_path(manifest_entry["path"], allow_dot=False)
    manifest = _parse_acquisition_manifest_bytes(
        _read(blobs, manifest_entry["sha256"]), path=Path(manifest_path)
    )
    lock_entry = capsule["acquisition-lock"]
    normalized_relative_path(lock_entry["path"], allow_dot=False)
    lock = parse_acquisition_lock_bytes(_read(blobs, lock_entry["sha256"]))
    validate_acquisition_contract(manifest, lock)
    if capsule["packaged-source-revision"] != lock.internal_source.acquisition_revision:
        raise ValueError("Packaged source revision differs from the acquisition lock")
    expected_files = _locked_workspace_files(manifest, lock)
    if capsule["workspace-files"] != expected_files:
        raise ValueError("Workspace files differ from the acquisition lock")
    for digest in expected_files.values():
        _read(blobs, digest)


def _locked_workspace_files(
    manifest: AcquisitionManifest, lock: AcquisitionLock
) -> dict[str, str]:
    """Map the locked workspace declarations, resources, and facets to blobs."""
    files: dict[str, str] = {}

    def bind(root: str, path: str, digest: str) -> None:
        """Reject incompatible bindings for the same workspace path."""
        coordinate = (PurePosixPath(root) / path).as_posix()
        if files.setdefault(coordinate, digest) != digest:
            raise ValueError(f"Conflicting locked workspace bytes for {coordinate}")

    for source, locked in zip(manifest.sources, lock.sources, strict=True):
        if source.kind is not AcquisitionKind.WORKSPACE:
            raise ValueError(f"Unsupported source kind in release: {source.kind}")
        for item in (*locked.files, *locked.resources):
            bind(source.root, item.path, item.sha256)
    for extension, locked in zip(
        manifest.facet_extensions, lock.facet_registry.extensions, strict=True
    ):
        bind(extension.root, locked.path, locked.sha256)
    return files


def _verify_review_binding(blobs: ByteStore, capsule: dict[str, Any]) -> dict[str, Any]:
    """Verify the review against the capsule without its review digest."""
    review = _load_record(blobs, capsule["review-packet"], "review")
    binding = {key: value for key, value in capsule.items() if key != "review-packet"}
    if _digest(jcs_bytes(binding)) != review["candidate-binding"]:
        raise ValueError("Review does not bind the candidate capsule")
    return review


def verify_capsule(blobs: ByteStore, address: str) -> None:
    """Check each release from the selected capsule to its initial baseline.

    The caller supplies the reviewed capsule address and a read-only byte store.
    """
    capsule = _load_record(blobs, address, "release")
    review = _verify_review_binding(blobs, capsule)
    seen = {address}
    while (predecessor := capsule["predecessor"]) is not None:
        if predecessor in seen:
            raise ValueError("Release history contains a cycle")
        seen.add(predecessor)
        prior_capsule = _load_record(blobs, predecessor, "release")
        prior_review = _verify_review_binding(blobs, prior_capsule)
        _verify_release(blobs, capsule, review, (prior_capsule, prior_review))
        capsule, review = prior_capsule, prior_review
    _verify_release(blobs, capsule, review, None)


def _verify_release(
    blobs: ByteStore,
    capsule: dict[str, Any],
    review: dict[str, Any],
    prior: tuple[dict[str, Any], dict[str, Any]] | None,
) -> None:
    """Verify one release and its reviewed relation to the preceding release."""
    semantics = review["semantics"]
    acquisition = review["acquisition"]
    artifacts = review["artifacts"]
    _verify_acquisition(blobs, capsule, acquisition["candidate"])
    distribution = capsule["distribution-revision"]
    try:
        distribution_bytes = blobs[distribution]
    except KeyError:
        pass  # Early draft bundles may store the revision without an archive.
    else:
        if _digest(distribution_bytes) != distribution:
            raise ValueError(f"Stored bytes differ from {distribution}")
    candidate_semantics = _read(blobs, semantics["candidate"])
    baseline = _read_targets(blobs, artifacts["baseline"], require_present=False)
    outputs = _read_targets(blobs, artifacts["candidate"], require_present=True)
    if prior is None:
        initial = capsule["initial-baseline"]
        if semantics["kind"] != "initial" or (
            semantics["accountability-ledger"] != initial["accountability-ledger"]
        ):
            raise ValueError("Review does not bind the initial accountability ledger")
        if baseline != initial["golden-targets"]:
            raise ValueError("Review does not bind the golden baseline targets")
        if semantics["accountability-ledger"] is not None:
            _read(blobs, semantics["accountability-ledger"])
    else:
        prior_capsule, prior_review = prior
        if semantics["kind"] != "successor" or (
            semantics["baseline"] != prior_review["semantics"]["candidate"]
        ):
            raise ValueError("Review does not bind predecessor semantics")
        if acquisition["baseline"] != prior_review["acquisition"]["candidate"]:
            raise ValueError("Review does not bind predecessor acquisition")
        if baseline != prior_capsule["managed-targets"]:
            raise ValueError("Review does not bind predecessor targets")
        baseline_semantics = _read(blobs, semantics["baseline"])
        differences = _read(blobs, semantics["differences"])
        if differences != encode_differences(baseline_semantics, candidate_semantics):
            raise ValueError("Review differences do not match the semantic snapshots")
    if acquisition["baseline"] is not None:
        _read(blobs, acquisition["baseline"])
    expected_targets = dict.fromkeys(baseline) | outputs
    if capsule["managed-targets"] != expected_targets:
        raise ValueError(
            "Managed targets must include every prior and candidate target"
        )


@contextmanager
def _open_bundle_blobs(bundle: Path) -> Iterator[_BundleBlobs]:
    """Retain the bundle blob directory for an observation."""
    bundle = bundle.absolute()
    blob_path = (Path(bundle.name) / "blobs" / "sha256").as_posix()
    with _trusted_directory_from_workspace_path(str(bundle.parent)) as parent:
        with parent.retain_directory(blob_path) as directory:
            yield _BundleBlobs(directory)


def verify_bundle(bundle: Path, address: str) -> None:
    """Verify one capsule stored below the bundle’s blob directory."""
    with _open_bundle_blobs(bundle) as blobs:
        verify_capsule(blobs, address)
        blobs.verify()


def main(argv: list[str] | None = None) -> int:
    """Run the read-only draft verifier on one bundle."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("address", help="Reviewed capsule digest")
    args = parser.parse_args(argv)
    try:
        verify_bundle(args.bundle, args.address)
    except (
        AcquisitionContractError,
        ByteCarrierError,
        OSError,
        ValidationError,
        ValueError,
    ) as error:
        parser.exit(1, f"Verification failed: {error}\n")
    print(f"Verified capsule {args.address}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
