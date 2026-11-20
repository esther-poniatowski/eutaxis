"""Prepare a draft initial declaration release from staged compiler outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from jsonschema.exceptions import ValidationError

from eutaxis.commands.exceptions import CommandError
from eutaxis.commands.synchronization import _atomic_rename_noreplace
from eutaxis.declarations.acquisition_paths import normalized_relative_path
from eutaxis.declarations.byte_carriers import (
    AuthoritativeByteCarrier,
    RetainedDirectory,
    _trusted_directory_from_workspace_path,
)
from eutaxis.declarations.canonical_json import _unique_object, jcs_bytes
from eutaxis.declarations.exceptions import (
    AcquisitionContractError,
    ByteCarrierError,
    DeclarationError,
    FacetRegistryError,
)
from eutaxis.declarations.external_result import (
    _issued_external_result_state,
    open_external_declaration_acquisition_from_path,
)
from eutaxis.declarations.markdown_projection import _thaw_json
from eutaxis.declarations.semantic_comparison import _key_order, _semantic_objects

from .verify_release_capsule import _digest, _locked_workspace_files, verify_bundle


class _Snapshot:
    """Read named files once and confirm they stayed stable through capture."""

    def __init__(self, directory: RetainedDirectory) -> None:
        """Retain the input directory used by each file observation."""
        self.directory = directory
        self.observations: dict[str, AuthoritativeByteCarrier] = {}

    def read(self, path: object) -> bytes:
        """Return exact bytes at a normalized, non-symlink coordinate."""
        relative = normalized_relative_path(path, allow_dot=False)
        if relative not in self.observations:
            self.observations[relative] = self.directory.read_authoritative(relative)
        return self.observations[relative].data

    def verify(self) -> None:
        """Check each collected file after the final input read."""
        for observation in self.observations.values():
            self.directory.verify(observation)


class _BlobWriter:
    """Write each distinct byte sequence once in a private bundle directory."""

    def __init__(self, bundle: Path) -> None:
        """Create the empty content-addressed store."""
        self.directory = bundle / "blobs" / "sha256"
        self.directory.mkdir(parents=True)

    def put(self, content: bytes) -> str:
        """Store a payload and return its draft SHA-256 address."""
        address = _digest(content)
        path = self.directory / address.removeprefix("sha256:")
        try:
            with path.open("xb") as stream:
                stream.write(content)
        except FileExistsError:
            if path.read_bytes() != content:
                raise ValueError(f"Different bytes share the address {address}")
        return address

    def record(self, value: object) -> str:
        """Store a canonical JSON record."""
        return self.put(jcs_bytes(value))


def _read_target_map(
    snapshot: _Snapshot, writer: _BlobWriter, paths: object, *, baseline: bool
) -> dict[str, str | None]:
    """Bind each logical target to its staged bytes or recorded absence."""
    if not isinstance(paths, dict):
        raise ValueError("Target maps must be JSON objects")
    targets: dict[str, str | None] = {}
    for name, path in paths.items():
        target = normalized_relative_path(name, allow_dot=False)
        targets[target] = (
            None if path is None and baseline else writer.put(snapshot.read(path))
        )
    return targets


def _read_review_inputs(
    plan: Path, writer: _BlobWriter
) -> tuple[dict[str, str | None], dict[str, str | None], str | None, str]:
    """Capture the explicit compiler outputs, baseline, ledger and distribution."""
    with _trusted_directory_from_workspace_path(str(plan.parent)) as root:
        with root.retain_directory(".") as directory:
            snapshot = _Snapshot(directory)
            values = json.loads(
                snapshot.read(plan.name), object_pairs_hook=_unique_object
            )
            fields = {"outputs", "goldens", "accountability-ledger", "distribution"}
            if not isinstance(values, dict) or values.keys() != fields:
                raise ValueError(
                    "Plan requires outputs, goldens, accountability-ledger and distribution"
                )
            baseline = _read_target_map(
                snapshot, writer, values["goldens"], baseline=True
            )
            outputs = _read_target_map(
                snapshot, writer, values["outputs"], baseline=False
            )
            ledger_path = values["accountability-ledger"]
            ledger = (
                None if ledger_path is None else writer.put(snapshot.read(ledger_path))
            )
            distribution = writer.put(snapshot.read(values["distribution"]))
            snapshot.verify()
    return baseline, outputs, ledger, distribution


def _capture_acquisition(
    workspace: Path,
    manifest: str,
    lock: str,
    distribution: str,
    writer: _BlobWriter,
) -> tuple[dict[str, object], str]:
    """Bind authenticated acquisition bytes and typed semantic objects."""
    with open_external_declaration_acquisition_from_path(
        str(workspace), manifest, lock
    ) as acquisition:
        state = _issued_external_result_state(acquisition)
        evidence = state.evidence_state
        lock_evidence = evidence.lock_evidence
        if lock_evidence is None:
            raise ValueError("Preparation requires an existing acquisition lock")

        coordinates = _locked_workspace_files(acquisition.manifest, acquisition.lock)
        with _trusted_directory_from_workspace_path(str(workspace)) as root:
            if root.identity != evidence.workspace_root_identity:
                raise ValueError("Workspace root changed after acquisition")
            with root.retain_directory(".") as directory:
                snapshot = _Snapshot(directory)
                for path, expected in coordinates.items():
                    content = snapshot.read(path)
                    if _digest(content) != expected:
                        raise ValueError(
                            f"Workspace bytes differ from the lock: {path}"
                        )
                    writer.put(content)
                snapshot.verify()

        objects = _semantic_objects(state)
        semantics = writer.record(
            [
                {
                    "kind": key.object_kind.value,
                    "id": key.id,
                    "version": key.version,
                    "value": _thaw_json(objects[key]),
                }
                for key in sorted(objects, key=_key_order)
            ]
        )
        authorization = {
            "acquisition-manifest": {
                "path": manifest,
                "sha256": writer.put(evidence.manifest_evidence.authoritative.data),
            },
            "acquisition-lock": {
                "path": lock,
                "sha256": writer.put(lock_evidence.authoritative.data),
            },
            "workspace-files": coordinates,
            "packaged-source-revision": acquisition.lock.internal_source.acquisition_revision,
            "distribution-revision": distribution,
        }
    return authorization, semantics


def prepare_bundle(
    workspace: Path, manifest: str, lock: str, plan: Path, bundle: Path
) -> str:
    """Verify and publish a draft bundle at an absent path."""
    workspace = workspace.absolute()
    plan = plan.absolute()
    bundle = bundle.absolute()
    if bundle.exists() or bundle.is_symlink():
        raise FileExistsError(f"Bundle path already exists: {bundle}")

    with TemporaryDirectory(prefix=".eutaxis-release-", dir=bundle.parent) as staging:
        candidate = Path(staging) / "bundle"
        writer = _BlobWriter(candidate)
        baseline, outputs, ledger, distribution = _read_review_inputs(plan, writer)
        authorization, semantics = _capture_acquisition(
            workspace, manifest, lock, distribution, writer
        )
        binding = {
            "_schema": "eutaxis:declaration-release@1",
            "predecessor": None,
            "initial-baseline": {
                "accountability-ledger": ledger,
                "golden-targets": baseline,
            },
            **authorization,
            "managed-targets": dict.fromkeys(baseline) | outputs,
        }
        review = {
            "_schema": "eutaxis:declaration-review@1",
            "candidate-binding": _digest(jcs_bytes(binding)),
            "semantics": {
                "kind": "initial",
                "accountability-ledger": ledger,
                "candidate": semantics,
            },
            "acquisition": {
                "baseline": None,
                "candidate": writer.record(authorization),
            },
            "artifacts": {
                "baseline": writer.record(baseline),
                "candidate": writer.record(outputs),
            },
        }
        address = writer.record({**binding, "review-packet": writer.record(review)})
        verify_bundle(candidate, address)
        _atomic_rename_noreplace(candidate, bundle)
    return address


def main(argv: list[str] | None = None) -> int:
    """Prepare one initial bundle and print its digest to standard output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--manifest", required=True, help="Workspace-relative manifest")
    parser.add_argument("--lock", required=True, help="Workspace-relative lock")
    parser.add_argument(
        "--plan", required=True, type=Path, help="JSON plan beside staged inputs"
    )
    parser.add_argument(
        "--bundle", required=True, type=Path, help="Absent bundle directory"
    )
    args = parser.parse_args(argv)
    try:
        address = prepare_bundle(
            args.workspace, args.manifest, args.lock, args.plan, args.bundle
        )
    except (
        AcquisitionContractError,
        ByteCarrierError,
        CommandError,
        DeclarationError,
        FacetRegistryError,
        OSError,
        ValidationError,
        ValueError,
    ) as error:
        parser.exit(1, f"Preparation failed: {error}\n")
    print(address)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
