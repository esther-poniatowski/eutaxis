"""Plan one authenticated structured rule-set Skill."""

from __future__ import annotations

from typing import NamedTuple, NoReturn, SupportsIndex, cast

from ..skill_placement import SkillPlacementCandidate, validate_skill_placement
from ._authority import IdentityAuthorityStore, identity_value_state
from .catalog import (
    DeclarationCatalog,
    _CatalogAuthorityState,
    _issued_catalog_state,
    build_declaration_catalog,
)
from .composition import _stable_dependency_order
from .exceptions import CompositionError
from .external_resolution import (
    ExternalResolutionResult,
    _ExternalResolutionState,
    _issued_external_resolution_state,
)
from .external_result import (
    _authenticated_external_result_operation_from_state,
    _register_provisional_authority,
)
from .models import (
    CompositionManifestDeclaration,
    RuleDeclaration,
    RuleSetDeclaration,
)
from .resolution import ResolvedRuleProjection
from ._structured_skill_common import (
    is_one_line_description as _is_one_line_description,
    raise_changed_catalog as _raise_changed_catalog,
    record_error as _record_error,
    require_manifest as _require_manifest,
    require_same_inputs as _require_same_inputs,
    require_same_resolution_owner as _require_same_resolution_owner,
)


class _StructuredRuleSkillPlanState(NamedTuple):
    """Retain the complete authority graph behind one rule-set Skill plan."""

    resolution: ExternalResolutionResult
    resolution_state: _ExternalResolutionState
    catalog: DeclarationCatalog
    catalog_state: _CatalogAuthorityState
    manifest: CompositionManifestDeclaration
    rule_set: RuleSetDeclaration
    rules: tuple[RuleDeclaration, ...]
    projections: tuple[ResolvedRuleProjection, ...]
    projection_state: object


