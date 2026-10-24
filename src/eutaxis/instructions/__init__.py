"""Composable instruction-file generation for AI coding agents."""

from .config import ConfigLoader, load_config
from .exceptions import (
    BudgetExceededError,
    ConfigurationError,
    InstructionChainBudgetExceededError,
    InstructionError,
    RejectedLabelError,
    SourceNotFoundError,
)
from .generator import InstructionGenerator
from .markdown import MarkdownAssembler, parse_frontmatter
from .models import (
    AgentConfig,
    InstructionChain,
    InstructionConfig,
    ReferenceDoc,
    Section,
    SourceFile,
    SkillLoadingUnit,
    SkillLoadingMember,
    TargetConfig,
    TaskModule,
)
from .rules import (
    LABEL_PATTERN,
    ParsedModule,
    RejectedLabel,
    Rule,
    RulePart,
    field_key,
    parse_module,
)
from .scanner import (
    ScanReport,
    collect_registered_paths,
    declared_sources,
    format_registration_snippet,
    scan_instructions,
)

__all__ = [
    "LABEL_PATTERN",
    "AgentConfig",
    "BudgetExceededError",
    "ConfigLoader",
    "ConfigurationError",
    "InstructionConfig",
    "InstructionChain",
    "InstructionChainBudgetExceededError",
    "InstructionError",
    "InstructionGenerator",
    "MarkdownAssembler",
    "ParsedModule",
    "ReferenceDoc",
    "RejectedLabel",
    "RejectedLabelError",
    "Rule",
    "RulePart",
    "ScanReport",
    "Section",
    "SourceFile",
    "SkillLoadingUnit",
    "SkillLoadingMember",
    "SourceNotFoundError",
    "TargetConfig",
    "TaskModule",
    "collect_registered_paths",
    "declared_sources",
    "field_key",
    "format_registration_snippet",
    "load_config",
    "parse_frontmatter",
    "parse_module",
    "scan_instructions",
]
