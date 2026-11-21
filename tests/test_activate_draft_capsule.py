"""Exercise forward activation, commit boundaries, and recovery."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from specs import activate_release_capsule as activation
from specs.approve_release_capsule import ExpectedActive, approval_bytes
from specs.release_activation_store import consumer_bytes, read_head
from tests.test_approve_draft_capsule import ReleaseChain, acquisition, chain


@pytest.fixture
def directories(tmp_path: Path) -> tuple[Path, Path]:
    """Create an empty private store and the reviewed initial target state."""
    store = tmp_path / "store"
    targets = tmp_path / "targets"
    store.mkdir()
    (targets / "host").mkdir(parents=True)
    (targets / "host" / "old.md").write_bytes(b"old instructions")
    return store, targets


def _approval(
    store: Path, bundle: Path, capsule: str, expected: ExpectedActive
) -> Path:
    """Keep the operator record beside the store."""
    path = store.parent / "approval.json"
    path.write_bytes(approval_bytes(bundle, capsule, expected))
    return path


def _activate_initial(chain: ReleaseChain, directories: tuple[Path, Path]) -> None:
    """Commit the first release against its reviewed golden baseline."""
    bundle, initial, _, _ = chain
    store, targets = directories
    approved = _approval(store, bundle, initial, ExpectedActive(None, None))
    assert activation.activate_release(store, targets, bundle, initial, approved) == 0
    assert read_head(store).active == ExpectedActive(0, initial)


def test_activates_initial_and_successor(
    chain: ReleaseChain, directories: tuple[Path, Path]
) -> None:
    _activate_initial(chain, directories)
    bundle, initial, successor, _ = chain
    store, targets = directories
    approved = _approval(store, bundle, successor, ExpectedActive(0, initial))
    assert activation.activate_release(store, targets, bundle, successor, approved) == 1
    assert read_head(store).active == ExpectedActive(1, successor)
    assert consumer_bytes(targets, "host/new.md") == b"new instructions"
    assert consumer_bytes(targets, "host/old.md") is None
    assert not list(store.glob("pending-*"))
    with pytest.raises(ValueError, match="predecessor differs"):
        activation.activate_release(store, targets, bundle, successor, approved)


def test_rejects_stale_approval_or_changed_targets_before_writes(
    chain: ReleaseChain, directories: tuple[Path, Path]
) -> None:
    _activate_initial(chain, directories)
    bundle, initial, successor, _ = chain
    store, targets = directories
    names = set(store.iterdir())
    approved = _approval(store, bundle, successor, ExpectedActive(5, initial))
    with pytest.raises(ValueError, match="Approval does not match"):
        activation.activate_release(store, targets, bundle, successor, approved)
    approved = _approval(store, bundle, successor, ExpectedActive(0, initial))
    (targets / "host" / "old.md").write_bytes(b"operator edit")
    with pytest.raises(ValueError, match="differs from the reviewed baseline"):
        activation.activate_release(store, targets, bundle, successor, approved)
    assert set(store.iterdir()) == names
    assert consumer_bytes(targets, "host/old.md") == b"operator edit"


def test_precommit_failure_restores_baseline(
    chain: ReleaseChain, directories: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _activate_initial(chain, directories)
    bundle, initial, successor, _ = chain
    store, targets = directories
    approved = _approval(store, bundle, successor, ExpectedActive(0, initial))
    original = activation.update_target

    def fail_after_retiring(root, name, expected, selected):
        original(root, name, expected, selected)
        if name == "host/old.md" and selected is None:
            raise OSError("planted precommit failure")

    monkeypatch.setattr(activation, "update_target", fail_after_retiring)
    with pytest.raises(OSError, match="planted precommit failure"):
        activation.activate_release(store, targets, bundle, successor, approved)
    assert read_head(store).active == ExpectedActive(0, initial)
    assert not list(store.glob("pending-*"))
    assert consumer_bytes(targets, "host/old.md") == b"old instructions"
    assert consumer_bytes(targets, "host/new.md") is None


def test_recovery_preserves_conflict_then_can_resume(
    chain: ReleaseChain, directories: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _activate_initial(chain, directories)
    bundle, initial, successor, _ = chain
    store, targets = directories
    approved = _approval(store, bundle, successor, ExpectedActive(0, initial))
    original = activation.update_target

    def conflict(root, name, expected, selected):
        original(root, name, expected, selected)
        if name == "host/old.md" and selected is None:
            (root / name).write_bytes(b"operator edit")
            raise OSError("planted interruption")

    with monkeypatch.context() as patch:
        patch.setattr(activation, "update_target", conflict)
        with pytest.raises(ValueError, match="Concurrent edits preserved"):
            activation.activate_release(store, targets, bundle, successor, approved)
    assert (store / "pending-1").is_file()
    assert consumer_bytes(targets, "host/old.md") == b"operator edit"
    with pytest.raises(ValueError, match="Concurrent edits preserved"):
        activation.recover_release(store, targets)
    (targets / "host" / "old.md").write_bytes(b"old instructions")
    assert "Restored the baseline" in activation.recover_release(store, targets)
    assert not list(store.glob("pending-*"))
    assert read_head(store).active == ExpectedActive(0, initial)


def test_error_after_commit_never_restores_targets(
    chain: ReleaseChain, directories: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _activate_initial(chain, directories)
    bundle, initial, successor, _ = chain
    store, targets = directories
    approved = _approval(store, bundle, successor, ExpectedActive(0, initial))
    original = activation.sync_directory

    def fail_marker_sync(directory: Path) -> None:
        if directory == store and (store / "commit-1").exists():
            raise OSError("planted marker sync failure")
        original(directory)

    with monkeypatch.context() as patch:
        patch.setattr(activation, "sync_directory", fail_marker_sync)
        with pytest.raises(ValueError, match="may have committed"):
            activation.activate_release(store, targets, bundle, successor, approved)
    assert read_head(store).active == ExpectedActive(1, successor)
    assert consumer_bytes(targets, "host/new.md") == b"new instructions"
    assert consumer_bytes(targets, "host/old.md") is None
    assert "Cleared committed intent" in activation.recover_release(store, targets)
    assert not list(store.glob("pending-*"))


def test_concurrent_promoters_commit_at_most_one_successor(
    chain: ReleaseChain, directories: tuple[Path, Path]
) -> None:
    _activate_initial(chain, directories)
    bundle, initial, successor, sibling = chain
    store, targets = directories
    expected = ExpectedActive(0, initial)

    def promote(address: str) -> str | None:
        approval = store.parent / f"{address.removeprefix('sha256:')}.json"
        approval.write_bytes(approval_bytes(bundle, address, expected))
        try:
            assert (
                activation.activate_release(store, targets, bundle, address, approval)
                == 1
            )
        except ValueError as error:
            assert "predecessor differs" in str(error)
            return None
        return address

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(promote, (successor, sibling)))
    committed = [address for address in results if address is not None]
    assert len(committed) == 1
    assert read_head(store).active == ExpectedActive(1, committed[0])
    assert not list(store.glob("pending-*"))


def _activate_successor(
    chain: ReleaseChain, directories: tuple[Path, Path]
) -> ExpectedActive:
    """Commit the fixture successor and return its recorded live state."""
    _activate_initial(chain, directories)
    bundle, initial, successor, _ = chain
    store, targets = directories
    approved = _approval(store, bundle, successor, ExpectedActive(0, initial))
    assert activation.activate_release(store, targets, bundle, successor, approved) == 1
    return ExpectedActive(1, successor)


def test_rollback_appends_history_and_allows_fresh_forward_approval(
    chain: ReleaseChain, directories: tuple[Path, Path]
) -> None:
    expected = _activate_successor(chain, directories)
    bundle, initial, successor, _ = chain
    store, targets = directories
    original = {name: (store / name).read_bytes() for name in ("commit-0", "commit-1")}
    assert activation.rollback_release(store, targets, expected) == (2, initial)
    assert read_head(store).active == ExpectedActive(2, initial)
    assert all((store / name).read_bytes() == data for name, data in original.items())
    assert consumer_bytes(targets, "host/old.md") == b"old instructions"
    assert consumer_bytes(targets, "host/new.md") is None
    assert not list(store.glob("pending-*"))
    with pytest.raises(ValueError, match="expected active state differs"):
        activation.rollback_release(store, targets, expected)
    with pytest.raises(ValueError, match="no predecessor"):
        activation.rollback_release(store, targets, ExpectedActive(2, initial))
    with pytest.raises(ValueError, match="Approval does not match"):
        activation.activate_release(
            store, targets, bundle, successor, store.parent / "approval.json"
        )
    approved = _approval(store, bundle, successor, ExpectedActive(2, initial))
    assert activation.activate_release(store, targets, bundle, successor, approved) == 3


def test_rollback_rejects_consumer_drift(
    chain: ReleaseChain, directories: tuple[Path, Path]
) -> None:
    expected = _activate_successor(chain, directories)
    store, targets = directories
    before = set(store.iterdir())
    (targets / "host" / "new.md").write_bytes(b"edited")
    with pytest.raises(ValueError, match="differs from the reviewed baseline"):
        activation.rollback_release(store, targets, expected)
    assert set(store.iterdir()) == before
    assert consumer_bytes(targets, "host/new.md") == b"edited"


def test_interrupted_rollback_preserves_successor_until_commit(
    chain: ReleaseChain, directories: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = _activate_successor(chain, directories)
    store, targets = directories
    original = activation.update_target

    def interrupt(root, name, expected_bytes, selected):
        original(root, name, expected_bytes, selected)
        if name == "host/new.md" and selected is None:
            raise OSError("planted rollback interruption")

    with monkeypatch.context() as patch:
        patch.setattr(activation, "update_target", interrupt)
        with pytest.raises(OSError, match="planted rollback interruption"):
            activation.rollback_release(store, targets, expected)
    assert read_head(store).active == expected
    assert consumer_bytes(targets, "host/new.md") == b"new instructions"
    assert consumer_bytes(targets, "host/old.md") is None
    assert not list(store.glob("pending-*"))


def test_rollback_after_marker_failure_keeps_predecessor_files(
    chain: ReleaseChain, directories: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = _activate_successor(chain, directories)
    _, initial, _, _ = chain
    store, targets = directories
    original = activation.sync_directory

    def fail(directory: Path) -> None:
        if directory == store and (store / "commit-2").exists():
            raise OSError("planted rollback marker failure")
        original(directory)

    with monkeypatch.context() as patch:
        patch.setattr(activation, "sync_directory", fail)
        with pytest.raises(ValueError, match="may have committed"):
            activation.rollback_release(store, targets, expected)
    assert read_head(store).active == ExpectedActive(2, initial)
    assert "Cleared committed intent" in activation.recover_release(store, targets)
    assert consumer_bytes(targets, "host/new.md") is None
    assert consumer_bytes(targets, "host/old.md") == b"old instructions"
