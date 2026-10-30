"""Verify that the built wheel contains every code-owned acquisition resource."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from setuptools import build_meta

from eutaxis.declarations.acquisition_contract import (
    PACKAGED_DECLARATION_PATHS,
    PACKAGED_FACET_PATH,
)


def test_built_wheel_contains_every_packaged_acquisition_resource(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = Path(__file__).parents[1]
    checkout = tmp_path / "project"
    shutil.copytree(
        project,
        checkout,
        ignore=shutil.ignore_patterns(
            ".git",
            ".mypy_cache",
            ".pytest_cache",
            "build",
            "dist",
            "*.egg-info",
        ),
    )
    distribution = tmp_path / "dist"
    distribution.mkdir()
    monkeypatch.chdir(checkout)

    wheel_name = build_meta.build_wheel(str(distribution))

    with zipfile.ZipFile(distribution / wheel_name) as archive:
        names = set(archive.namelist())
    expected = {
        f"eutaxis/data/{PACKAGED_FACET_PATH}",
        *(
            f"eutaxis/data/declarations/v1/{path}"
            for path in PACKAGED_DECLARATION_PATHS
        ),
    }
    assert expected <= names
