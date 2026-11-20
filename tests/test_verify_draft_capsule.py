"""Exercise complete initial and successor bundles against the draft verifier."""

import hashlib
from pathlib import Path

import pytest

from eutaxis.declarations.exceptions import ByteCarrierError
from eutaxis.declarations.canonical_json import jcs_bytes
from specs import verify_release_capsule
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


def _write_bundle(root: Path) -> tuple[str, Path]:
    """Materialize a valid fixture and return its capsule and source blob."""
    blobs: dict[str, bytes] = {}
    initial = _release(blobs)
    address = _release(blobs, prior=initial)[0]
    source = _store(blobs, b"rule source")
    blob_dir = root / "blobs" / "sha256"
    blob_dir.mkdir(parents=True)
    for digest, content in blobs.items():
        (blob_dir / digest.removeprefix("sha256:")).write_bytes(content)
    return address, blob_dir / source.removeprefix("sha256:")


def test_bundle_command_verifies_files_without_writing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    address, blob = _write_bundle(tmp_path)
    contents = {file.name: file.read_bytes() for file in blob.parent.iterdir()}
    assert verify_release_capsule.main([str(tmp_path), address]) == 0
    assert capsys.readouterr().out == f"Verified capsule {address}\n"
    assert {file.name: file.read_bytes() for file in blob.parent.iterdir()} == contents


def test_bundle_rejects_symlink_to_matching_bytes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    address, blob = _write_bundle(tmp_path)
    content = tmp_path / "outside-blob-store"
    blob.rename(content)
    blob.symlink_to(content)
    with pytest.raises(SystemExit) as error:
        verify_release_capsule.main([str(tmp_path), address])
    assert error.value.code == 1
    assert "Verification failed: Invalid byte carrier" in capsys.readouterr().err


def test_bundle_rejects_changed_blob_after_first_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    address, blob = _write_bundle(tmp_path)

    def change_before_recheck(store, digest):
        verify_capsule(store, digest)
        blob.write_bytes(b"changed source")

    monkeypatch.setattr(verify_release_capsule, "verify_capsule", change_before_recheck)
    with pytest.raises(ByteCarrierError):
        verify_release_capsule.verify_bundle(tmp_path, address)
