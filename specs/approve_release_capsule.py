"""Record or check a draft operator approval for one verified release capsule."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

from jsonschema.exceptions import ValidationError

from eutaxis.declarations._cli import _write_exact_stdout
from eutaxis.declarations.byte_carriers import _trusted_directory_from_workspace_path
from eutaxis.declarations.canonical_json import jcs_bytes
from eutaxis.declarations.exceptions import AcquisitionContractError, ByteCarrierError

from .verify_release_capsule import _load_record, _open_bundle_blobs, verify_capsule


@dataclass(frozen=True)
class ExpectedActive:
    """Name the active record and release, or an empty release history."""

    record: int | None
    release: str | None

    def __post_init__(self) -> None:
        """Require an empty history or a complete active-state pair."""
        if self.record is None and self.release is None:
            return
        if type(self.record) is not int or not 0 <= self.record:
            raise ValueError("Expected active record must be a non-negative integer")
        if type(self.release) is not str or not re.fullmatch(
            r"sha256:[0-9a-f]{64}", self.release
        ):
            raise ValueError("Expected active release must be a SHA-256 capsule digest")


def approval_bytes(bundle: Path, address: str, expected: ExpectedActive) -> bytes:
    """Return the exact operator approval for one verified forward release."""
    with _open_bundle_blobs(bundle) as blobs:
        verify_capsule(blobs, address)
        capsule = _load_record(blobs, address, "release")
        if capsule["predecessor"] != expected.release:
            raise ValueError(
                "Capsule predecessor differs from the expected active release"
            )
        blobs.verify()

    return jcs_bytes(
        {
            "_schema": "eutaxis:declaration-approval@1",
            "capsule": address,
            "review-packet": capsule["review-packet"],
            "expected-record": expected.record,
            "expected-active": expected.release,
        }
    )


def verify_approval(
    bundle: Path, address: str, expected: ExpectedActive, approved: bytes
) -> None:
    """Require exact approval bytes from the operator's trusted review record."""
    if approved != approval_bytes(bundle, address, expected):
        raise ValueError(
            "Approval does not match the capsule, review, or expected active record"
        )


def _check_approval_file(
    path: Path, bundle: Path, address: str, expected: ExpectedActive
) -> None:
    """Verify a retained approval file without following a symlink."""
    path = path.absolute()
    with _trusted_directory_from_workspace_path(str(path.parent)) as parent:
        with parent.retain_directory(".") as directory:
            approved = directory.read_authoritative(path.name)
            verify_approval(bundle, address, expected, approved.data)
            directory.verify(approved)


def main(argv: list[str] | None = None) -> int:
    """Emit canonical approval bytes or check a saved approval."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("address", help="Exact capsule digest reviewed by the operator")
    parser.add_argument(
        "--expect-empty", action="store_true", help="Expect no active release"
    )
    parser.add_argument(
        "--expect-record", type=int, help="Expected active record number"
    )
    parser.add_argument("--expect-active", help="Expected active capsule digest")
    parser.add_argument("--check", type=Path, help="Saved operator approval to check")
    args = parser.parse_args(argv)
    if args.expect_empty:
        if args.expect_record is not None or args.expect_active is not None:
            parser.error(
                "--expect-empty cannot be combined with an active record or release"
            )
    elif args.expect_record is None or args.expect_active is None:
        parser.error(
            "Supply --expect-empty or both --expect-record and --expect-active"
        )

    try:
        expected = ExpectedActive(args.expect_record, args.expect_active)
        if args.check is None:
            _write_exact_stdout(approval_bytes(args.bundle, args.address, expected))
        else:
            _check_approval_file(args.check, args.bundle, args.address, expected)
            print(f"Verified approval for {args.address}")
    except (
        AcquisitionContractError,
        ByteCarrierError,
        OSError,
        ValidationError,
        ValueError,
    ) as error:
        parser.exit(1, f"Approval failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
