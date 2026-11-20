"""Exercise complete initial and successor bundles against the draft verifier."""

import hashlib

import pytest

from eutaxis.declarations.canonical_json import jcs_bytes
from specs.verify_release_capsule import ACQUISITION_FIELDS, verify_capsule


def _store(blobs: dict[str, bytes], content: bytes) -> str:
    """Add one content-addressed fixture."""
    address = "sha256:" + hashlib.sha256(content).hexdigest()
    blobs[address] = content
    return address


def _release(
    blobs: dict[str, bytes],
    *,
    prior: tuple[str, str, str] | None = None,
    omit_retired: bool = False,
    change_after_review: bool = False,
) -> tuple[str, str, str]:
    """Build a complete candidate and its review in the fixture store."""
    initial = prior is None
    predecessor, prior_semantics, prior_acquisition = prior or (None, None, None)
    old = {"host/old.md": _store(blobs, b"old instructions")}
    new = {"host/new.md": _store(blobs, b"new instructions")}
    outputs = old if initial else new
    ledger = _store(blobs, b"legacy ledger")
    semantics = _store(blobs, jcs_bytes({"declarations": ["example/rule"]}))
    capsule = {
        "_schema": "eutaxis:declaration-release@1",
        "predecessor": predecessor,
        "initial-baseline": (
            {"accountability-ledger": ledger, "golden-targets": old}
            if initial
            else None
        ),
        "acquisition-manifest": {
            "path": "declarations/acquisition.yaml",
            "sha256": _store(blobs, b"manifest"),
        },
        "acquisition-lock": {
            "path": "declarations/acquisition.lock.json",
            "sha256": _store(blobs, b"canonical lock"),
        },
        "workspace-files": {"declarations/rules.yaml": _store(blobs, b"rule source")},
        "packaged-source-revision": _store(blobs, b"packaged sources"),
        "distribution-revision": _store(blobs, b"distribution"),
        "managed-targets": (
            outputs if initial or omit_retired else {"host/old.md": None, **outputs}
        ),
    }
    authorization = _store(
        blobs, jcs_bytes({field: capsule[field] for field in ACQUISITION_FIELDS})
    )
    review = {
        "_schema": "eutaxis:declaration-review@1",
        "candidate-binding": _store(blobs, jcs_bytes(capsule)),
        "semantics": (
            {"kind": "initial", "accountability-ledger": ledger, "candidate": semantics}
            if initial
            else {
                "kind": "successor",
                "baseline": prior_semantics,
                "candidate": semantics,
                "differences": _store(blobs, jcs_bytes([])),
            }
        ),
        "acquisition": {
            "baseline": prior_acquisition,
            "candidate": authorization,
        },
        "artifacts": {
            "baseline": _store(blobs, jcs_bytes(old)),
            "candidate": _store(blobs, jcs_bytes(outputs)),
        },
    }
    capsule["review-packet"] = _store(blobs, jcs_bytes(review))
    if change_after_review:
        capsule["distribution-revision"] = _store(blobs, b"changed distribution")
    return _store(blobs, jcs_bytes(capsule)), semantics, authorization


def test_verifies_initial_and_successor_without_writes() -> None:
    blobs: dict[str, bytes] = {}
    initial = _release(blobs)
    successor = _release(blobs, prior=initial)
    snapshot = blobs.copy()
    verify_capsule(blobs, initial[0])
    verify_capsule(blobs, successor[0])
    assert blobs == snapshot


@pytest.mark.parametrize(
    "original", [b"rule source", b"canonical lock", b"old instructions"]
)
def test_rejects_altered_payload(original: bytes) -> None:
    blobs: dict[str, bytes] = {}
    initial = _release(blobs)
    address = _store(blobs, original)
    blobs[address] = b"changed"
    with pytest.raises(ValueError, match="Stored bytes differ"):
        verify_capsule(blobs, initial[0])


def test_rejects_omitted_retired_target_even_with_valid_digests() -> None:
    blobs: dict[str, bytes] = {}
    initial = _release(blobs)
    successor = _release(blobs, prior=initial, omit_retired=True)
    with pytest.raises(ValueError, match="include every prior and candidate target"):
        verify_capsule(blobs, successor[0])


def test_rejects_capsule_changed_after_review() -> None:
    blobs: dict[str, bytes] = {}
    capsule = _release(blobs, change_after_review=True)
    with pytest.raises(ValueError, match="Review does not bind"):
        verify_capsule(blobs, capsule[0])
