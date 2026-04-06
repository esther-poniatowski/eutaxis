"""
Prompt scaffolding module.

Initializes prompt-composition structure in a target project by copying or
symlinking starter templates from the eutaxis data directory.

This module is a stub. Implementation will follow once the prompt-family
scaffolding model is stabilized.
"""

from __future__ import annotations

from pathlib import Path

from . import data_path


def scaffold_workspace(target: Path) -> None:
    """Scaffold prompt-composition structure into a target project.

    Creates the initial prompt-family layout and copies default
    composition templates from the eutaxis data directory.

    Parameters
    ----------
    target : Path
        Root of the target project.
    """
    source = data_path()
    print(f"Scaffolding from {source} into {target}")
    print("Prompt scaffolding is not yet implemented.")
