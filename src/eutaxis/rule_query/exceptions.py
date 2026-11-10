"""Exceptions for the rule query."""

from __future__ import annotations


class RuleQueryError(Exception):
    """Base exception for rule queries; every one is a usage error (exit status 2)."""

    exit_code = 2


class RuleSourceError(RuleQueryError):
    """Raised when the modules or skills to query cannot be read."""


class UnknownRuleError(RuleQueryError):
    """Raised when no queried module defines the requested label."""


class AmbiguousRuleError(RuleQueryError):
    """Raised when several queried modules define the requested label."""


class UnknownPartError(RuleQueryError):
    """Raised when the requested rule lacks the requested part."""
