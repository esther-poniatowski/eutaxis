"""Verify that the built wheel contains every code-owned acquisition resource."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
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
        "eutaxis/data/schemas/context-facets-v1.base.schema.json",
        "eutaxis/data/schemas/context-facets-v1.schema.json",
        "eutaxis/data/schemas/declaration-v1.base.schema.json",
        "eutaxis/data/schemas/declaration-v1.schema.json",
        *(
            f"eutaxis/data/declarations/v1/{path}"
            for path in PACKAGED_DECLARATION_PATHS
        ),
    }
    assert expected <= names

    installed = tmp_path / "installed"
    with zipfile.ZipFile(distribution / wheel_name) as archive:
        archive.extractall(installed)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(installed)
    subprocess.run(
        (
            sys.executable,
            "-c",
            "from eutaxis import data_path; "
            "from eutaxis.declarations import load_declaration, load_facet_registry; "
            "from eutaxis.declarations.schema import declaration_schema; "
            "root=data_path(); "
            "assert declaration_schema()['properties']['_schema']['const'] "
            "== 'eutaxis:declaration@1'; "
            "load_facet_registry(root/'registries'/'context-facets-v1.yaml'); "
            "load_declaration(root/'declarations'/'v1'/'manual-judgment.yaml')",
        ),
        check=True,
        cwd=tmp_path,
        env=environment,
    )
