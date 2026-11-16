"""Render authenticated structured rule-set plans as bounded Agent Skills."""

from __future__ import annotations

from types import MappingProxyType

from ..commands.adapters import AgentAdapter
from ..commands.models import RenderedArtifact, SkillRenderInput
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
        catalog_view = _AuthenticatedCatalogView(
            declarations=state.catalog.declarations,
            contracts=state.catalog.contracts,
        )
        source = SkillRenderInput(
            name=state.manifest.target,
            description=state.rule_set.purpose,
            scope=host_scope(state.manifest.scope),
            invocation=state.manifest.invocation,
            entrypoint_body=_render_rule_skill_body(
                catalog_view,
                state.rule_set,
                state.rules,
                state.projections,
            ),
            contract_file=None,
            resources=(),
            adapter_passthrough=MappingProxyType({}),
        )
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
