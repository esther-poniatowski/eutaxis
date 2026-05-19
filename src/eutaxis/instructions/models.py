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


@dataclass
class AgentConfig:
    """One generated instruction output."""

    name: str
    target: TargetConfig
    sources: list[SourceFile] = field(default_factory=list)
    enabled: bool = True


@dataclass
class InstructionConfig:
    """Complete instruction assembly configuration."""

    root: Path
    config_path: Path
    agents: list[AgentConfig] = field(default_factory=list)
    common_sources: list[SourceFile] = field(default_factory=list)

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
