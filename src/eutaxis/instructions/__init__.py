"""Composable instruction-file generation for AI coding agents."""

from .config import ConfigLoader, load_config
from .exceptions import (
    BudgetExceededError,
    ConfigurationError,
    InstructionError,
    SourceNotFoundError,
)
from .generator import InstructionGenerator
from .markdown import MarkdownAssembler
from .models import (
    AgentConfig,
    InstructionConfig,
    Section,
    SourceFile,
    TargetConfig,
    TaskModule,
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
    "Section",
    "SourceFile",
    "SourceNotFoundError",
    "TargetConfig",
    "TaskModule",
    "load_config",
]
