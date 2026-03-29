"""
Prompt validation module.

Will validate prompt family layouts, composition configs, and related
artifacts against eutaxis profile rules.

This module is a stub. Implementation will follow once family profiles
and assembly diagnostics are stabilized.
"""

from __future__ import annotations

from pathlib import Path


def validate_prompt_paths(paths: list[Path]) -> list[str]:
    """Validate that the referenced prompt files exist.

    Parameters
    ----------
    paths : list[Path]
        Prompt-related files or directories to validate.

    Returns
    -------
    list of str
        List of validation error messages. Empty if all paths exist.
    """
    errors: list[str] = []
    for path in paths:
        if not path.exists():
            errors.append(f"Path not found: {path}")
    return errors
