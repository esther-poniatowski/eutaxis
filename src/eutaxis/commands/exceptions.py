"""Exceptions for the commands subsystem."""

from __future__ import annotations


class CommandError(Exception):
    """Base exception for the commands subsystem."""

    exit_code = 1


class CommandNotFoundError(CommandError):
    """Raised when a referenced command name is unknown."""


class CommandRenderError(CommandError):
    """Raised when a command source cannot be parsed or rendered."""


class TemplateError(CommandError):
    """Raised when a template references an unknown variable or is malformed."""


class OwnershipError(CommandError):
    """Raised when an install/uninstall target is not eutaxis-owned."""

    exit_code = 2
