"""Check that operator approval binds a verified capsule and its active state."""

from pathlib import Path

import pytest

from eutaxis.declarations.canonical_json import parse_canonical_json_bytes
from specs.approve_release_capsule import (
    ExpectedActive,
    approval_bytes,
    main,
    verify_approval,
)
from tests.test_verify_draft_capsule import Snapshot, _release, acquisition

ReleaseChain = tuple[Path, str, str, str]


@pytest.fixture
def chain(tmp_path: Path, acquisition: Snapshot) -> ReleaseChain:
    """Store an initial release and two distinct successors of it."""
    blobs: dict[str, bytes] = {}
    initial = _release(blobs, acquisition)
    first = _release(blobs, acquisition, prior=initial)
    other = _release(blobs, acquisition, prior=initial, successor_output=b"other")
    store = tmp_path / "bundle" / "blobs" / "sha256"
    store.mkdir(parents=True)
    for address, content in blobs.items():
        (store / address.removeprefix("sha256:")).write_bytes(content)
    return tmp_path / "bundle", initial[0], first[0], other[0]


@pytest.mark.parametrize("initial_release", [True, False])
def test_issue_and_check(
    chain: ReleaseChain,
    tmp_path: Path,
    capsysbinary: pytest.CaptureFixture[bytes],
    initial_release: bool,
) -> None:
    bundle, initial, first, _ = chain
    if initial_release:
        address, flags = initial, ["--expect-empty"]
    else:
        address, flags = first, ["--expect-record", "0", "--expect-active", initial]

    args = [str(bundle), address, *flags]
    assert main(args) == 0
    issued = capsysbinary.readouterr().out
    record = parse_canonical_json_bytes(issued)
    assert isinstance(record, dict)
    assert record["_schema"] == "eutaxis:declaration-approval@1"
    assert record["capsule"] == address
    assert record["expected-active"] == (None if initial_release else initial)
    assert record["expected-record"] == (None if initial_release else 0)
    store = bundle / "blobs" / "sha256"
    capsule = parse_canonical_json_bytes(
        (store / address.removeprefix("sha256:")).read_bytes()
    )
    assert isinstance(capsule, dict)
    assert record["review-packet"] == capsule["review-packet"]

    approval = tmp_path / "approval.json"
    approval.write_bytes(issued)
    assert main([*args, "--check", str(approval)]) == 0
    assert b"Verified approval" in capsysbinary.readouterr().out
    assert approval.read_bytes() == issued


def test_rejects_approval_for_sibling_or_stale_record(chain: ReleaseChain) -> None:
    bundle, initial, first, other = chain
    expected = ExpectedActive(0, initial)
    issued = approval_bytes(bundle, first, expected)

    with pytest.raises(ValueError, match="Approval does not match"):
        verify_approval(bundle, other, expected, issued)
    with pytest.raises(ValueError, match="Approval does not match"):
        verify_approval(bundle, first, ExpectedActive(1, initial), issued)
    with pytest.raises(ValueError, match="predecessor differs"):
        verify_approval(bundle, first, ExpectedActive(1, other), issued)
    with pytest.raises(ValueError, match="Approval does not match"):
        verify_approval(bundle, first, expected, issued + b"\n")


def test_rejects_damaged_candidate_without_emitting_approval(
    chain: ReleaseChain, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    bundle, initial, first, _ = chain
    blob = bundle / "blobs" / "sha256" / first.removeprefix("sha256:")
    blob.write_bytes(blob.read_bytes() + b"\n")
    with pytest.raises(SystemExit) as error:
        main([str(bundle), first, "--expect-record", "0", "--expect-active", initial])
    assert error.value.code == 1
    captured = capsysbinary.readouterr()
    assert captured.out == b""
    assert b"Stored bytes differ" in captured.err


@pytest.mark.parametrize(
    "flags",
    [[], ["--expect-record", "0"], ["--expect-empty", "--expect-record", "0"]],
)
def test_requires_explicit_active_state(
    chain: ReleaseChain, capsysbinary: pytest.CaptureFixture[bytes], flags: list[str]
) -> None:
    bundle, _, address, _ = chain
    with pytest.raises(SystemExit) as error:
        main([str(bundle), address, *flags])
    assert error.value.code == 2
    assert capsysbinary.readouterr().out == b""
