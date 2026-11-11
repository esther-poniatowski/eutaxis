"""Plan one authenticated structured procedure Skill and its resource closure."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple, NoReturn, SupportsIndex, cast

from ..names import is_portable_skill_name
from ._authority import IdentityAuthorityStore, identity_value_state
from .byte_carriers import VerifiedByteCarrier
from .catalog import (
    DeclarationCatalog,
    _CatalogAuthorityState,
    _issued_catalog_state,
    build_declaration_catalog,
)
from .exceptions import CompositionError
from .external_resolution import (
    ExternalResolutionResult,
    _ExternalResolutionState,
    _issued_external_resolution_state,
)
from .external_result import AcquiredResource
from .models import (
    CompositionMechanism,
    CompositionManifestDeclaration,
    DeclarationKind,
    OperationDeclaration,
    ProcedureDeclaration,
    VersionedReference,
)
from .registry import RegisteredDeclaration
from .source import DocumentPath, format_document_path, nearest_location

_RESERVED_DESTINATIONS = frozenset(
    {
        "SKILL.md",
        ".eutaxis-owned.json",
        "agents/openai.yaml",
        "references/contract.md",
    }
)
_MAX_DESCRIPTION_CHARACTERS = 1024


@dataclass(frozen=True)
class PlannedSupportResource:
    """Bind one operation dependency to exact acquired bytes and a destination."""

    operation: VersionedReference
    resource: AcquiredResource
    destination: str


class _StructuredSkillPlanState(NamedTuple):
    """Retain the complete authority graph behind one public Skill plan."""

    resolution: ExternalResolutionResult
    resolution_state: _ExternalResolutionState
    catalog: DeclarationCatalog
    catalog_state: _CatalogAuthorityState
    manifest: CompositionManifestDeclaration
    procedure: ProcedureDeclaration
    operation_references: tuple[VersionedReference, ...]
    operations: tuple[OperationDeclaration, ...]
    support_resources: tuple[PlannedSupportResource, ...]
    resource_evidence: tuple[VerifiedByteCarrier, ...]
    projection_state: object


class StructuredSkillPlan:
    """Expose an authenticated structured procedure and resource closure."""

    __slots__ = ("__weakref__", "_token")

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("structured Skill plans must be issued")

    def __init_subclass__(cls, **_kwargs: object) -> NoReturn:
        raise TypeError("structured Skill plans cannot be subclassed")

    @property
    def manifest(self) -> CompositionManifestDeclaration:
        """Return the exact separate-directory manifest."""
        return _issued_structured_skill_plan_state(self).manifest

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
    def procedure(self) -> ProcedureDeclaration:
        """Return the exact selected root procedure."""
        return _issued_structured_skill_plan_state(self).procedure

    @property
    def operations(self) -> tuple[OperationDeclaration, ...]:
        """Return exact operations in first action-reference order."""
        return _issued_structured_skill_plan_state(self).operations

    @property
    def support_resources(self) -> tuple[PlannedSupportResource, ...]:
        """Return the authenticated operation-owned resource closure."""
        return _issued_structured_skill_plan_state(self).support_resources

    def __copy__(self) -> NoReturn:
        raise TypeError("structured Skill plans cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("structured Skill plans cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("structured Skill plans cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("structured Skill plans cannot be serialized")


_STRUCTURED_SKILL_PLAN_AUTHORITIES: IdentityAuthorityStore[object] = (
    IdentityAuthorityStore()
)


def plan_structured_skill(
    resolution: ExternalResolutionResult,
) -> StructuredSkillPlan:
    """Close one resolved procedure over exact operations and support resources."""
    resolution_state = _issued_external_resolution_state(resolution)
    catalog = build_declaration_catalog(resolution_state.acquisition)
    catalog_state = _issued_catalog_state(catalog)
    try:
        manifest_record = resolution_state.resolution.manifest_record
        manifest = _require_manifest(manifest_record)
        procedure_record = _require_root_procedure(
            catalog,
            manifest_record,
            manifest,
            resolution_state,
        )
        procedure = cast(ProcedureDeclaration, procedure_record.declaration)
        operation_references, operations = _resolve_operations(catalog, procedure)
        support_resources, evidence = _close_support_resources(
            resolution_state,
            operation_references,
            operations,
            catalog,
        )
        _require_same_inputs(resolution, resolution_state, catalog, catalog_state)
        return _issue_structured_skill_plan(
            resolution,
            resolution_state,
            catalog,
            catalog_state,
            manifest,
            procedure,
            operation_references,
            operations,
            support_resources,
            evidence,
        )
    except BaseException as error:
        _raise_changed_inputs(
            resolution,
            resolution_state,
            catalog,
            catalog_state,
            error,
        )
        raise


def _require_manifest(
    record: RegisteredDeclaration,
) -> CompositionManifestDeclaration:
    declaration = record.declaration
    if not isinstance(declaration, CompositionManifestDeclaration):
        _record_error(record, (), "resolved root is not a composition manifest")
    manifest = cast(CompositionManifestDeclaration, declaration)
    if manifest.mechanism is not CompositionMechanism.SEPARATE_DIRECTORY:
        _record_error(
            record,
            ("mechanism",),
            f"manifest mechanism {manifest.mechanism.value!r} is not separate-directory",
        )
    if not is_portable_skill_name(manifest.target):
        _record_error(
            record,
            ("target",),
            "Skill name is not one portable segment of at most 64 UTF-8 bytes",
        )
    return manifest


def _require_root_procedure(
    catalog: DeclarationCatalog,
    manifest_record: RegisteredDeclaration,
    manifest: CompositionManifestDeclaration,
    resolution_state: _ExternalResolutionState,
) -> RegisteredDeclaration:
    selected = tuple(
        identifier
        for section in manifest.sections
        for identifier in section.declarations
    )
    if len(selected) != 1:
        _record_error(
            manifest_record,
            ("sections",),
            "separate-directory manifest must select exactly one root procedure",
        )
    identifier = selected[0]
    record = catalog.get(identifier)
    if record is None or not isinstance(record.declaration, ProcedureDeclaration):
        _record_error(
            manifest_record,
            ("sections",),
            f"selected root {identifier!r} is not a procedure",
        )
    if not any(
        component.declaration == identifier
        for component in resolution_state.resolution.unit.components
    ):
        _record_error(
            manifest_record,
            ("sections",),
            f"selected procedure {identifier!r} is not effective",
        )
    procedure = cast(ProcedureDeclaration, record.declaration)
    if not _is_one_line_description(procedure.purpose):
        _record_error(
            record,
            ("purpose",),
            "procedure purpose is not a one-line Skill description of at most 1024 characters",
        )
    return record


def _is_one_line_description(value: str) -> bool:
    """Return whether one description has content and no line boundary."""
    return (
        bool(value.strip())
        and value == value.strip()
        and value.splitlines(keepends=True) == [value]
        and len(value) <= _MAX_DESCRIPTION_CHARACTERS
    )


def _resolve_operations(
    catalog: DeclarationCatalog,
    procedure: ProcedureDeclaration,
) -> tuple[tuple[VersionedReference, ...], tuple[OperationDeclaration, ...]]:
    references: list[VersionedReference] = []
    operations: list[OperationDeclaration] = []
    seen: set[tuple[str, int]] = set()
    for action_index, action in enumerate(procedure.actions):
        key = (action.operation.id, action.operation.version)
        if key in seen:
            continue
        record = catalog.get_contract(
            DeclarationKind.OPERATION,
            action.operation.id,
            action.operation.version,
        )
        if record is None or not isinstance(record.declaration, OperationDeclaration):
            raise CompositionError(
                f"$.procedure.actions[{action_index}].operation",
                f"unknown operation {action.operation.id!r}@{action.operation.version}",
            )
        operation = cast(OperationDeclaration, record.declaration)
        if operation.method is None or not operation.method.strip():
            _record_error(
                record,
                ("method",),
                "structured Skill operation requires a non-empty authored method",
            )
        seen.add(key)
        references.append(action.operation)
        operations.append(operation)
    return tuple(references), tuple(operations)


def _close_support_resources(
    resolution_state: _ExternalResolutionState,
    references: tuple[VersionedReference, ...],
    operations: tuple[OperationDeclaration, ...],
    catalog: DeclarationCatalog,
) -> tuple[tuple[PlannedSupportResource, ...], tuple[VerifiedByteCarrier, ...]]:
    acquisition_state = resolution_state.acquisition_state
    resources = {resource.id: resource for resource in acquisition_state.resources}
    evidence_by_resource = {
        resource.id: carrier for resource, carrier in acquisition_state.resource_map
    }
    planned: list[PlannedSupportResource] = []
    evidence: list[VerifiedByteCarrier] = []
    destinations: dict[str, str] = {}
    resource_destinations: dict[str, str] = {}
    for reference, operation in zip(references, operations, strict=True):
        record = catalog.get_contract(
            DeclarationKind.OPERATION,
            reference.id,
            reference.version,
        )
        assert record is not None
        for index, support in enumerate(operation.support_resources):
            resource = resources.get(support.resource)
            carrier = evidence_by_resource.get(support.resource)
            if resource is None or carrier is None:
                _record_error(
                    record,
                    ("support-resources", index, "resource"),
                    f"unknown acquired resource {support.resource!r}",
                )
            if any(
                _artifact_paths_collide(support.destination, reserved)
                for reserved in _RESERVED_DESTINATIONS
            ):
                _record_error(
                    record,
                    ("support-resources", index, "destination"),
                    f"destination {support.destination!r} is reserved",
                )
            for prior_destination, prior_resource in destinations.items():
                if not _artifact_paths_collide(support.destination, prior_destination):
                    continue
                if support.destination == prior_destination:
                    if prior_resource != support.resource:
                        _record_error(
                            record,
                            ("support-resources", index, "destination"),
                            (
                                f"destination {support.destination!r} names "
                                "multiple resources"
                            ),
                        )
                else:
                    _record_error(
                        record,
                        ("support-resources", index, "destination"),
                        (
                            f"destination {support.destination!r} collides with "
                            f"artifact path {prior_destination!r}"
                        ),
                    )
            known_destination = resource_destinations.get(support.resource)
            if (
                known_destination is not None
                and known_destination != support.destination
            ):
                _record_error(
                    record,
                    ("support-resources", index, "destination"),
                    f"resource {support.resource!r} has multiple destinations",
                )
            destinations[support.destination] = support.resource
            resource_destinations[support.resource] = support.destination
            planned.append(
                PlannedSupportResource(reference, resource, support.destination)
            )
            evidence.append(carrier)
    return tuple(planned), tuple(evidence)


def _artifact_paths_collide(first: str, second: str) -> bool:
    """Return whether two file paths require one path to be a directory."""
    first_parts = tuple(first.split("/"))
    second_parts = tuple(second.split("/"))
    common = min(len(first_parts), len(second_parts))
    return first_parts[:common] == second_parts[:common]


def _issue_structured_skill_plan(
    resolution: ExternalResolutionResult,
    resolution_state: _ExternalResolutionState,
    catalog: DeclarationCatalog,
    catalog_state: _CatalogAuthorityState,
    manifest: CompositionManifestDeclaration,
    procedure: ProcedureDeclaration,
    operation_references: tuple[VersionedReference, ...],
    operations: tuple[OperationDeclaration, ...],
    support_resources: tuple[PlannedSupportResource, ...],
    resource_evidence: tuple[VerifiedByteCarrier, ...],
) -> StructuredSkillPlan:
    result = object.__new__(StructuredSkillPlan)
    state = _StructuredSkillPlanState(
        resolution,
        resolution_state,
        catalog,
        catalog_state,
        manifest,
        procedure,
        operation_references,
        operations,
        support_resources,
        resource_evidence,
        _plan_projection_state(manifest, procedure, operations, support_resources),
    )
    try:
        token = _STRUCTURED_SKILL_PLAN_AUTHORITIES.issue(result, state)
        object.__setattr__(result, "_token", token)
        _issued_structured_skill_plan_state(result)
        return result
    except BaseException:
        _STRUCTURED_SKILL_PLAN_AUTHORITIES.retire(result)
        raise


def _issued_structured_skill_plan_state(
    plan: object,
) -> _StructuredSkillPlanState:
    """Authenticate one Skill plan and every retained upstream authority."""
    try:
        return _authenticate_structured_skill_plan_state(plan)
    except BaseException:
        _STRUCTURED_SKILL_PLAN_AUTHORITIES.retire(plan)
        raise


def _authenticate_structured_skill_plan_state(
    plan: object,
) -> _StructuredSkillPlanState:
    if type(plan) is not StructuredSkillPlan:
        raise CompositionError("$", "structured Skill plan is not issued here")
    issued = _STRUCTURED_SKILL_PLAN_AUTHORITIES.lookup(plan)
    if issued is None or getattr(plan, "_token", None) is not issued[0]:
        raise CompositionError("$", "structured Skill plan is not issued here")
    state = issued[1]
    if type(state) is not _StructuredSkillPlanState:
        raise CompositionError("$", "structured Skill plan is not issued here")
    _require_same_inputs(
        state.resolution,
        state.resolution_state,
        state.catalog,
        state.catalog_state,
    )
    if (
        _plan_projection_state(
            state.manifest,
            state.procedure,
            state.operations,
            state.support_resources,
        )
        != state.projection_state
    ):
        raise CompositionError("$", "structured Skill plan state changed")
    current_manifest = state.resolution_state.resolution.manifest_record.declaration
    if current_manifest is not state.manifest:
        raise CompositionError("$.manifest", "structured Skill manifest changed")
    procedure_record = state.catalog.get(state.procedure.id)
    if procedure_record is None or procedure_record.declaration is not state.procedure:
        raise CompositionError("$.procedure", "structured Skill procedure changed")
    acquisition_state = state.resolution_state.acquisition_state
    acquired_evidence = {
        id(resource): carrier for resource, carrier in acquisition_state.resource_map
    }
    for index, (reference, operation) in enumerate(
        zip(state.operation_references, state.operations, strict=True)
    ):
        record = state.catalog.get_contract(
            DeclarationKind.OPERATION,
            reference.id,
            reference.version,
        )
        if record is None or record.declaration is not operation:
            raise CompositionError(
                f"$.operations[{index}]",
                "structured Skill operation changed",
            )
    if len(state.support_resources) != len(state.resource_evidence):
        raise CompositionError("$.support-resources", "resource evidence count changed")
    for index, (planned, evidence) in enumerate(
        zip(state.support_resources, state.resource_evidence, strict=True)
    ):
        if acquired_evidence.get(id(planned.resource)) is not evidence:
            raise CompositionError(
                f"$.support-resources[{index}]",
                "structured Skill resource evidence changed",
            )
    return state


def _plan_projection_state(
    manifest: CompositionManifestDeclaration,
    procedure: ProcedureDeclaration,
    operations: tuple[OperationDeclaration, ...],
    support_resources: tuple[PlannedSupportResource, ...],
) -> object:
    """Snapshot every public projection field without a temporary identity."""
    return tuple(
        identity_value_state(value)
        for value in (manifest, procedure, operations, support_resources)
    )


def _require_same_inputs(
    resolution: ExternalResolutionResult,
    resolution_state: _ExternalResolutionState,
    catalog: DeclarationCatalog,
    catalog_state: _CatalogAuthorityState,
) -> None:
    if _issued_external_resolution_state(resolution) is not resolution_state:
        raise CompositionError("$", "external resolution authority state changed")
    if _issued_catalog_state(catalog) is not catalog_state:
        raise CompositionError("$", "declaration catalog authority state changed")
    if (
        catalog_state.result is not resolution_state.acquisition
        or catalog_state.result_state is not resolution_state.acquisition_state
    ):
        raise CompositionError("$", "catalog belongs to another acquisition")


def _raise_changed_inputs(
    resolution: ExternalResolutionResult,
    resolution_state: _ExternalResolutionState,
    catalog: DeclarationCatalog,
    catalog_state: _CatalogAuthorityState,
    error: BaseException,
) -> None:
    try:
        _require_same_inputs(resolution, resolution_state, catalog, catalog_state)
    except BaseException as authority_error:
        raise authority_error from error


def _record_error(
    record: RegisteredDeclaration,
    parts: DocumentPath,
    message: str,
) -> NoReturn:
    path = record.root + parts
    source = nearest_location(record.source.locations, path)
    raise CompositionError(
        format_document_path(path),
        message,
        path=record.source.path,
        line=source.line if source else None,
        column=source.column if source else None,
    )
