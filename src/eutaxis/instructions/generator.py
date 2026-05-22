"""Instruction-file generation and stale-output checks."""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Iterator

from .exceptions import (
    BudgetExceededError,
    ConfigurationError,
    SourceNotFoundError,
)
from .markdown import MarkdownAssembler
from .models import (
    AgentConfig,
    InstructionConfig,
    ReferenceDoc,
    SourceFile,
    TaskModule,
)


class InstructionGenerator:
    """Generate, write and compare instruction outputs."""

    def __init__(
        self,
        config: InstructionConfig,
        assembler: MarkdownAssembler | None = None,
    ) -> None:
        self.config = config
        self.assembler = assembler or MarkdownAssembler()

    def generate_all(
        self,
        agent_name: str | None = None,
        enforce_budget: bool = True,
    ) -> dict[str, str]:
        """Generate content for enabled outputs."""
        outputs: dict[str, str] = {}
        for agent in self._selected_agents(agent_name):
            content = self.generate_for_agent(agent)
            if enforce_budget:
                self._enforce_budget(agent, content)
            outputs[agent.name] = content
        return outputs

    def generate_for_agent(self, agent: AgentConfig) -> str:
        """Generate content for one output."""
        parts: list[str] = []

        if agent.target.header:
            parts.append(agent.target.header.strip())

        for source in [*self.config.common_sources, *agent.sources]:
            content = self._load_source(source)
            if content:
                parts.append(content)

        router = self._render_task_module_router()
        if router:
            parts.append(router)

        reference_docs = self._render_reference_docs()
        if reference_docs:
            parts.append(reference_docs)

        rule_index = self._render_rule_index(agent)
        if rule_index:
            parts.append(rule_index)

        if agent.target.footer:
            parts.append(agent.target.footer.strip())

        return "\n\n".join(parts).rstrip() + "\n"

    def write_all(
        self,
        agent_name: str | None = None,
        dry_run: bool = False,
        enforce_budget: bool = True,
    ) -> list[Path]:
        """Write selected outputs and return their paths."""
        paths: list[Path] = []

        for agent in self._selected_agents(agent_name):
            output_path = self.config.resolve(agent.target.path)
            paths.append(output_path)

            content = self.generate_for_agent(agent)
            if enforce_budget:
                self._enforce_budget(agent, content)

            if dry_run:
                continue

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content, encoding="utf-8")

        return paths

    def diff_report(
        self,
        agent_name: str | None = None,
    ) -> Iterator[tuple[AgentConfig, Path, bool]]:
        """Yield whether each selected output differs from generated content."""
        for agent in self._selected_agents(agent_name):
            output_path = self.config.resolve(agent.target.path)
            expected = self.generate_for_agent(agent)
            existing = (
                output_path.read_text(encoding="utf-8")
                if output_path.is_file()
                else ""
            )
            yield agent, output_path, existing != expected

    def unified_diff(self, agent_name: str) -> str:
        """Return a unified diff for one output."""
        agent = self.config.get_agent(agent_name)
        if agent is None:
            raise ConfigurationError(f"Unknown agent: {agent_name}")

        output_path = self.config.resolve(agent.target.path)
        expected = self.generate_for_agent(agent)
        existing = (
            output_path.read_text(encoding="utf-8") if output_path.is_file() else ""
        )

        return "".join(
            difflib.unified_diff(
                existing.splitlines(keepends=True),
                expected.splitlines(keepends=True),
                fromfile=str(output_path),
                tofile=f"{output_path} (generated)",
            )
        )

    def _selected_agents(self, agent_name: str | None) -> list[AgentConfig]:
        if agent_name is None:
            return self.config.enabled_agents()

        agent = self.config.get_agent(agent_name)
        if agent is None:
            raise ConfigurationError(f"Unknown agent: {agent_name}")
        if not agent.enabled:
            raise ConfigurationError(f"Agent is disabled: {agent_name}")
        return [agent]

    def budget_report(
        self, agent_name: str | None = None
    ) -> Iterator[tuple[AgentConfig, int, int | None]]:
        """Yield (agent, byte_size, byte_budget) for each selected agent."""
        for agent in self._selected_agents(agent_name):
            content = self.generate_for_agent(agent)
            yield (
                agent,
                len(content.encode("utf-8")),
                self.config.budget_for(agent),
            )

    def _enforce_budget(self, agent: AgentConfig, content: str) -> None:
        limit = self.config.budget_for(agent)
        if limit is None:
            return
        size = len(content.encode("utf-8"))
        if size > limit:
            raise BudgetExceededError(agent.name, size, limit)

    def _render_task_module_router(self) -> str:
        modules = self.config.task_modules
        if not modules:
            return ""

        lines = [f"## {self.config.task_modules_heading}"]
        intro = self.config.task_modules_intro.strip()
        if intro:
            lines.extend(["", intro])

        lines.append("")
        for module in modules:
            lines.append(self._render_task_module_bullet(module))
        return "\n".join(lines)

    def _render_task_module_bullet(self, module: TaskModule) -> str:
        bullet = (
            f"- **{module.title}.** Load `{module.path}` {module.trigger.strip()}."
        )
        description = module.description.strip()
        if description:
            bullet = f"{bullet} {description}"
        return bullet

    def _render_reference_docs(self) -> str:
        docs = self.config.reference_docs
        if not docs:
            return ""

        lines = [f"## {self.config.reference_docs_heading}"]
        intro = self.config.reference_docs_intro.strip()
        if intro:
            lines.extend(["", intro])

        lines.append("")
        for doc in docs:
            lines.append(self._render_reference_doc_bullet(doc))
        return "\n".join(lines)

    _label_pattern = re.compile(r"^\*\*([a-z][a-z0-9-]*)\*\*:\s*$", re.MULTILINE)

    def _render_rule_index(self, agent: AgentConfig) -> str:
        if not self.config.rule_index_enabled:
            return ""

        scan_paths: list[Path] = []
        for source in [*self.config.common_sources, *agent.sources]:
            scan_paths.append(self.config.resolve(source.path))
        target_dir = self.config.resolve(agent.target.path).parent
        for module in self.config.task_modules:
            if module.path.is_absolute():
                scan_paths.append(module.path)
            else:
                scan_paths.append((target_dir / module.path).resolve())

        entries: list[tuple[str, list[str]]] = []
        for path in scan_paths:
            labels = self._scan_labels(path)
            if labels:
                entries.append((path.stem, labels))

        if not entries:
            return ""

        lines = [f"## {self.config.rule_index_heading}"]
        intro = self.config.rule_index_intro.strip()
        if intro:
            lines.extend(["", intro])

        lines.append("")
        for stem, labels in entries:
            lines.append(f"- **{stem}**: {', '.join(labels)}")
        return "\n".join(lines)

    def _scan_labels(self, path: Path) -> list[str]:
        if not path.is_file():
            return []
        content = path.read_text(encoding="utf-8")
        return self._label_pattern.findall(content)

    def _render_reference_doc_bullet(self, doc: ReferenceDoc) -> str:
        header = f"- **{doc.title}.** Consult {doc.trigger.strip()}."
        description = doc.description.strip()
        if description:
            header = f"{header} {description}"
        return (
            f"{header}\n"
            f"  - Local (primary): `{doc.local_path}`\n"
            f"  - GitHub (fallback): <{doc.github_url}>"
        )

    def _load_source(self, source: SourceFile) -> str:
        source_path = self.config.resolve(source.path)
        if not source_path.is_file():
            raise SourceNotFoundError(source_path)

        content = source_path.read_text(encoding="utf-8")
        return self.assembler.process(content, source)
