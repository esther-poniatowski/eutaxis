"""Discover instruction files and compare against a config's registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .markdown import parse_frontmatter
from .models import InstructionConfig, SourceFile


@dataclass
class ScanReport:
    """Outcome of a scan of instruction files versus a config."""

    registered_present: list[Path] = field(default_factory=list)
    unregistered_present: list[Path] = field(default_factory=list)
    registered_missing: list[Path] = field(default_factory=list)
    frontmatter_errors: list[tuple[Path, str]] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        """True when the scan found drift between disk and config."""
        return bool(
            self.unregistered_present
            or self.registered_missing
            or self.frontmatter_errors
        )


def collect_registered_paths(config: InstructionConfig) -> list[Path]:
    """Return the resolved paths of every instruction file the config registers."""
    paths: list[Path] = []
    for source in config.common_sources:
        paths.append(config.resolve(source.path))
    for module in config.task_modules:
        paths.append(config.resolve(module.path))
    return paths


def declared_sources(
    config: InstructionConfig,
) -> list[tuple[Path, SourceFile | None]]:
    """Return every module that the config declares, with its source entry.

    The modules come in configuration order: ``common_sources``, then
    ``task_modules``, then the ``sources`` of each agent. A ``task_modules``
    entry carries no section selection, so its entry is ``None``. A path
    declared several times appears once per declaration.
    """
    declared: list[tuple[Path, SourceFile | None]] = [
        (config.resolve(source.path), source) for source in config.common_sources
    ]
    declared.extend((config.resolve(module.path), None) for module in config.task_modules)
    declared.extend(
        (config.resolve(source.path), source)
        for agent in config.agents
        for source in agent.sources
    )
    return declared


def scan_instructions(
    config: InstructionConfig, root: Path | None = None
) -> ScanReport:
    """Scan instruction directories and report drift against the config.

    When ``root`` is provided, the scan walks that single directory.
    Otherwise it walks the union of parent directories of every currently
    registered file.

    A discovered file is reported as unregistered unless its frontmatter
    contains ``enabled: false`` (opt-out). Registered files that are
    missing on disk are always reported.
    """
    registered = collect_registered_paths(config)
    registered_set = {path.resolve() for path in registered}

    if root is not None:
        scan_dirs = [root.expanduser().resolve()]
    else:
        scan_dirs = sorted(
            {path.parent for path in registered if path.parent.exists()}
        )

    discovered: set[Path] = set()
    for scan_dir in scan_dirs:
        if not scan_dir.is_dir():
            continue
        for md_path in scan_dir.rglob("*.md"):
            discovered.add(md_path.resolve())

    report = ScanReport()

    for path in sorted(registered_set):
        if path.is_file():
            report.registered_present.append(path)
        else:
            report.registered_missing.append(path)

    for path in sorted(discovered - registered_set):
        try:
            frontmatter = parse_frontmatter(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            report.frontmatter_errors.append((path, str(exc)))
            continue
        if frontmatter.get("enabled", True) is False:
            continue
        report.unregistered_present.append(path)

    return report


def format_registration_snippet(
    config: InstructionConfig, paths: list[Path]
) -> str:
    """Return a YAML snippet registering the given files under ``common_sources``."""
    if not paths:
        return ""

    lines = ["common_sources:"]
    root = config.root.resolve()
    for path in paths:
        try:
            rel = path.resolve().relative_to(root)
            lines.append(f"  - path: {rel}")
        except ValueError:
            lines.append(f"  - path: {path}")
    return "\n".join(lines) + "\n"
