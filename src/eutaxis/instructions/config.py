"""Configuration loading for instruction-file assembly."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from ..names import is_safe_slug
from .exceptions import ConfigurationError
from .loading_units import validate_loading_units
from .markdown import parse_frontmatter
from .models import (
    AgentConfig,
    InstructionChain,
    InstructionConfig,
    ReferenceDoc,
    SkillLoadingMember,
    SkillLoadingUnit,
    SourceFile,
    TargetConfig,
    TaskModule,
)


class ConfigLoader:
    """Load and validate instruction assembly configuration.

    The relative paths of the configuration file resolve against ``root``, or,
    when ``root`` is absent, against ``settings_root(config_path)``. The
    retired key ``root`` is rejected.
    """

    def __init__(self, config_path: Path, root: Path | None = None) -> None:
        self.config_path = config_path.expanduser().resolve()
        self.root = root.expanduser().resolve() if root else None

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

        config = InstructionConfig(
            root=self._resolve_root(raw),
            config_path=self.config_path,
            common_sources=self._parse_sources(raw.get("common_sources", [])),
            agents=self._parse_agents(raw.get("agents", [])),
            task_modules=self._parse_task_modules(raw.get("task_modules", [])),
            task_modules_heading=str(raw.get("task_modules_heading", "Task modules")),
            task_modules_intro=str(raw.get("task_modules_intro", "")),
            task_modules_router_enabled=self._as_bool(
                raw.get("task_modules_router_enabled", True),
                "task_modules_router_enabled",
            ),
            skill_entrypoint_max_bytes=self._as_optional_positive_int(
                raw.get("skill_entrypoint_max_bytes"),
                "skill_entrypoint_max_bytes",
            ),
            skill_loading_units=self._parse_skill_loading_units(
                raw.get("skill_loading_units", [])
            ),
            instruction_chains=self._parse_instruction_chains(
                raw.get("instruction_chains", [])
            ),
            reference_docs=self._parse_reference_docs(raw.get("reference_docs", [])),
            reference_docs_heading=str(
                raw.get("reference_docs_heading", "Reference docs")
            ),
            reference_docs_intro=str(raw.get("reference_docs_intro", "")),
            rule_index_enabled=self._as_bool(
                raw.get("rule_index_enabled", False), "rule_index_enabled"
            ),
            rule_index_heading=str(raw.get("rule_index_heading", "Rule index")),
            rule_index_intro=str(raw.get("rule_index_intro", "")),
            rule_index_pointer=str(raw.get("rule_index_pointer", "")),
            rule_index_target=self._parse_optional_target(raw.get("rule_index_target")),
            default_max_bytes=self._as_optional_positive_int(
                raw.get("max_bytes"), "max_bytes"
            ),
            strict_rule_labels=self._as_bool(
                raw.get("strict_rule_labels", False), "strict_rule_labels"
            ),
        )

        self._resolve_descriptions(config)
        validate_loading_units(
            config.skill_loading_units,
            (module.id for module in config.task_modules),
        )
        self._validate_instruction_chains(config)
        return config

    def _resolve_root(self, raw: dict[str, Any]) -> Path:
        if "root" in raw:
            raise ConfigurationError(
                f"{self.config_path} declares the key 'root', which is retired. "
                "The paths of the configuration file resolve against the root of "
                "the command: --root, then EUTAXIS_ROOT, then the nearest "
                "folder above the current one that holds config/tools/eutaxis.yml "
                "or eutaxis.yml, then the current folder. Remove the key. To "
                "install project-scope Skills into another project, pass "
                "--target-project to the skills subcommands."
            )
        if self.root is not None:
            return self.root
        return settings_root(self.config_path)

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
            max_bytes=self._as_optional_positive_int(raw.get("max_bytes"), "max_bytes"),
        )

    def _parse_optional_target(self, raw: Any) -> TargetConfig | None:
        if raw is None:
            return None
        return self._parse_target(raw)

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
                raise ConfigurationError(f"Duplicate task_module id: {module.id}")
            seen.add(module.id)
            modules.append(module)
        return modules

    def _parse_task_module(self, raw: Any) -> TaskModule:
        if not isinstance(raw, dict):
            raise ConfigurationError(f"Invalid task_module specification: {raw!r}")
        for required in ("id", "title", "path", "trigger"):
            if required not in raw:
                raise ConfigurationError(
                    f"task_module entries must specify '{required}'"
                )

        description = raw.get("description")
        return TaskModule(
            id=str(raw["id"]),
            title=str(raw["title"]),
            path=Path(str(raw["path"])),
            trigger=str(raw["trigger"]),
            description=str(description) if description is not None else None,
        )

    def _parse_skill_loading_units(self, raw_units: Any) -> list[SkillLoadingUnit]:
        if raw_units is None:
            return []
        if not isinstance(raw_units, list):
            raise ConfigurationError("skill_loading_units must be a list")

        loading_units: list[SkillLoadingUnit] = []
        seen_casefolded: set[str] = set()
        for raw in raw_units:
            if not isinstance(raw, dict):
                raise ConfigurationError(f"Invalid skill loading unit: {raw!r}")
            for required in ("name", "max_bytes"):
                if required not in raw:
                    raise ConfigurationError(
                        "skill_loading_units entries must specify " f"'{required}'"
                    )
            name = str(raw["name"])
            folded_name = name.casefold()
            if folded_name in seen_casefolded:
                raise ConfigurationError(f"Duplicate skill loading unit name: {name}")
            if not is_safe_slug(name):
                raise ConfigurationError(
                    f"Invalid skill loading unit name {name!r}; expected a safe "
                    "lowercase slug"
                )
            seen_casefolded.add(folded_name)
            members = self._parse_skill_loading_members(raw.get("members", []), name)
            includes = self._as_tuple(raw.get("includes", ()))
            if not members and not includes:
                raise ConfigurationError(
                    f"Skill loading unit '{name}' must declare " "members or includes"
                )
            if len(set(includes)) != len(includes):
                raise ConfigurationError(
                    f"Skill loading unit '{name}' includes another unit "
                    "more than once"
                )
            loading_units.append(
                SkillLoadingUnit(
                    name=name,
                    max_bytes=self._as_positive_int(
                        raw["max_bytes"],
                        f"skill_loading_units[{name}].max_bytes",
                    ),
                    members=members,
                    includes=includes,
                    publish_to=(
                        str(raw["publish_to"])
                        if raw.get("publish_to") is not None
                        else None
                    ),
                )
            )
        return loading_units

    def _parse_skill_loading_members(
        self, raw_members: Any, unit_name: str
    ) -> tuple[SkillLoadingMember, ...]:
        if not isinstance(raw_members, list):
            raise ConfigurationError(
                f"Members of skill loading unit '{unit_name}' " "must be a list"
            )
        members: list[SkillLoadingMember] = []
        seen: set[str] = set()
        for raw in raw_members:
            if not isinstance(raw, dict) or "module" not in raw:
                raise ConfigurationError(
                    f"Members of skill loading unit '{unit_name}' "
                    "must be mappings with a 'module' key"
                )
            module = str(raw["module"])
            if module in seen:
                raise ConfigurationError(
                    f"Skill loading unit '{unit_name}' declares "
                    f"module '{module}' more than once"
                )
            seen.add(module)
            rules = self._as_tuple(raw.get("rules", ()))
            if len(set(rules)) != len(rules):
                raise ConfigurationError(
                    f"Skill loading unit '{unit_name}' declares a "
                    f"rule of module '{module}' more than once"
                )
            members.append(
                SkillLoadingMember(
                    module=module,
                    rules=rules,
                    include_entrypoint=self._as_bool(
                        raw.get("include_entrypoint", True),
                        f"skill_loading_units[{unit_name}]."
                        f"members[{module}].include_entrypoint",
                    ),
                )
            )
        return tuple(members)

    def _parse_instruction_chains(self, raw_chains: Any) -> list[InstructionChain]:
        if raw_chains is None:
            return []
        if not isinstance(raw_chains, list):
            raise ConfigurationError("instruction_chains must be a list")

        chains: list[InstructionChain] = []
        seen: set[str] = set()
        for raw in raw_chains:
            if not isinstance(raw, dict):
                raise ConfigurationError(
                    f"Invalid instruction chain specification: {raw!r}"
                )
            for required in ("name", "agent", "sources", "max_bytes"):
                if required not in raw:
                    raise ConfigurationError(
                        "instruction_chains entries must specify " f"'{required}'"
                    )
            name = str(raw["name"])
            if name in seen:
                raise ConfigurationError(f"Duplicate instruction chain name: {name}")
            seen.add(name)
            raw_sources = raw["sources"]
            if not isinstance(raw_sources, list) or not raw_sources:
                raise ConfigurationError(
                    f"Instruction chain '{name}' must declare sources"
                )
            chains.append(
                InstructionChain(
                    name=name,
                    agent=str(raw["agent"]),
                    sources=tuple(Path(str(path)) for path in raw_sources),
                    max_bytes=self._as_positive_int(
                        raw["max_bytes"],
                        f"instruction_chains[{name}].max_bytes",
                    ),
                )
            )
        return chains

    def _validate_instruction_chains(self, config: InstructionConfig) -> None:
        agent_names = {agent.name for agent in config.agents}
        for chain in config.instruction_chains:
            if chain.agent not in agent_names:
                raise ConfigurationError(
                    f"Instruction chain '{chain.name}' references unknown "
                    f"agent: {chain.agent}"
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
                raise ConfigurationError(f"Duplicate reference_doc id: {doc.id}")
            seen.add(doc.id)
            docs.append(doc)
        return docs

    def _parse_reference_doc(self, raw: Any) -> ReferenceDoc:
        if not isinstance(raw, dict):
            raise ConfigurationError(f"Invalid reference_doc specification: {raw!r}")
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

    def _resolve_descriptions(self, config: InstructionConfig) -> None:
        """Fill task-module descriptions from each file's frontmatter."""
        resolved: list[TaskModule] = []
        for module in config.task_modules:
            if module.description is None:
                description = self._read_frontmatter_description(config, module.path)
                if description is None:
                    raise ConfigurationError(
                        f"task_module '{module.id}' has no description: "
                        f"set it in the config or in the frontmatter of "
                        f"{module.path}"
                    )
                module = TaskModule(
                    id=module.id,
                    title=module.title,
                    path=module.path,
                    trigger=module.trigger,
                    description=description,
                )
            resolved.append(module)
        config.task_modules = resolved

    def _read_frontmatter_description(
        self, config: InstructionConfig, path: Path
    ) -> str | None:
        resolved_path = config.resolve(path)
        if not resolved_path.is_file():
            return None
        try:
            frontmatter = parse_frontmatter(resolved_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ConfigurationError(
                f"Invalid frontmatter in {resolved_path}: {exc}"
            ) from exc
        description = frontmatter.get("description")
        if description is None:
            return None
        return str(description)

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

    def _as_optional_positive_int(self, value: Any, field: str) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigurationError(
                f"Field '{field}' must be a positive integer, got {value!r}"
            )
        if value <= 0:
            raise ConfigurationError(f"Field '{field}' must be positive")
        return value

    def _as_positive_int(self, value: Any, field: str) -> int:
        parsed = self._as_optional_positive_int(value, field)
        if parsed is None:
            raise ConfigurationError(f"Field '{field}' must be a positive integer")
        return parsed

    def _as_non_negative_int(self, value: Any, field: str) -> int:
        if not isinstance(value, int):
            raise ConfigurationError(
                f"Field '{field}' must be an integer, got {value!r}"
            )
        if value < 0:
            raise ConfigurationError(f"Field '{field}' must be non-negative")
        return value


CONFIG_FILENAME = "eutaxis.yml"
"""File name of the configuration file of Eutaxis."""

CONFIG_SEARCH_PATHS: tuple[Path, ...] = (
    Path("config") / "tools" / CONFIG_FILENAME,
    Path(CONFIG_FILENAME),
)
"""Places of the configuration file below the root. At most one of them may exist."""

ROOT_ENV_VAR = "EUTAXIS_ROOT"
"""Environment variable that names the root when ``--root`` is absent."""


def resolve_root(
    root: Path | None = None,
    *,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Return the root of a command, from the first source that gives one.

    The sources are tried in this order:

    1. ``root``, the value of ``--root``;
    2. the environment variable ``EUTAXIS_ROOT``, when set and not empty;
    3. the nearest ancestor of the current folder, the folder itself
       included, that holds a configuration file at one of ``CONFIG_SEARCH_PATHS``;
    4. the current folder.

    Parameters
    ----------
    root : Path, optional
        Root given on the command line, relative to the current folder.
    cwd : Path, optional
        Current folder. Default: the working directory of the process.
    environ : Mapping[str, str], optional
        Environment variables. Default: ``os.environ``.

    Returns
    -------
    Path
        Absolute root folder.
    """
    current = (cwd or Path.cwd()).expanduser().resolve()
    if root is not None:
        return _absolute(root, current)
    variable = (os.environ if environ is None else environ).get(ROOT_ENV_VAR, "")
    if variable:
        return _absolute(Path(variable), current)
    for folder in (current, *current.parents):
        if any((folder / place).is_file() for place in CONFIG_SEARCH_PATHS):
            return folder
    return current


def settings_root(config_path: Path) -> Path:
    """Return the root implied by the place of a configuration file.

    A file in ``config/tools/`` implies the folder that holds ``config/``;
    any other file implies its own folder. ``load_config`` uses this root
    when its caller gives none; the command line always passes the root
    that ``resolve_root`` returns.
    """
    folder = config_path.expanduser().resolve().parent
    if folder.name == "tools" and folder.parent.name == "config":
        return folder.parent.parent
    return folder


def find_config(config: Path | None, root: Path) -> Path:
    """Return the configuration file that a command reads.

    Parameters
    ----------
    config : Path, optional
        Path given with ``--config``. When set, it is returned resolved
        against the current folder, without any lookup; ``load_config``
        reports it when it does not exist.
    root : Path
        Root folder of the project. Without ``config``, the configuration file is
        ``config/tools/eutaxis.yml`` or ``eutaxis.yml`` below this folder.

    Returns
    -------
    Path
        Absolute path of the configuration file.

    Raises
    ------
    ConfigurationError
        When ``config`` is absent and either both places or no place below
        ``root`` holds a configuration file. Eutaxis has no built-in defaults:
        every source and every output is declared in the configuration file.
    """
    if config is not None:
        return config.expanduser().resolve()
    base = root.expanduser().resolve()
    candidates = [base / relative for relative in CONFIG_SEARCH_PATHS]
    present = [candidate for candidate in candidates if candidate.is_file()]
    if len(present) > 1:
        raise ConfigurationError(
            "Two configuration files compete: "
            + " and ".join(str(path) for path in present)
            + ". Keep one of them."
        )
    if present:
        return present[0]
    searched = " or ".join(str(candidate) for candidate in candidates)
    raise ConfigurationError(
        f"No configuration file at {searched}. Eutaxis has no built-in defaults: "
        "create the file (eutaxis init scaffolds one), or pass --config or --root."
    )


def load_config(config_path: Path, root: Path | None = None) -> InstructionConfig:
    """Load instruction configuration from disk.

    Parameters
    ----------
    config_path : Path
        Configuration file.
    root : Path, optional
        Folder against which the relative paths of the file resolve.
        Default: ``settings_root(config_path)``.
    """
    return ConfigLoader(config_path, root=root).load()


def _absolute(path: Path, base: Path) -> Path:
    """Return ``path`` made absolute against ``base``, without symbolic links."""
    path = path.expanduser()
    return (path if path.is_absolute() else base / path).resolve()
