"""Render concise command-line failures without hiding exception notes."""

from __future__ import annotations

from typing import NoReturn

import typer


def exit_with_error(exc: BaseException) -> NoReturn:
    """Print the primary failure and its cleanup notes, then exit unsuccessfully."""
    typer.echo(f"Error: {exc}", err=True)
    for note in getattr(exc, "__notes__", ()):
        typer.echo(note, err=True)
    raise typer.Exit(code=getattr(exc, "exit_code", 3)) from exc
