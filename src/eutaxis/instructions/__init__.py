"""Composable instruction-file generation for AI coding agents."""

from .config import ConfigLoader, load_config
from .exceptions import ConfigurationError, InstructionError, SourceNotFoundError
from .generator import InstructionGenerator
from .markdown import MarkdownAssembler
from .models import AgentConfig, InstructionConfig, Section, SourceFile, TargetConfig

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
]
