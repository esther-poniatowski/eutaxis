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


class FailureModeError(CommandError):
    """Raised when a source's failure-mode classification forbids the target regime.

    A ``failure-mode: silent`` source cannot ship as a ``model-invoked`` skill;
    the model-judgment activation gate gives no visibility guarantee before the
    first irreversible action. A ``silent`` source with
    ``required-visibility: pre-invocation`` cannot ship as a ``user-invoked``
    skill either; it routes only to the always-on body. See the
    ``failure-mode-as-source-field`` ADR.
    """

    exit_code = 3
