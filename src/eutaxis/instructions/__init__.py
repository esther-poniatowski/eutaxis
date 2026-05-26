"""Composable instruction-file generation for AI coding agents."""

from .config import ConfigLoader, load_config
from .exceptions import (
    BudgetExceededError,
    ConfigurationError,
    InstructionError,
    SourceNotFoundError,
)
from .generator import InstructionGenerator
from .markdown import MarkdownAssembler, parse_frontmatter
from .models import (
    AgentConfig,
    InstructionConfig,
    ReferenceDoc,
    Section,
    SourceFile,
    TargetConfig,
    TaskModule,
)
from .scanner import (
    ScanReport,
    collect_registered_paths,
    format_registration_snippet,
    scan_instructions,
)

__all__ = [
    "AgentConfig",
    "BudgetExceededError",
    "ConfigLoader",
    "ConfigurationError",
    "InstructionConfig",
    "InstructionError",
    "InstructionGenerator",
    "MarkdownAssembler",
    "ReferenceDoc",
    "ScanReport",
    "Section",
    "SourceFile",
    "SourceNotFoundError",
    "TargetConfig",
    "TaskModule",
    "collect_registered_paths",
    "format_registration_snippet",
    "load_config",
    "parse_frontmatter",
    "scan_instructions",
]
