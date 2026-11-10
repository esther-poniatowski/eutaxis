"""Exceptions for shell-side operations."""

from __future__ import annotations


class OpsError(Exception):
    """Base exception for operations; every one is a usage error (exit status 2)."""

    exit_code = 2


class OutsideAllowedRootError(OpsError):
    """Raised when a resolved path escapes its declared root.

    This is the path-prefix guard that prevents wildcards or symlinks
    from causing deletion outside the agent-memory directories.
    """

    exit_code = 2
