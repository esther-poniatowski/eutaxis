"""Tests for the install registry: atomicity, locking, error surfacing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eutaxis.commands.models import InstallRecord
from eutaxis.commands.registry import Registry, RegistryCorruptedError


def _record(name: str = "alpha") -> InstallRecord:
    return InstallRecord(
        name=name,
        adapter="claude",
        scope="user",
        path=Path(f"/tmp/{name}"),
        content_hash="deadbeef",
        installed_at="2026-05-22T00:00:00+00:00",
    )


def test_upsert_round_trip(tmp_path: Path) -> None:
    reg = Registry(tmp_path / "state")
    reg.upsert(_record("alpha"))
    reg.upsert(_record("beta"))
    rows = sorted(reg.load(), key=lambda r: r.name)
    assert [r.name for r in rows] == ["alpha", "beta"]


def test_truncated_registry_raises_actionable_error(tmp_path: Path) -> None:
    reg = Registry(tmp_path / "state")
    reg.upsert(_record("alpha"))

    # Simulate a crash mid-write.
    reg.path.write_text("[", encoding="utf-8")

    with pytest.raises(RegistryCorruptedError) as exc_info:
        reg.load()
    msg = str(exc_info.value)
    assert str(reg.path) in msg
    assert "corrupted" in msg.lower()


def test_empty_registry_file_is_treated_as_empty(tmp_path: Path) -> None:
    reg = Registry(tmp_path / "state")
    reg.path.parent.mkdir(parents=True, exist_ok=True)
    reg.path.write_text("", encoding="utf-8")
    assert reg.load() == []


def test_registry_write_is_atomic_no_tmp_left_behind(tmp_path: Path) -> None:
    reg = Registry(tmp_path / "state")
    reg.upsert(_record("alpha"))
    # After a successful write the .tmp shouldn't linger.
    tmp_sibling = reg.path.with_suffix(reg.path.suffix + ".tmp")
    assert not tmp_sibling.exists()


def test_top_level_non_list_raises(tmp_path: Path) -> None:
    reg = Registry(tmp_path / "state")
    reg.path.parent.mkdir(parents=True, exist_ok=True)
    reg.path.write_text(json.dumps({"oops": "dict"}), encoding="utf-8")
    with pytest.raises(RegistryCorruptedError):
        reg.load()


def _upsert_worker(args: tuple[str, str]) -> None:
    """Module-level worker so multiprocessing can pickle it."""
    state_dir_str, name = args
    Registry(Path(state_dir_str)).upsert(
        InstallRecord(
            name=name,
            adapter="claude",
            scope="user",
            path=Path(f"/tmp/{name}"),
            content_hash="h",
            installed_at="2026-05-22T00:00:00+00:00",
        )
    )


def test_concurrent_upserts_preserve_records(tmp_path: Path) -> None:
    """Two processes upserting at once must not lose a row.

    Uses a multiprocessing pool because threads in the same process
    share the file lock by default with fcntl.flock; multiprocessing
    exercises the cross-process guarantee.
    """
    import multiprocessing

    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    Registry(state_dir).upsert(_record("seed"))

    names = [f"row-{i:02d}" for i in range(8)]
    with multiprocessing.get_context("spawn").Pool(4) as pool:
        pool.map(_upsert_worker, [(str(state_dir), n) for n in names])

    rows = {r.name for r in Registry(state_dir).load()}
    assert {"seed", *names}.issubset(rows)
