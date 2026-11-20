"""Exercise the draft capsule shape before it becomes a runtime contract."""

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from eutaxis.declarations.canonical_json import jcs_bytes, parse_canonical_json_bytes


def _digest(content: bytes) -> str:
    """Return the address of one byte sequence."""
    return "sha256:" + hashlib.sha256(content).hexdigest()


@pytest.fixture
def verifier() -> Draft202012Validator:
    """Check the draft schema before applying it to records."""
    root = Path(__file__).resolve().parents[1]
    schema = json.loads(
        (root / "specs" / "declaration-release-v1.draft.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.fixture
def initial_capsule() -> dict[str, object]:
    """Model a first release that replaces an existing output."""
    return {
        "_schema": "eutaxis:declaration-release@1",
        "predecessor": None,
        "initial-baseline": {
            "accountability-ledger": _digest(b"legacy ledger"),
            "golden-targets": {"host/instructions.md": _digest(b"legacy instructions")},
        },
        "acquisition-manifest": {
            "path": "declarations/acquisition.yaml",
            "sha256": _digest(b"manifest"),
        },
        "acquisition-lock": {
            "path": "declarations/acquisition.lock.json",
            "sha256": _digest(b"lock"),
        },
        "workspace-files": {"declarations/rules.yaml": _digest(b"rules")},
        "packaged-source-revision": _digest(b"packaged sources"),
        "distribution-revision": _digest(b"distribution"),
        "review-packet": _digest(b"initial review"),
        "managed-targets": {"host/instructions.md": _digest(b"new instructions")},
    }


def test_initial_and_successor_capsules_admit_exact_bytes(
    verifier: Draft202012Validator, initial_capsule: dict[str, object]
) -> None:
    initial_bytes = jcs_bytes(initial_capsule)
    verifier.validate(parse_canonical_json_bytes(initial_bytes))
    successor = {
        **initial_capsule,
        "predecessor": _digest(initial_bytes),
        "initial-baseline": None,
        "review-packet": _digest(b"successor review"),
        "managed-targets": {
            "host/instructions.md": None,
            "host/project.md": _digest(b""),
        },
    }
    verifier.validate(parse_canonical_json_bytes(jcs_bytes(successor)))


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("initial-baseline", None),
        ("predecessor", _digest(b"unexpected predecessor")),
        ("workspace-files", {"declarations/rules.yaml": None}),
        ("managed-targets", {"host/instructions.md": ""}),
        ("review-packet", "sha256:" + "a" * 63 + "\n"),
        ("runtime-authority", {}),
    ],
)
def test_capsule_rejects_invalid_record_fields(
    verifier: Draft202012Validator,
    initial_capsule: dict[str, object],
    field: str,
    invalid: object,
) -> None:
    assert not verifier.is_valid({**initial_capsule, field: invalid})
