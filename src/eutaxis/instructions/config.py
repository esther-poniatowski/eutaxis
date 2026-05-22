"""Configuration loading for instruction-file assembly."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .exceptions import ConfigurationError
from .models import (
    AgentConfig,
    InstructionConfig,
    ReferenceDoc,
    SourceFile,
    TargetConfig,
    TaskModule,
)


class ConfigLoader:
    """Load and validate instruction assembly configuration."""

    def __init__(self, config_path: Path, root: Path | None = None) -> None:
        self.config_path = config_path.expanduser().resolve()
        self.root_override = root.expanduser().resolve() if root else None

    def load(self) -> InstructionConfig:
        """Load a YAML configuration file."""
        if not self.config_path.is_file():
            raise ConfigurationError(
                f"Configuration file not found: {self.config_path}"
            )

        try:
            raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigurationError(
                f"Invalid YAML in {self.config_path}: {exc}"
            ) from exc

        if not isinstance(raw, dict):
            raise ConfigurationError("Configuration must be a YAML mapping")

        return InstructionConfig(
            root=self._resolve_root(raw),
            config_path=self.config_path,
            common_sources=self._parse_sources(raw.get("common_sources", [])),
            agents=self._parse_agents(raw.get("agents", [])),
            task_modules=self._parse_task_modules(raw.get("task_modules", [])),
            task_modules_heading=str(
                raw.get("task_modules_heading", "Task modules")
            ),
            task_modules_intro=str(raw.get("task_modules_intro", "")),
            reference_docs=self._parse_reference_docs(
                raw.get("reference_docs", [])
            ),
            reference_docs_heading=str(
                raw.get("reference_docs_heading", "Reference docs")
            ),
            reference_docs_intro=str(raw.get("reference_docs_intro", "")),
            rule_index_enabled=self._as_bool(
                raw.get("rule_index_enabled", False), "rule_index_enabled"
            ),
            rule_index_heading=str(
                raw.get("rule_index_heading", "Rule index")
            ),
            rule_index_intro=str(raw.get("rule_index_intro", "")),
            default_max_bytes=self._as_optional_positive_int(
                raw.get("max_bytes"), "max_bytes"
            ),
        )

    def _resolve_root(self, raw: dict[str, Any]) -> Path:
        if self.root_override is not None:
            return self.root_override

        raw_root = raw.get("root")
        if raw_root is None:
            return self.config_path.parent

        root = Path(str(raw_root)).expanduser()
        if not root.is_absolute():
            root = self.config_path.parent / root
        return root.resolve()

    def _parse_sources(self, raw_sources: Any) -> list[SourceFile]:
        if raw_sources is None:
            return []
        if not isinstance(raw_sources, list):
            raise ConfigurationError("sources must be a list")

        return [self._parse_source(source) for source in raw_sources]

    def _parse_source(self, raw: Any) -> SourceFile:
        if isinstance(raw, str):
            return SourceFile(path=Path(raw))

        if not isinstance(raw, dict):
            raise ConfigurationError(f"Invalid source specification: {raw!r}")
        if "path" not in raw:
            raise ConfigurationError("Source entries must specify 'path'")

        return SourceFile(
            path=Path(str(raw["path"])),
            sections=self._as_tuple(raw.get("sections", ())),
            exclude_sections=self._as_tuple(raw.get("exclude_sections", ())),
            heading_offset=self._as_non_negative_int(
                raw.get("heading_offset", 0),
                "heading_offset",
            ),
            strip_frontmatter=self._as_bool(
                raw.get("strip_frontmatter", True),
                "strip_frontmatter",
            ),
        )

    def _parse_agents(self, raw_agents: Any) -> list[AgentConfig]:
        if raw_agents is None:
            return []
        if not isinstance(raw_agents, list):
            raise ConfigurationError("agents must be a list")

        agents: list[AgentConfig] = []
        seen: set[str] = set()

        for raw_agent in raw_agents:
            agent = self._parse_agent(raw_agent)
            if agent.name in seen:
                raise ConfigurationError(f"Duplicate agent name: {agent.name}")
            seen.add(agent.name)
            agents.append(agent)

        return agents

    def _parse_agent(self, raw: Any) -> AgentConfig:
        if not isinstance(raw, dict):
            raise ConfigurationError(f"Invalid agent specification: {raw!r}")
        if "name" not in raw:
            raise ConfigurationError("Agent entries must specify 'name'")
        if "target" not in raw:
            raise ConfigurationError(f"Agent '{raw['name']}' must specify 'target'")

        return AgentConfig(
            name=str(raw["name"]),
            target=self._parse_target(raw["target"]),
            sources=self._parse_sources(raw.get("sources", [])),
            enabled=self._as_bool(raw.get("enabled", True), "enabled"),
            max_bytes=self._as_optional_positive_int(
                raw.get("max_bytes"), "max_bytes"
            ),
        )

    def _parse_target(self, raw: Any) -> TargetConfig:
        if isinstance(raw, str):
            return TargetConfig(path=Path(raw))

        if not isinstance(raw, dict):
            raise ConfigurationError(f"Invalid target specification: {raw!r}")
        if "path" not in raw:
            raise ConfigurationError("Target entries must specify 'path'")

        return TargetConfig(
            path=Path(str(raw["path"])),
            header=str(raw.get("header", "")),
            footer=str(raw.get("footer", "")),
        )

    def _parse_task_modules(self, raw_modules: Any) -> list[TaskModule]:
        if raw_modules is None:
            return []
        if not isinstance(raw_modules, list):
            raise ConfigurationError("task_modules must be a list")

        modules: list[TaskModule] = []
        seen: set[str] = set()
        for raw in raw_modules:
            module = self._parse_task_module(raw)
            if module.id in seen:
                raise ConfigurationError(
                    f"Duplicate task_module id: {module.id}"
                )
            seen.add(module.id)
            modules.append(module)
        return modules

    def _parse_task_module(self, raw: Any) -> TaskModule:
        if not isinstance(raw, dict):
            raise ConfigurationError(
                f"Invalid task_module specification: {raw!r}"
            )
        for required in ("id", "title", "path", "trigger"):
            if required not in raw:
                raise ConfigurationError(
                    f"task_module entries must specify '{required}'"
                )

        return TaskModule(
            id=str(raw["id"]),
            title=str(raw["title"]),
            path=Path(str(raw["path"])),
            trigger=str(raw["trigger"]),
            description=str(raw.get("description", "")),
        )

    def _parse_reference_docs(self, raw_docs: Any) -> list[ReferenceDoc]:
        if raw_docs is None:
            return []
        if not isinstance(raw_docs, list):
            raise ConfigurationError("reference_docs must be a list")

        docs: list[ReferenceDoc] = []
        seen: set[str] = set()
        for raw in raw_docs:
            doc = self._parse_reference_doc(raw)
            if doc.id in seen:
                raise ConfigurationError(
                    f"Duplicate reference_doc id: {doc.id}"
                )
            seen.add(doc.id)
            docs.append(doc)
        return docs

    def _parse_reference_doc(self, raw: Any) -> ReferenceDoc:
        if not isinstance(raw, dict):
            raise ConfigurationError(
                f"Invalid reference_doc specification: {raw!r}"
            )
        for required in ("id", "title", "local_path", "github_url", "trigger"):
            if required not in raw:
                raise ConfigurationError(
                    f"reference_doc entries must specify '{required}'"
                )

        return ReferenceDoc(
            id=str(raw["id"]),
            title=str(raw["title"]),
            local_path=str(raw["local_path"]),
            github_url=str(raw["github_url"]),
            trigger=str(raw["trigger"]),
            description=str(raw.get("description", "")),
        )

    def _as_tuple(self, value: Any) -> tuple[str, ...]:
        if value in (None, ()):
            return ()
        if isinstance(value, str):
            return (value,)
        if isinstance(value, list):
            return tuple(str(item) for item in value)
        raise ConfigurationError(f"Expected string or list of strings, got {value!r}")

    def _as_bool(self, value: Any, field: str) -> bool:
        if isinstance(value, bool):
            return value
        raise ConfigurationError(f"Field '{field}' must be a boolean, got {value!r}")

    def _as_optional_positive_int(
        self, value: Any, field: str
    ) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigurationError(
                f"Field '{field}' must be a positive integer, got {value!r}"
            )
        if value <= 0:
            raise ConfigurationError(f"Field '{field}' must be positive")
        return value

    def _as_non_negative_int(self, value: Any, field: str) -> int:
        if not isinstance(value, int):
            raise ConfigurationError(
                f"Field '{field}' must be an integer, got {value!r}"
            )
        if value < 0:
            raise ConfigurationError(f"Field '{field}' must be non-negative")
        return value


def load_config(config_path: Path, root: Path | None = None) -> InstructionConfig:
    """Load instruction configuration from disk."""
    return ConfigLoader(config_path, root=root).load()
