"""Data models for instruction-file assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .exceptions import ConfigurationError


@dataclass(frozen=True)
class SourceFile:
    """Markdown source file included in one or more instruction outputs."""

    path: Path
    sections: tuple[str, ...] = ()
    exclude_sections: tuple[str, ...] = ()
    heading_offset: int = 0
    strip_frontmatter: bool = True

    def __post_init__(self) -> None:
        if self.heading_offset < 0:
            raise ConfigurationError("heading_offset must be non-negative")


@dataclass(frozen=True)
class TargetConfig:
    """Output file target and surrounding literal content."""

    path: Path
    header: str = ""
    footer: str = ""


@dataclass(frozen=True)
class TaskModule:
    """A task-specific instruction module referenced by the router section."""

    id: str
    title: str
    path: Path
    trigger: str
    description: str = ""


@dataclass(frozen=True)
class ReferenceDoc:
    """An authoritative external reference doc with a local path and GitHub fallback."""

    id: str
    title: str
    local_path: str
    github_url: str
    trigger: str
    description: str = ""


@dataclass
class AgentConfig:
    """One generated instruction output."""

    name: str
    target: TargetConfig
    sources: list[SourceFile] = field(default_factory=list)
    enabled: bool = True
    max_bytes: int | None = None


@dataclass
class InstructionConfig:
    """Complete instruction assembly configuration."""

    root: Path
    config_path: Path
    agents: list[AgentConfig] = field(default_factory=list)
    common_sources: list[SourceFile] = field(default_factory=list)
    task_modules: list[TaskModule] = field(default_factory=list)
    task_modules_heading: str = "Task modules"
    task_modules_intro: str = ""
    reference_docs: list[ReferenceDoc] = field(default_factory=list)
    reference_docs_heading: str = "Reference docs"
    reference_docs_intro: str = ""
    rule_index_enabled: bool = False
    rule_index_heading: str = "Rule index"
    rule_index_intro: str = ""
    rule_index_pointer: str = ""
    rule_index_target: TargetConfig | None = None
    default_max_bytes: int | None = None

    def budget_for(self, agent: AgentConfig) -> int | None:
        """Return the byte budget that applies to one agent, if any."""
        if agent.max_bytes is not None:
            return agent.max_bytes
        return self.default_max_bytes

    def enabled_agents(self) -> list[AgentConfig]:
        """Return enabled agent outputs."""
        return [agent for agent in self.agents if agent.enabled]

    def get_agent(self, name: str) -> AgentConfig | None:
        """Return an agent output by name."""
        for agent in self.agents:
            if agent.name == name:
                return agent
        return None

    def resolve(self, path: Path) -> Path:
        """Resolve a config path against the configured root."""
        path = path.expanduser()
        if path.is_absolute():
            return path
        return self.root / path


@dataclass(frozen=True)
class Section:
    """A Markdown section with its heading and full body."""

    heading: str
    level: int
    content: str
