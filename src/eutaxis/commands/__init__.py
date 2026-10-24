"""Declarative skill-artifact subsystem for cross-agent compilation.

The package compiles a single Markdown command source into a native
**Agent Skill** directory for each registered agent (Claude Code,
Codex). The artifact is multi-file: ``SKILL.md`` plus adapter-specific
siblings (e.g. ``agents/openai.yaml`` for Codex) plus an
``.eutaxis-owned.json`` sidecar used by the installer. A source that
declares ``disclosure: progressive`` also emits one ``rules/<label>.md``
file per rule (see :mod:`eutaxis.commands.disclosure`).

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
    ``CommandSource × AgentAdapter`` -> ``RenderedArtifact``, without writes.
install_command, uninstall_command, diff_command
    Filesystem-effecting operations guarded by ownership markers.
is_eutaxis_owned
    Ownership predicate for an artifact directory.
Registry
    Persistent record of installed commands.
"""

from .adapters import (
    AgentAdapter,
    all_adapters,
    get_adapter,
    register_adapter,
)
from .skill_budgets import SkillBudgetMeasurement, measure_skill_budgets
from .exceptions import (
    CommandError,
    CommandNotFoundError,
    CommandRenderError,
    FailureModeError,
    OwnershipError,
    TemplateError,
)
from .installer import (
    diff_command,
    install_command,
    is_eutaxis_owned,
    uninstall_command,
)
from .loader import load_from_instruction_config, load_sources
from .models import ArtifactFile, CommandSource, InstallRecord, RenderedArtifact
from .registry import Registry, RegistryCorruptedError
from .rendering import check_failure_mode, render_command
from .synchronization import (
    SkillSyncAction,
    SkillSyncManifest,
    apply_skill_sync,
    plan_skill_sync,
)

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
    "SkillBudgetMeasurement",
    "SkillSyncAction",
    "SkillSyncManifest",
    "TemplateError",
    "all_adapters",
    "apply_skill_sync",
    "check_failure_mode",
    "diff_command",
    "get_adapter",
    "install_command",
    "is_eutaxis_owned",
    "load_from_instruction_config",
    "load_sources",
    "measure_skill_budgets",
    "plan_skill_sync",
    "register_adapter",
    "render_command",
    "uninstall_command",
]