class StructuredRuleSkillPlan:
    """Expose one authenticated rule set and its effective projections."""

    __slots__ = ("__weakref__", "_token")

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("structured rule Skill plans must be issued")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("structured rule Skill plans cannot be subclassed")

    @property
    def manifest(self) -> CompositionManifestDeclaration:
        """Return the exact separate-directory manifest."""
        return _issued_structured_rule_skill_plan_state(self).manifest

    @property
    def name(self) -> str:
        """Return the authenticated Skill name."""
        return self.manifest.target

    @property
    def scope(self) -> str:
        """Return the authenticated installation scope."""
        return self.manifest.scope

    @property
    def invocation(self) -> tuple[str, ...]:
        """Return the authenticated invocation routes."""
        return self.manifest.invocation

    @property
    def rule_set(self) -> RuleSetDeclaration:
        """Return the exact selected root rule set."""
        return _issued_structured_rule_skill_plan_state(self).rule_set

    @property
    def rules(self) -> tuple[RuleDeclaration, ...]:
        """Return every effective member in authored order."""
        return _issued_structured_rule_skill_plan_state(self).rules

    @property
    def projections(self) -> tuple[ResolvedRuleProjection, ...]:
        """Return each member's exact effective projection."""
        return _issued_structured_rule_skill_plan_state(self).projections

    def __copy__(self) -> NoReturn:
        raise TypeError("structured rule Skill plans cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("structured rule Skill plans cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("structured rule Skill plans cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("structured rule Skill plans cannot be serialized")


_STRUCTURED_RULE_SKILL_PLAN_AUTHORITIES: IdentityAuthorityStore[object] = (
    IdentityAuthorityStore()
)


def plan_structured_rule_skill(
    resolution: ExternalResolutionResult,
) -> StructuredRuleSkillPlan:
    """Close one resolved rule set over exact effective member projections."""
    resolution_state = _issued_external_resolution_state(resolution)
    return _authenticated_external_result_operation_from_state(
        resolution_state.acquisition,
        resolution_state.acquisition_state,
        lambda: _plan_structured_rule_skill(resolution, resolution_state),
        lambda result: _validate_plan_success(result, resolution, resolution_state),
        lambda _error: _require_same_resolution_owner(resolution, resolution_state),
    )


def _plan_structured_rule_skill(
    resolution: ExternalResolutionResult,
    resolution_state: _ExternalResolutionState,
) -> StructuredRuleSkillPlan:
    """Plan one rule-set Skill inside an exact acquisition operation."""
    catalog = build_declaration_catalog(resolution_state.acquisition)
    catalog_state = _issued_catalog_state(catalog)
    try:
        return _plan_from_catalog(
            resolution,
            resolution_state,
            catalog,
            catalog_state,
        )
    except BaseException as error:
        _raise_changed_catalog(catalog, catalog_state, error)
        raise


def _plan_from_catalog(
    resolution: ExternalResolutionResult,
    resolution_state: _ExternalResolutionState,
    catalog: DeclarationCatalog,
    catalog_state: _CatalogAuthorityState,
) -> StructuredRuleSkillPlan:
    """Close one rule-set plan over an authenticated catalog."""
    manifest_record = resolution_state.resolution.manifest_record
    manifest = _require_manifest(manifest_record)
    selected = tuple(
        identifier
        for section in manifest.sections
        for identifier in section.declarations
    )
    if len(selected) != 1:
        _record_error(
            manifest_record,
            ("sections",),
            "separate-directory manifest must select exactly one root rule set",
        )
    root_record = catalog.get(selected[0])
    if root_record is None or not isinstance(
        root_record.declaration, RuleSetDeclaration
    ):
        _record_error(
            manifest_record,
            ("sections",),
            f"selected root {selected[0]!r} is not a rule set",
        )
    rule_set = cast(RuleSetDeclaration, root_record.declaration)
    if not _is_one_line_description(rule_set.purpose):
        _record_error(
            root_record,
            ("purpose",),
            "rule-set purpose is not a one-line Skill description of at most 1024 characters",
        )
    rules, projections = _close_members(
        resolution_state,
        catalog,
        manifest,
        rule_set,
    )
    candidates: list[SkillPlacementCandidate] = []
    for rule in rules:
        member_record = catalog.get(rule.id)
        if member_record is None:
            raise CompositionError("$.components", f"missing member {rule.id!r}")
        candidates.append(
            SkillPlacementCandidate(
                identifier=rule.id,
                source=str(member_record.source.path),
                failure_mode=rule.failure_mode,
                required_visibility=rule.required_visibility,
            )
        )
    validate_skill_placement(tuple(candidates), manifest.invocation)
    return _issue_plan(
        resolution,
        resolution_state,
        catalog,
        catalog_state,
        manifest,
        rule_set,
        rules,
        projections,
    )


def _close_members(
    resolution_state: _ExternalResolutionState,
    catalog: DeclarationCatalog,
    manifest: CompositionManifestDeclaration,
    rule_set: RuleSetDeclaration,
) -> tuple[tuple[RuleDeclaration, ...], tuple[ResolvedRuleProjection, ...]]:
    """Require exact effective membership and dependency-safe authored order."""
    unit = resolution_state.resolution.unit
    authored = tuple(rule.id for rule in rule_set.rules)
    components = {component.declaration: component for component in unit.components}
    if set(components) != set(authored) or len(components) != len(authored):
        raise CompositionError(
            "$.components",
            "effective components must equal the root rule-set members",
        )
    section_order = {
        section.id: index for index, section in enumerate(manifest.sections)
    }
    ordered = _stable_dependency_order(components, unit.dependencies, section_order)
    if ordered != authored:
        raise CompositionError(
            "$.dependencies",
            "resolved dependency order must equal rule-set authored order",
        )
    projections_by_id = {
        projection.declaration: projection for projection in unit.rule_projections
    }
    projections = tuple(projections_by_id[identifier] for identifier in authored)
    rules: list[RuleDeclaration] = []
    for identifier, authored_rule in zip(authored, rule_set.rules, strict=True):
        record = catalog.get(identifier)
        if (
            record is None
            or record.containing_rule_set != rule_set.id
            or record.declaration is not authored_rule
        ):
            raise CompositionError(
                "$.components",
                f"rule-set member {identifier!r} changed",
            )
        rules.append(authored_rule)
    return tuple(rules), projections


def _issue_plan(
    resolution: ExternalResolutionResult,
    resolution_state: _ExternalResolutionState,
    catalog: DeclarationCatalog,
    catalog_state: _CatalogAuthorityState,
    manifest: CompositionManifestDeclaration,
    rule_set: RuleSetDeclaration,
    rules: tuple[RuleDeclaration, ...],
    projections: tuple[ResolvedRuleProjection, ...],
) -> StructuredRuleSkillPlan:
    result = object.__new__(StructuredRuleSkillPlan)
    state = _StructuredRuleSkillPlanState(
        resolution,
        resolution_state,
        catalog,
        catalog_state,
        manifest,
        rule_set,
        rules,
        projections,
        _projection_state(manifest, rule_set, rules, projections),
    )
    try:
        token = _STRUCTURED_RULE_SKILL_PLAN_AUTHORITIES.issue(result, state)
        object.__setattr__(result, "_token", token)
        _issued_structured_rule_skill_plan_state(result)
        _register_provisional_authority(
            resolution_state.acquisition,
            result,
            lambda: _STRUCTURED_RULE_SKILL_PLAN_AUTHORITIES.retire(result),
        )
        return result
    except BaseException:
        _STRUCTURED_RULE_SKILL_PLAN_AUTHORITIES.retire(result)
        raise


def _validate_plan_success(
    result: StructuredRuleSkillPlan,
    resolution: ExternalResolutionResult,
    resolution_state: _ExternalResolutionState,
) -> None:
    """Authenticate one returned plan after its lease is revoked."""
    state = _issued_structured_rule_skill_plan_state(result)
    if (
        state.resolution is not resolution
        or state.resolution_state is not resolution_state
    ):
        raise CompositionError(
            "$", "structured rule Skill plan belongs to another resolution"
        )


def _issued_structured_rule_skill_plan_state(
    plan: object,
) -> _StructuredRuleSkillPlanState:
    """Authenticate one rule-set plan and every retained authority."""
    try:
        state = _structured_rule_skill_plan_authority_state(plan)
        _require_same_inputs(
            state.resolution,
            state.resolution_state,
            state.catalog,
            state.catalog_state,
        )
        if (
            _projection_state(
                state.manifest,
                state.rule_set,
                state.rules,
                state.projections,
            )
            != state.projection_state
        ):
            raise CompositionError("$", "structured rule Skill plan state changed")
        if (
            state.resolution_state.resolution.manifest_record.declaration
            is not state.manifest
        ):
            raise CompositionError(
                "$.manifest", "structured rule Skill manifest changed"
            )
        root_record = state.catalog.get(state.rule_set.id)
        if root_record is None or root_record.declaration is not state.rule_set:
            raise CompositionError("$.rule-set", "structured rule Skill root changed")
        for index, rule in enumerate(state.rules):
            record = state.catalog.get(rule.id)
            if record is None or record.declaration is not rule:
                raise CompositionError(
                    f"$.rules[{index}]",
                    "structured rule Skill member changed",
                )
        return state
    except BaseException:
        _STRUCTURED_RULE_SKILL_PLAN_AUTHORITIES.retire(plan)
        raise


def _structured_rule_skill_plan_authority_state(
    plan: object,
) -> _StructuredRuleSkillPlanState:
    """Return one plan's private state without traversing its owners."""
    if type(plan) is not StructuredRuleSkillPlan:
        raise CompositionError("$", "structured rule Skill plan is not issued here")
    issued = _STRUCTURED_RULE_SKILL_PLAN_AUTHORITIES.lookup(plan)
    if issued is None or getattr(plan, "_token", None) is not issued[0]:
        raise CompositionError("$", "structured rule Skill plan is not issued here")
    state = issued[1]
    if type(state) is not _StructuredRuleSkillPlanState:
        raise CompositionError("$", "structured rule Skill plan is not issued here")
    return state


def _projection_state(
    manifest: CompositionManifestDeclaration,
    rule_set: RuleSetDeclaration,
    rules: tuple[RuleDeclaration, ...],
    projections: tuple[ResolvedRuleProjection, ...],
) -> object:
    """Snapshot every public projection field."""
    return tuple(
        identity_value_state(value)
        for value in (manifest, rule_set, rules, projections)
    )
