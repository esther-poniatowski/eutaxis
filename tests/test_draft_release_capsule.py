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


def _draft_verifier(name: str) -> Draft202012Validator:
    """Check a draft schema before applying it to records."""
    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / "specs" / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.fixture
def verifier() -> Draft202012Validator:
    return _draft_verifier("declaration-release-v1.draft.schema.json")


@pytest.fixture
def review_verifier() -> Draft202012Validator:
    return _draft_verifier("declaration-review-v1.draft.schema.json")


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


@pytest.fixture
def initial_review() -> dict[str, object]:
    """Model the independent evidence required for a first release."""
    return {
        "_schema": "eutaxis:declaration-review@1",
        "candidate-binding": _digest(b"candidate projection"),
        "semantics": {
            "kind": "initial",
            "accountability-ledger": _digest(b"legacy ledger"),
            "candidate": _digest(b"candidate declarations"),
        },
        "acquisition": {"baseline": None, "candidate": _digest(b"authorization")},
        "artifacts": {
            "baseline": _digest(b"golden target map"),
            "candidate": _digest(b"candidate target map"),
        },
    }


def test_review_binds_capsule_without_a_digest_cycle(
    verifier: Draft202012Validator,
    review_verifier: Draft202012Validator,
    initial_capsule: dict[str, object],
    initial_review: dict[str, object],
) -> None:
    candidate = dict(initial_capsule)
    del candidate["review-packet"]
    candidate_binding = _digest(jcs_bytes(candidate))
    review = {**initial_review, "candidate-binding": candidate_binding}
    review_bytes = jcs_bytes(review)
    final_capsule = {**candidate, "review-packet": _digest(review_bytes)}

    review_verifier.validate(parse_canonical_json_bytes(review_bytes))
    verifier.validate(parse_canonical_json_bytes(jcs_bytes(final_capsule)))
    for changed in (
        {
            **candidate,
            "acquisition-lock": {
                "path": "declarations/acquisition.lock.json",
                "sha256": _digest(b"different lock"),
            },
        },
        {**candidate, "managed-targets": {"host/instructions.md": None}},
    ):
        verifier.validate({**changed, "review-packet": _digest(review_bytes)})
        assert _digest(jcs_bytes(changed)) != candidate_binding


def test_successor_review_keeps_changes_independent(
    review_verifier: Draft202012Validator, initial_review: dict[str, object]
) -> None:
    same_semantics = _digest(b"same declarations")
    successor = {
        **initial_review,
        "semantics": {
            "kind": "successor",
            "baseline": same_semantics,
            "candidate": same_semantics,
            "differences": _digest(jcs_bytes([])),
        },
        "acquisition": {
            "baseline": _digest(b"prior authorization"),
            "candidate": _digest(b"next authorization"),
        },
    }
    review_verifier.validate(successor)
    assert not review_verifier.is_valid(
        {
            **successor,
            "acquisition": {"baseline": None, "candidate": _digest(b"authorization")},
        }
    )


@pytest.mark.parametrize("missing", ["semantics", "acquisition", "artifacts"])
def test_review_requires_all_three_comparisons(
    review_verifier: Draft202012Validator,
    initial_review: dict[str, object],
    missing: str,
) -> None:
    del initial_review[missing]
    assert not review_verifier.is_valid(initial_review)
