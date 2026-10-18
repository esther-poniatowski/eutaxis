"""Exceptions for instruction-file assembly."""

from __future__ import annotations

from pathlib import Path


class InstructionError(Exception):
    """Base exception for instruction assembly errors."""

    exit_code = 1


class ConfigurationError(InstructionError):
    """Raised when an instruction config file is invalid."""


class SourceNotFoundError(InstructionError):
    """Raised when a configured source file does not exist."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"Source file not found: {path}")
        self.path = path


class RejectedLabelError(InstructionError):
    """Raised under ``strict_rule_labels`` when a module holds a rejected label line."""

    def __init__(self, locations: list[str]) -> None:
        super().__init__(
            f"{len(locations)} label line(s) violate the label grammar, and "
            f"strict_rule_labels is set: {', '.join(locations)}. Rename each "
            f"label, or unset strict_rule_labels to report them as warnings."
        )
        self.locations = locations


class BudgetExceededError(InstructionError):
    """Raised when a rendered output exceeds its configured byte budget."""

    exit_code = 2

    def __init__(self, agent_name: str, size: int, limit: int) -> None:
        super().__init__(
            f"Agent {agent_name!r} renders to {size} bytes, "
            f"over the {limit}-byte budget."
        )
        self.agent_name = agent_name
        self.size = size
        self.limit = limit
