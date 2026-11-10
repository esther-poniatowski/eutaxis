"""Fixtures shared by the test modules."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run each test from its temporary folder, without ``EUTAXIS_ROOT``.

    A command resolves its root from ``EUTAXIS_ROOT`` and from the current
    folder. The fixture keeps the environment and the folder of the test
    runner out of that resolution.
    """
    monkeypatch.delenv("EUTAXIS_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
