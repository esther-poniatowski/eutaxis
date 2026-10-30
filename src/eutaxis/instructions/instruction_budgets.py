"""Measure and enforce generated instruction-file budgets."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping

from .exceptions import (
    BudgetExceededError,
    InstructionChainBudgetExceededError,
    SourceNotFoundError,
)
from .models import AgentConfig, InstructionChain, InstructionConfig


SEPARATOR_BYTES = len("\n\n".encode("utf-8"))


def target_budget_measurement(
    config: InstructionConfig,
    agent: AgentConfig,
    content: str,
) -> tuple[AgentConfig, int, int | None]:
    """Return one generated target, its byte size, and its budget."""
    return agent, len(content.encode("utf-8")), config.budget_for(agent)


def enforce_target_budget(
    config: InstructionConfig,
    agent: AgentConfig,
    content: str,
) -> None:
    """Raise when one generated target exceeds its configured budget."""
    _, size, limit = target_budget_measurement(config, agent, content)
    if limit is not None and size > limit:
        raise BudgetExceededError(agent.name, size, limit)


def instruction_chain_size(
    config: InstructionConfig,
    chain: InstructionChain,
    outputs: Mapping[str, str],
) -> int:
    """Measure one cumulative output with its project instruction sources."""
    size = len(outputs[chain.agent].encode("utf-8"))
    for source in chain.sources:
        source_path = config.resolve(source)
        if not source_path.is_file():
            raise SourceNotFoundError(source_path)
        size += SEPARATOR_BYTES + len(source_path.read_bytes())
    return size


def instruction_chain_budget_report(
    config: InstructionConfig,
    outputs: Mapping[str, str],
) -> Iterator[tuple[InstructionChain, int, int]]:
    """Yield the size and limit of each chain represented in ``outputs``."""
    for chain in config.instruction_chains:
        if chain.agent in outputs:
            yield chain, instruction_chain_size(config, chain, outputs), chain.max_bytes


def enforce_instruction_chain_budgets(
    config: InstructionConfig,
    outputs: Mapping[str, str],
    selected: Iterable[AgentConfig],
) -> None:
    """Raise when a selected cumulative instruction chain exceeds its budget."""
    selected_names = {agent.name for agent in selected}
    for chain, size, limit in instruction_chain_budget_report(config, outputs):
        if chain.agent in selected_names and size > limit:
            raise InstructionChainBudgetExceededError(chain.name, size, limit)
