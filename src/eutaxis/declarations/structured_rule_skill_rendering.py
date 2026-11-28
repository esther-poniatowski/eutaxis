"""Render authenticated structured rule-set plans as bounded Agent Skills."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

from ..commands.adapters import AgentAdapter
from ..commands.models import (
    CommandSource,
    RenderedArtifact,
    SkillRenderInput,
    TargetsSpec,
)
from ..commands.rendering import assemble_skill
from ._structured_skill_rendering_common import (
    check_budgets,
    host_scope,
    require_positive_budget,
)
from .catalog import _AuthenticatedCatalogView
from .exceptions import CompositionError
from .external_result import _authenticated_external_result_operation
from .markdown_projection import _render_rule_skill_body
from .structured_rule_skill import (
    StructuredRuleSkillPlan,
    _StructuredRuleSkillPlanState,
    _issued_structured_rule_skill_plan_state,
    _structured_rule_skill_plan_authority_state,
)

def render_structured_rule_skill(
    plan: StructuredRuleSkillPlan,
    adapter: AgentAdapter,
    *,
    entrypoint_max_bytes: int,
    artifact_max_bytes: int,
) -> RenderedArtifact:
    """Render one issued rule-set plan within final host-byte limits."""
    state = _structured_rule_skill_plan_authority_state(plan)
    return _authenticated_external_result_operation(
        state.resolution_state.acquisition,
        lambda: _render_operation(
            plan,
            state,
            adapter,
            entrypoint_max_bytes=entrypoint_max_bytes,
            artifact_max_bytes=artifact_max_bytes,
        ),
    )


def _render_operation(
    plan: StructuredRuleSkillPlan,
    expected: _StructuredRuleSkillPlanState,
    adapter: AgentAdapter,
    *,
    entrypoint_max_bytes: int,
    artifact_max_bytes: int,
) -> RenderedArtifact:
    """Render one rule-set artifact inside an exact acquisition operation."""
    state = _issued_structured_rule_skill_plan_state(plan)
    if state is not expected:
        raise CompositionError("$", "structured rule Skill plan authority changed")
    try:
        require_positive_budget(entrypoint_max_bytes, "entrypoint-max-bytes")
        require_positive_budget(artifact_max_bytes, "artifact-max-bytes")
        source = _project_skill_input(state)
        artifact = assemble_skill(source, adapter)
        check_budgets(
            artifact,
            entrypoint_max_bytes=entrypoint_max_bytes,
            artifact_max_bytes=artifact_max_bytes,
        )
    except BaseException as error:
        _raise_changed_plan(plan, state, error)
        raise
    _require_same_plan(plan, state)
    return artifact


def configured_rule_skill_source(
    plan: StructuredRuleSkillPlan, source_path: Path
) -> CommandSource:
    """Project a rule Skill into the source shared by configured Skill commands."""
    expected = _structured_rule_skill_plan_authority_state(plan)
    return _authenticated_external_result_operation(
        expected.resolution_state.acquisition,
        lambda: _configured_source_operation(plan, expected, source_path),
    )


def _configured_source_operation(
    plan: StructuredRuleSkillPlan,
    expected: _StructuredRuleSkillPlanState,
    source_path: Path,
) -> CommandSource:
    """Project an issued rule-set plan while its acquisition is authoritative."""
    state = _issued_structured_rule_skill_plan_state(plan)
    if state is not expected:
        raise CompositionError("$", "structured rule Skill plan authority changed")
    try:
        source = _project_skill_input(state)
        silent = any(rule.failure_mode == "silent" for rule in state.rules)
        result = CommandSource(
            name=source.name,
            description=source.description,
            invocation=source.invocation,
            failure_mode="silent" if silent else "visible",
            required_visibility="pre-action" if silent else None,
            scope_default=source.scope,
            targets=TargetsSpec(),
            action=None,
            body=source.entrypoint_body,
            source_path=source_path,
            layer="config",
            literal_body=True,
        )
    except BaseException as error:
        _raise_changed_plan(plan, state, error)
        raise
    _require_same_plan(plan, state)
    return result


def _project_skill_input(state: _StructuredRuleSkillPlanState) -> SkillRenderInput:
    """Produce the literal body and activation metadata of one rule Skill."""
    catalog = _AuthenticatedCatalogView(
        declarations=state.catalog.declarations,
        contracts=state.catalog.contracts,
    )
    return SkillRenderInput(
        name=state.manifest.target,
        description=state.rule_set.purpose,
        scope=host_scope(state.manifest.scope),
        invocation=state.manifest.invocation,
        entrypoint_body=_render_rule_skill_body(
            catalog,
            state.rule_set,
            state.rules,
            state.projections,
        ),
        contract_file=None,
        resources=(),
        adapter_passthrough=MappingProxyType({}),
    )


def _require_same_plan(
    plan: StructuredRuleSkillPlan,
    expected: _StructuredRuleSkillPlanState,
) -> None:
    """Require one rule-set plan to retain its exact issued state."""
    if _issued_structured_rule_skill_plan_state(plan) is not expected:
        raise CompositionError("$", "structured rule Skill plan authority changed")


def _raise_changed_plan(
    plan: StructuredRuleSkillPlan,
    expected: _StructuredRuleSkillPlanState,
    error: BaseException,
) -> None:
    """Give plan-authority failure precedence over a rendering failure."""
    try:
        _require_same_plan(plan, expected)
    except BaseException as authority_error:
        raise authority_error from error
