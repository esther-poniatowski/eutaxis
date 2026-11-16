"""Render authenticated structured procedure plans as bounded Agent Skills."""

from __future__ import annotations

from types import MappingProxyType

from ..commands.adapters import AgentAdapter
from ..commands.models import ArtifactFile, RenderedArtifact, SkillRenderInput
from ..commands.rendering import assemble_skill
from ._structured_skill_rendering_common import (
    check_budgets as _check_budgets,
    host_scope as _host_scope,
    require_positive_budget as _require_positive_budget,
)
from .catalog import _AuthenticatedCatalogView
from .exceptions import CompositionError
from .external_result import _authenticated_external_result_operation
from .markdown_projection import _render_procedure
from .structured_skill import (
    StructuredSkillPlan,
    _StructuredSkillPlanState,
    _issued_structured_skill_plan_state,
    _structured_skill_plan_authority_state,
)

CONTRACT_FILENAME = "references/contract.md"


def render_structured_skill(
    plan: StructuredSkillPlan,
    adapter: AgentAdapter,
    *,
    entrypoint_max_bytes: int,
    artifact_max_bytes: int,
) -> RenderedArtifact:
    """Render one issued plan within explicit entrypoint and artifact limits."""
    state = _structured_skill_plan_authority_state(plan)
    return _authenticated_external_result_operation(
        state.resolution_state.acquisition,
        lambda: _render_structured_skill_operation(
            plan,
            state,
            adapter,
            entrypoint_max_bytes=entrypoint_max_bytes,
            artifact_max_bytes=artifact_max_bytes,
        ),
    )


def _render_structured_skill_operation(
    plan: StructuredSkillPlan,
    expected: _StructuredSkillPlanState,
    adapter: AgentAdapter,
    *,
    entrypoint_max_bytes: int,
    artifact_max_bytes: int,
) -> RenderedArtifact:
    """Render one Skill artifact inside an exact acquisition operation."""
    state = _issued_structured_skill_plan_state(plan)
    if state is not expected:
        raise CompositionError("$", "structured Skill plan authority changed")
    try:
        _require_positive_budget(entrypoint_max_bytes, "entrypoint-max-bytes")
        _require_positive_budget(artifact_max_bytes, "artifact-max-bytes")
        catalog_view = _AuthenticatedCatalogView(
            declarations=state.catalog.declarations,
            contracts=state.catalog.contracts,
        )
        source = _render_input(state, catalog_view)
        artifact = assemble_skill(source, adapter)
        _check_budgets(
            artifact,
            entrypoint_max_bytes=entrypoint_max_bytes,
            artifact_max_bytes=artifact_max_bytes,
        )
    except BaseException as error:
        _raise_changed_plan(plan, state, error)
        raise
    _require_same_skill_plan(plan, state)
    return artifact


def _require_same_skill_plan(
    plan: StructuredSkillPlan,
    expected: _StructuredSkillPlanState,
) -> None:
    """Require one Skill plan to retain its exact issued state."""
    if _issued_structured_skill_plan_state(plan) is not expected:
        raise CompositionError("$", "structured Skill plan authority changed")


def _raise_changed_plan(
    plan: StructuredSkillPlan,
    expected: _StructuredSkillPlanState,
    error: BaseException,
) -> None:
    """Give plan-authority failure precedence over a rendering failure."""
    try:
        _require_same_skill_plan(plan, expected)
    except BaseException as authority_error:
        raise authority_error from error


def _render_input(
    state: _StructuredSkillPlanState,
    catalog_view: _AuthenticatedCatalogView,
) -> SkillRenderInput:
    """Project one authenticated plan into the shared artifact input."""
    contract = (
        "# Complete procedure contract\n\n"
        + _render_procedure(
            catalog_view,
            state.procedure,
            allow_support_resources=True,
        ).rstrip()
        + "\n"
    )
    resources = _resource_files(state)
    return SkillRenderInput(
        name=state.manifest.target,
        description=state.procedure.purpose,
        scope=_host_scope(state.manifest.scope),
        invocation=state.manifest.invocation,
        entrypoint_body=(
            f"# {state.manifest.target}\n\n"
            "Read [the complete procedure contract]"
            f"({CONTRACT_FILENAME}) before the first action. "
            "Execute that contract exactly.\n"
        ),
        contract_file=ArtifactFile(CONTRACT_FILENAME, contract),
        resources=resources,
        adapter_passthrough=MappingProxyType({}),
    )


def _resource_files(
    state: _StructuredSkillPlanState,
) -> tuple[ArtifactFile, ...]:
    """Decode each exact retained resource once and deduplicate repeated uses."""
    unique: dict[tuple[bytes, bytes], ArtifactFile] = {}
    for planned in state.support_resources:
        key = (
            planned.resource.id.encode("utf-8", errors="strict"),
            planned.destination.encode("utf-8", errors="strict"),
        )
        if key in unique:
            continue
        try:
            content = planned.resource.data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise CompositionError(
                "$.support-resources",
                f"resource {planned.resource.id!r} is not strict UTF-8",
            ) from error
        if content.encode("utf-8", errors="strict") != planned.resource.data:
            raise CompositionError(
                "$.support-resources",
                f"resource {planned.resource.id!r} changed during UTF-8 decoding",
            )
        unique[key] = ArtifactFile(planned.destination, content)
    return tuple(unique[key] for key in sorted(unique))
