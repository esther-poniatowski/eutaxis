"""Imperative shell-side operations invoked by compiled commands.

This package holds the doers (``clean_memory``, ...) that compiled
slash commands call via the CLI. It is independent of
``eutaxis.commands``; nothing here imports from there. The split keeps
the imperative, privilege-affecting code isolated from the declarative
compilation pipeline.
"""

from .exceptions import OpsError, OutsideAllowedRootError
from .memory import (
    CLAUDE_PROJECTS_ROOT,
    CODEX_MEMORIES_ROOT,
    MemoryWipeResult,
    clean_memory,
    encode_project_slug,
)

__all__ = [
    "CLAUDE_PROJECTS_ROOT",
    "CODEX_MEMORIES_ROOT",
    "MemoryWipeResult",
    "OpsError",
    "OutsideAllowedRootError",
    "clean_memory",
    "encode_project_slug",
]
