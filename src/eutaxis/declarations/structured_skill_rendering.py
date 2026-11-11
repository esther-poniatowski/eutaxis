"""Render authenticated structured procedure plans as bounded Agent Skills."""

from __future__ import annotations

from types import MappingProxyType

from ..commands.adapters import AgentAdapter
from ..commands.models import ArtifactFile, RenderedArtifact, SkillRenderInput
from ..commands.rendering import ENTRYPOINT_FILENAME, assemble_skill
from .exceptions import CompositionError
from .markdown_projection import _render_procedure
from .structured_skill import (
    StructuredSkillPlan,
    _StructuredSkillPlanState,
    _issued_structured_skill_plan_state,
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
    state = _issued_structured_skill_plan_state(plan)
    _require_positive_budget(entrypoint_max_bytes, "entrypoint-max-bytes")
    _require_positive_budget(artifact_max_bytes, "artifact-max-bytes")
    try:
        source = _render_input(state)
        artifact = assemble_skill(source, adapter)
        _check_budgets(
            artifact,
            entrypoint_max_bytes=entrypoint_max_bytes,
            artifact_max_bytes=artifact_max_bytes,
        )
    except BaseException as error:
        _raise_changed_plan(plan, state, error)
        raise
    if _issued_structured_skill_plan_state(plan) is not state:
        raise CompositionError("$", "structured Skill plan authority changed")
    return artifact


def _render_input(state: _StructuredSkillPlanState) -> SkillRenderInput:
    """Project one authenticated plan into the shared artifact input."""
    contract = (
        "# Complete procedure contract\n\n"
        + _render_procedure(
            state.catalog,
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


def _host_scope(scope: str) -> str:
    """Translate declaration scope into the established adapter vocabulary."""
    if scope == "personal":
        return "user"
    if scope == "project":
        return scope
    raise CompositionError("$.manifest.scope", f"unsupported Skill scope {scope!r}")


def _check_budgets(
    artifact: RenderedArtifact,
    *,
    entrypoint_max_bytes: int,
    artifact_max_bytes: int,
) -> None:
    """Enforce both limits on the final host-specific artifact bytes."""
    entrypoint = next(
        file for file in artifact.files if file.relative_path == ENTRYPOINT_FILENAME
    )
    entrypoint_bytes = len(entrypoint.content.encode("utf-8", errors="strict"))
    if entrypoint_bytes > entrypoint_max_bytes:
        raise CompositionError(
            "$.budgets.entrypoint-max-bytes",
            f"SKILL.md uses {entrypoint_bytes} bytes, limit is {entrypoint_max_bytes}",
        )
    artifact_bytes = sum(
        len(file.content.encode("utf-8", errors="strict")) for file in artifact.files
    )
    if artifact_bytes > artifact_max_bytes:
        raise CompositionError(
            "$.budgets.artifact-max-bytes",
            f"complete artifact uses {artifact_bytes} bytes, limit is {artifact_max_bytes}",
        )


def _require_positive_budget(value: object, field: str) -> None:
    """Require one exact positive integer budget."""
    if type(value) is not int or value <= 0:
        raise CompositionError(
            f"$.budgets.{field}",
            "budget must be an exact positive integer",
        )


def _raise_changed_plan(
    plan: StructuredSkillPlan,
    expected: _StructuredSkillPlanState,
    error: BaseException,
) -> None:
    """Give plan-authority failure precedence over a rendering failure."""
    try:
        current = _issued_structured_skill_plan_state(plan)
    except BaseException as authority_error:
        raise authority_error from error
    if current is not expected:
        raise CompositionError(
            "$", "structured Skill plan authority changed"
        ) from error
