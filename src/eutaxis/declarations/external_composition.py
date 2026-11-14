"""Compose authenticated external resolutions without exposing their registries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple, NoReturn

from ._authority import IdentityAuthorityStore, identity_value_state
from .catalog import (
    DeclarationCatalog,
    _issued_catalog_state,
    build_declaration_catalog,
)
from .composition import (
    CumulativeArtifact,
    CumulativeCompositionPlan,
    PlannedComponent,
    assemble_cumulative_artifact,
    plan_cumulative_composition,
)
from .exceptions import AcquisitionContractError
from .models import CumulativeMarkdownProfile
from .external_resolution import (
    ExternalResolutionResult,
    _ExternalResolutionState,
    _issued_external_resolution_state,
)
from .markdown_projection import _render_cumulative_markdown


class _ExternalPlanState(NamedTuple):
    """Bind one public plan projection to its external resolution."""

    resolution: ExternalResolutionResult
    resolution_state: _ExternalResolutionState
    plan: CumulativeCompositionPlan
    plan_state: object


class _ExternalArtifactState(NamedTuple):
    """Bind one public artifact projection to its authenticated plan."""

    plan: ExternalCumulativeCompositionPlan
    plan_state: _ExternalPlanState
    artifact: CumulativeArtifact
    artifact_state: object
    contributors: tuple[str, ...]


class ExternalCumulativeCompositionPlan:
    """Expose an authenticated cumulative plan without its private registry."""

    __slots__ = ("__weakref__", "_token")

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("external composition plans must be issued")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("external composition plans cannot be subclassed")

    @property
    def manifest(self) -> str:
        """Return the authenticated composition-manifest identifier."""
        return _issued_external_plan_state(self).plan.manifest

    @property
    def scope(self) -> str:
        """Return the authenticated artifact scope."""
        return _issued_external_plan_state(self).plan.scope

    @property
    def target(self) -> str:
        """Return the authenticated artifact target."""
        return _issued_external_plan_state(self).plan.target

    @property
    def components(self) -> tuple[PlannedComponent, ...]:
        """Return the authenticated component order."""
        return _issued_external_plan_state(self).plan.components

    def __copy__(self) -> NoReturn:
        raise TypeError("external composition plans cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("external composition plans cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("external composition plans cannot be serialized")

    def __reduce_ex__(self, _protocol: object) -> NoReturn:
        raise TypeError("external composition plans cannot be serialized")


class ExternalCumulativeArtifact:
    """Expose cumulative bytes that remain bound to external authority."""

    __slots__ = ("__weakref__", "_token")

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("external cumulative artifacts must be issued")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("external cumulative artifacts cannot be subclassed")

    @property
    def manifest(self) -> str:
        """Return the authenticated composition-manifest identifier."""
        return _issued_external_artifact_state(self).artifact.manifest

    @property
    def scope(self) -> str:
        """Return the authenticated artifact scope."""
        return _issued_external_artifact_state(self).artifact.scope

    @property
    def target(self) -> str:
        """Return the authenticated artifact target."""
        return _issued_external_artifact_state(self).artifact.target

    @property
    def content(self) -> bytes:
        """Return the authenticated canonical artifact bytes."""
        return _issued_external_artifact_state(self).artifact.content

    @property
    def text(self) -> str:
        """Decode the authenticated canonical bytes as strict UTF-8."""
        return self.content.decode("utf-8", errors="strict")

    @property
    def contributors(self) -> tuple[str, ...]:
        """Return declarations that supplied the artifact's visible content."""
        return _issued_external_artifact_state(self).contributors

    def __copy__(self) -> NoReturn:
        raise TypeError("external cumulative artifacts cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("external cumulative artifacts cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("external cumulative artifacts cannot be serialized")

    def __reduce_ex__(self, _protocol: object) -> NoReturn:
        raise TypeError("external cumulative artifacts cannot be serialized")


_EXTERNAL_PLAN_AUTHORITIES: IdentityAuthorityStore[object] = IdentityAuthorityStore()
_EXTERNAL_ARTIFACT_AUTHORITIES: IdentityAuthorityStore[object] = (
    IdentityAuthorityStore()
)


def plan_external_cumulative_composition(
    resolution: ExternalResolutionResult,
) -> ExternalCumulativeCompositionPlan:
    """Plan one external cumulative unit through its private registry."""
    resolution_state = _issued_external_resolution_state(resolution)
    registry = resolution_state.acquisition_state.external_registry_state.registry
    plan: CumulativeCompositionPlan | None = None
    try:
        plan = plan_cumulative_composition(registry, resolution_state.resolution.unit)
    except BaseException as error:
        _raise_changed_resolution(resolution, resolution_state, error)
        raise
    try:
        _require_same_resolution(resolution, resolution_state)
        return _issue_external_plan(
            resolution,
            resolution_state,
            plan,
        )
    except BaseException as error:
        _raise_changed_resolution(resolution, resolution_state, error)
        raise


def assemble_external_cumulative_artifact(
    plan: ExternalCumulativeCompositionPlan,
    fragments: Mapping[str, str],
) -> ExternalCumulativeArtifact:
    """Assemble one external plan while rechecking its complete authority."""
    plan_state = _issued_external_plan_state(plan)
    artifact: CumulativeArtifact | None = None
    try:
        artifact = assemble_cumulative_artifact(plan_state.plan, fragments)
    except BaseException as error:
        _raise_changed_plan(plan, plan_state, error)
        raise
    try:
        _require_same_plan(plan, plan_state)
        return _issue_external_artifact(
            plan,
            plan_state,
            artifact,
            tuple(component.declaration for component in plan_state.plan.components),
        )
    except BaseException as error:
        _raise_changed_plan(plan, plan_state, error)
        raise


def render_external_cumulative_markdown(
    plan: ExternalCumulativeCompositionPlan,
    *,
    profile: CumulativeMarkdownProfile = CumulativeMarkdownProfile.AUDITABLE,
) -> ExternalCumulativeArtifact:
    """Render one external cumulative plan for a declared consumer profile."""
    plan_state = _issued_external_plan_state(plan)
    acquisition = plan_state.resolution_state.acquisition
    catalog = build_declaration_catalog(acquisition)
    catalog_state = _issued_catalog_state(catalog)
    rendered = None
    try:
        rendered = _render_cumulative_markdown(
            catalog,
            plan_state.resolution_state.resolution.unit,
            plan_state.plan,
            profile,
        )
    except BaseException as error:
        _raise_changed_plan(plan, plan_state, error)
        _raise_changed_catalog(catalog, catalog_state, error)
        raise
    try:
        _require_same_plan(plan, plan_state)
        _require_same_catalog(catalog, catalog_state)
        return _issue_external_artifact(
            plan,
            plan_state,
            rendered.artifact,
            rendered.contributors,
        )
    except BaseException as error:
        _raise_changed_plan(plan, plan_state, error)
        _raise_changed_catalog(catalog, catalog_state, error)
        raise


def _issue_external_plan(
    resolution: ExternalResolutionResult,
    resolution_state: _ExternalResolutionState,
    plan: CumulativeCompositionPlan,
) -> ExternalCumulativeCompositionPlan:
    result = object.__new__(ExternalCumulativeCompositionPlan)
    state = _ExternalPlanState(
        resolution,
        resolution_state,
        plan,
        identity_value_state(plan),
    )
    try:
        token = _EXTERNAL_PLAN_AUTHORITIES.issue(result, state)
        object.__setattr__(result, "_token", token)
        _issued_external_plan_state(result)
        return result
    except BaseException:
        _EXTERNAL_PLAN_AUTHORITIES.retire(result)
        raise


def _issue_external_artifact(
    plan: ExternalCumulativeCompositionPlan,
    plan_state: _ExternalPlanState,
    artifact: CumulativeArtifact,
    contributors: tuple[str, ...],
) -> ExternalCumulativeArtifact:
    result = object.__new__(ExternalCumulativeArtifact)
    state = _ExternalArtifactState(
        plan,
        plan_state,
        artifact,
        identity_value_state(artifact),
        contributors,
    )
    try:
        token = _EXTERNAL_ARTIFACT_AUTHORITIES.issue(result, state)
        object.__setattr__(result, "_token", token)
        _issued_external_artifact_state(result)
        return result
    except BaseException:
        _EXTERNAL_ARTIFACT_AUTHORITIES.retire(result)
        raise


def _issued_external_plan_state(result: object) -> _ExternalPlanState:
    try:
        return _authenticate_external_plan_state(result)
    except BaseException:
        _EXTERNAL_PLAN_AUTHORITIES.retire(result)
        raise


def _authenticate_external_plan_state(result: object) -> _ExternalPlanState:
    if type(result) is not ExternalCumulativeCompositionPlan:
        _fail("$", "external composition plan is not issued here")
    issued = _EXTERNAL_PLAN_AUTHORITIES.lookup(result)
    if issued is None or getattr(result, "_token", None) is not issued[0]:
        _fail("$", "external composition plan is not issued here")
    state = issued[1]
    if type(state) is not _ExternalPlanState:
        _fail("$", "external composition plan is not issued here")
    _require_same_resolution(state.resolution, state.resolution_state)
    if identity_value_state(state.plan) != state.plan_state:
        _fail("$", "external composition plan state changed")
    return state


def _issued_external_artifact_state(result: object) -> _ExternalArtifactState:
    try:
        return _authenticate_external_artifact_state(result)
    except BaseException:
        _EXTERNAL_ARTIFACT_AUTHORITIES.retire(result)
        raise


def _authenticate_external_artifact_state(result: object) -> _ExternalArtifactState:
    if type(result) is not ExternalCumulativeArtifact:
        _fail("$", "external cumulative artifact is not issued here")
    issued = _EXTERNAL_ARTIFACT_AUTHORITIES.lookup(result)
    if issued is None or getattr(result, "_token", None) is not issued[0]:
        _fail("$", "external cumulative artifact is not issued here")
    state = issued[1]
    if type(state) is not _ExternalArtifactState:
        _fail("$", "external cumulative artifact is not issued here")
    _require_same_plan(state.plan, state.plan_state)
    if identity_value_state(state.artifact) != state.artifact_state:
        _fail("$", "external cumulative artifact state changed")
    return state


def _require_same_resolution(
    resolution: ExternalResolutionResult,
    expected: _ExternalResolutionState,
) -> None:
    if _issued_external_resolution_state(resolution) is not expected:
        _fail("$", "external resolution authority state changed")


def _require_same_plan(
    plan: ExternalCumulativeCompositionPlan,
    expected: _ExternalPlanState,
) -> None:
    if _issued_external_plan_state(plan) is not expected:
        _fail("$", "external composition authority state changed")


def _require_same_catalog(catalog: DeclarationCatalog, expected: object) -> None:
    if _issued_catalog_state(catalog) is not expected:
        _fail("$", "declaration catalog authority state changed")


def _raise_changed_resolution(
    resolution: ExternalResolutionResult,
    expected: _ExternalResolutionState,
    error: BaseException,
) -> None:
    try:
        _require_same_resolution(resolution, expected)
    except BaseException as authority_error:
        raise authority_error from error


def _raise_changed_plan(
    plan: ExternalCumulativeCompositionPlan,
    expected: _ExternalPlanState,
    error: BaseException,
) -> None:
    try:
        _require_same_plan(plan, expected)
    except BaseException as authority_error:
        raise authority_error from error


def _raise_changed_catalog(
    catalog: DeclarationCatalog,
    expected: object,
    error: BaseException,
) -> None:
    try:
        _require_same_catalog(catalog, expected)
    except BaseException as authority_error:
        raise authority_error from error


def _fail(location: str, message: str) -> NoReturn:
    raise AcquisitionContractError(location, message)
