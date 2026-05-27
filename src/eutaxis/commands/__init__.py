"""Declarative skill-artifact subsystem for cross-agent compilation.

The package compiles a single Markdown command source into a native
**Agent Skill** directory for each registered agent (Claude Code,
Codex). The artifact is multi-file: ``SKILL.md`` plus adapter-specific
siblings (e.g. ``agents/openai.yaml`` for Codex) plus an
``.eutaxis-owned.json`` sidecar used by the installer.

Public objects
--------------
CommandError, CommandNotFoundError, CommandRenderError, OwnershipError,
TemplateError, RegistryCorruptedError
    Exception hierarchy.
CommandSource, RenderedArtifact, ArtifactFile, InstallRecord
    Data containers.
AgentAdapter, register_adapter, get_adapter, all_adapters
    Adapter registry contract.
load_sources
    Discover command sources across built-in, user, and project layers.
render_command
    Pure function: ``CommandSource × AgentAdapter`` -> ``RenderedArtifact``.
install_command, uninstall_command, diff_command
    Filesystem-effecting operations guarded by ownership markers.
Registry
    Persistent record of installed commands.
"""

from .adapters import (
    AgentAdapter,
    all_adapters,
    get_adapter,
    register_adapter,
)
from .exceptions import (
    CommandError,
    CommandNotFoundError,
    CommandRenderError,
    FailureModeError,
    OwnershipError,
    TemplateError,
)
from .installer import diff_command, install_command, uninstall_command
from .loader import load_from_instruction_config, load_sources
from .models import ArtifactFile, CommandSource, InstallRecord, RenderedArtifact
from .registry import Registry, RegistryCorruptedError
from .rendering import check_failure_mode, render_command

__all__ = [
    "AgentAdapter",
    "ArtifactFile",
    "CommandError",
    "CommandNotFoundError",
    "CommandRenderError",
    "CommandSource",
    "FailureModeError",
    "InstallRecord",
    "OwnershipError",
    "Registry",
    "RegistryCorruptedError",
    "RenderedArtifact",
    "TemplateError",
    "all_adapters",
    "check_failure_mode",
    "diff_command",
    "get_adapter",
    "install_command",
    "load_from_instruction_config",
    "load_sources",
    "register_adapter",
    "render_command",
    "uninstall_command",
]
