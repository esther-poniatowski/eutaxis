"""
Workspace scaffolding module.

Initializes governance structure in a target workspace by copying or
symlinking governance files from the eutaxis data directory.

This module is a stub. Implementation will follow once the governance
file structure is stabilized.
"""

from __future__ import annotations

from pathlib import Path

from . import data_path


def scaffold_workspace(target: Path) -> None:
    """Scaffold governance structure into a target workspace.

    Creates the governance directory layout and copies default
    specification files from the eutaxis data directory.

    Parameters
    ----------
    target : Path
        Root of the target workspace.
    """
    source = data_path()
    print(f"Scaffolding from {source} into {target}")
    print("Scaffolding is not yet implemented.")
