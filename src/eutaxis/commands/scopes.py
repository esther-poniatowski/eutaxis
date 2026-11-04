"""Validate the closed installation-scope vocabulary at command boundaries."""

from __future__ import annotations

from .exceptions import CommandError

VALID_SCOPES = ("user", "project")


def validate_scope(scope: str) -> None:
    """Reject values outside the public ``user|project`` scope domain."""
    if scope not in VALID_SCOPES:
        admitted = " or ".join(repr(value) for value in VALID_SCOPES)
        raise CommandError(f"Invalid scope {scope!r}; expected {admitted}.")
