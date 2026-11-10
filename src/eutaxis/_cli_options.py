"""Options and behaviors shared by the command-line modules of ``eutaxis``.

The module applies the command-line conventions of the workspace:

- the reserved option ``--root`` names the root, which ``resolve_root``
  completes from ``EUTAXIS_ROOT``, from the nearest folder that holds the
  settings file, or from the current folder;
- every error of the package exits with the status that its exception
  carries: 2 for a usage or configuration error, 1 for a problem found by a
  check or a validation;
- a command that deletes files outside its outputs asks for a confirmation
  on a terminal, ``--yes`` answers it, and without a terminal and without
  ``--yes`` the command stops with status 2.
"""

from __future__ import annotations

import functools
import sys
from pathlib import Path
from typing import Any, Callable, TypeVar

import typer

F = TypeVar("F", bound=Callable[..., Any])


def root_option(help_text: str) -> Any:
    """Return the ``--root`` / ``-r`` option with the help text of one command."""
    return typer.Option(None, "--root", "-r", help=help_text)


def command_root(root: str | None) -> Path:
    """Return the root of a command, given the value of ``--root``.

    Parameters
    ----------
    root : str, optional
        Value of ``--root``, relative to the current folder.

    Returns
    -------
    Path
        Absolute root folder, resolved by ``resolve_root``.
    """
    from .instructions.config import resolve_root

    return resolve_root(Path(root) if root is not None else None)


def command_path(path: str | None) -> Path | None:
    """Return a path option made absolute against the current folder."""
    if path is None:
        return None
    return Path(path).expanduser().resolve()


def _domain_errors() -> tuple[type[Exception], ...]:
    """Return the exception bases of the package, each carrying ``exit_code``."""
    from .commands.exceptions import CommandError
    from .instructions.exceptions import InstructionError
    from .ops.exceptions import OpsError
    from .rule_query.exceptions import RuleQueryError
    from .scaffold import ScaffoldError

    return (CommandError, InstructionError, OpsError, RuleQueryError, ScaffoldError)


def reports_errors(function: F) -> F:
    """Report an error of the package as a message and its exit status.

    The decorated command prints ``Error: <message>`` on standard error and
    exits with the ``exit_code`` of the exception, in place of a traceback.
    """

    @functools.wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except _domain_errors() as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=getattr(exc, "exit_code", 2)) from exc

    return wrapper  # type: ignore[return-value]


def stdin_is_terminal() -> bool:
    """Return whether the standard input is a terminal that can answer."""
    return sys.stdin.isatty()


def confirmation_needed(yes: bool, action: str) -> bool:
    """Return whether a command must ask before it acts.

    Parameters
    ----------
    yes : bool
        Value of ``--yes``, which answers the confirmation.
    action : str
        Description of the action, printed when no confirmation can be asked.

    Returns
    -------
    bool
        False under ``--yes``; True on a terminal without ``--yes``.

    Raises
    ------
    typer.Exit
        With status 2, without a terminal and without ``--yes``.
    """
    if yes:
        return False
    if not stdin_is_terminal():
        typer.echo(
            f"Error: {action} requires a confirmation, and the standard input "
            "is not a terminal. Pass --yes to confirm, or --dry-run to preview.",
            err=True,
        )
        raise typer.Exit(code=2)
    return True
