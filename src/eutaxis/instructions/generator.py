"""Instruction-file generation and stale-output checks."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Iterator

from .exceptions import (
    BudgetExceededError,
    ConfigurationError,
    RejectedLabelError,
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
from .rules import LABEL_PATTERN, RejectedLabel, parse_module
from .scanner import declared_sources


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
        """Write selected outputs and return their paths.

        Raises
        ------
        RejectedLabelError
            When the configuration sets ``strict_rule_labels`` and a declared
            module holds a rejected label line. Nothing is written.
        BudgetExceededError
            When ``enforce_budget`` is set and an output exceeds its budget.
        """
        self.enforce_rule_labels()
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

        if agent_name is None:
            standalone = self.render_standalone_rule_index()
            if standalone is not None:
                index_path, index_content = standalone
                paths.append(index_path)
                if not dry_run:
                    index_path.parent.mkdir(parents=True, exist_ok=True)
                    index_path.write_text(index_content, encoding="utf-8")

        return paths

    def rejected_labels(self) -> list[tuple[Path, RejectedLabel]]:
        """Return the label-shaped lines that the label grammar rejects.

        Every module declared by the configuration is parsed whole, as the
        rule index scans it: ``common_sources``, ``task_modules`` and the
        ``sources`` of each agent. A rejected line defines no label, so the
        rule index, the rule query and progressive disclosure all omit it. A
        declared module missing on disk is skipped here; generation reports
        it.
        """
        found: list[tuple[Path, RejectedLabel]] = []
        for path in dict.fromkeys(path for path, _ in declared_sources(self.config)):
            if not path.is_file():
                continue
            parsed = parse_module(path.read_text(encoding="utf-8"), module=path.stem)
            found.extend((path, rejection) for rejection in parsed.rejected)
        return found

    def enforce_rule_labels(self) -> None:
        """Raise when ``strict_rule_labels`` is set and a label line is rejected.

        Raises
        ------
        RejectedLabelError
            Listing the location of every rejected line.
        """
        if not self.config.strict_rule_labels:
            return
        rejected = self.rejected_labels()
        if rejected:
            raise RejectedLabelError(
                [f"{path}:{item.line_number}" for path, item in rejected]
            )

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
        if not modules or not self.config.task_modules_router_enabled:
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
        description = (module.description or "").strip()
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

    _label_pattern = LABEL_PATTERN

    def _render_rule_index(self, agent: AgentConfig) -> str:
        """Render the rule-index section for inclusion inside an agent output."""
        if not self.config.rule_index_enabled:
            return ""

        if self.config.rule_index_target is not None:
            pointer = self.config.rule_index_pointer.strip()
            if not pointer:
                return ""
            return f"## {self.config.rule_index_heading}\n\n{pointer}"

        target_dir = self.config.resolve(agent.target.path).parent
        entries = self._scan_rule_index_entries(target_dir)
        if not entries:
            return ""

        return self._render_rule_index_section(entries)

    def render_standalone_rule_index(self) -> tuple[Path, str] | None:
        """Return (path, content) for the standalone rule-index file, if any."""
        if not self.config.rule_index_enabled:
            return None
        target = self.config.rule_index_target
        if target is None:
            return None

        target_path = self.config.resolve(target.path)
        entries = self._scan_rule_index_entries(target_path.parent)
        if not entries:
            return None

        parts: list[str] = []
        if target.header:
            parts.append(target.header.strip())
        parts.append(self._render_rule_index_section(entries))
        if target.footer:
            parts.append(target.footer.strip())
        return target_path, "\n\n".join(parts).rstrip() + "\n"

    def _scan_rule_index_entries(
        self, target_dir: Path
    ) -> list[tuple[str, list[str]]]:
        scan_paths: list[Path] = []
        for source in self.config.common_sources:
            scan_paths.append(self.config.resolve(source.path))
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
        return entries

    def _render_rule_index_section(
        self, entries: list[tuple[str, list[str]]]
    ) -> str:
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
