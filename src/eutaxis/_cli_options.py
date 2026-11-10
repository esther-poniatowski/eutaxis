"""Options shared by the command-line modules of ``eutaxis``.

The reserved option ``--root`` names the project folder from which a
command finds its settings file and resolves relative paths. Former names
of that option (``--project``, ``--target``) stay accepted for one release
as hidden aliases, which print a warning naming ``--root``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer


def root_option(help_text: str) -> Any:
    """Return the ``--root`` / ``-r`` option with the help text of one command."""
    return typer.Option(None, "--root", "-r", help=help_text)


def former_root_option(*flags: str) -> Any:
    """Return a hidden option that keeps a former name of ``--root``."""
    return typer.Option(None, *flags, hidden=True)


def explicit_root(
    root: str | None, former: str | None, former_flag: str
) -> Path | None:
    """Return the root given on the command line, or ``None`` when absent.

    Parameters
    ----------
    root : str, optional
        Value of ``--root``.
    former : str, optional
        Value of the hidden alias that keeps the former name of the option.
    former_flag : str
        Former name, printed in the deprecation warning.

    Returns
    -------
    Path or None
        Absolute root folder, or ``None`` when neither option is given.

    Raises
    ------
    typer.Exit
        With code 2 when both ``--root`` and its former name are given.
    """
    if former is not None:
        typer.echo(
            f"warning: {former_flag} is deprecated and will be removed; use --root.",
            err=True,
        )
        if root is not None:
            typer.echo(
                f"Error: give the root once, with --root; {former_flag} is its "
                "former name.",
                err=True,
            )
            raise typer.Exit(code=2)
        root = former
    return Path(root).expanduser().resolve() if root is not None else None
