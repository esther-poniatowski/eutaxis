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
