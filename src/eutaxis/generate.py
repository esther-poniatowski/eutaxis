"""
Compatibility interface for instruction-file generation.

New code should import from ``eutaxis.instructions``. This module preserves the
initial ``eutaxis.generate`` API used by existing tests, scripts, and project
configs.
"""

from __future__ import annotations

from pathlib import Path

from .instructions import (
    AgentConfig,
    ConfigLoader,
    ConfigurationError,
    InstructionConfig,
    InstructionError,
    InstructionGenerator,
    MarkdownAssembler,
    Section,
    SourceFile,
    SourceNotFoundError,
    TargetConfig,
    load_config,
)

__all__ = [
    "AgentConfig",
    "ConfigLoader",
    "ConfigurationError",
    "InstructionConfig",
    "InstructionError",
    "InstructionGenerator",
    "MarkdownAssembler",
    "Section",
    "SourceFile",
    "SourceNotFoundError",
    "TargetConfig",
    "load_config",
    "main",
]


def main(config_path: Path) -> int:
    """Compatibility entry point used by older ``eutaxis generate`` calls."""
    try:
        config = load_config(config_path)
        generator = InstructionGenerator(config)
        paths = generator.write_all()
    except InstructionError as exc:
        print(f"Error: {exc}")
        return exc.exit_code

    print(f"Generated {len(paths)} instruction file(s):")
    for path in paths:
        print(f"  - {path}")
    return 0
