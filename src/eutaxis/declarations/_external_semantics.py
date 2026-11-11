"""Validate source authority and reference syntax before registry construction."""

from __future__ import annotations

from typing import NoReturn

from .acquisition_contract import _identifier_value, _namespace_value
from .exceptions import AcquisitionContractError
from .loader import LoadedDeclarationSource
from .models import (
    AnyDeclaration,
    CompositionManifestDeclaration,
    OperationDeclaration,
    Predicate,
    ProcedureDeclaration,
    ResolutionPolicyDeclaration,
    RuleDeclaration,
    RuleSetDeclaration,
    VersionedReference,
)
from .source import DocumentPath, format_document_path


def _validate_external_declaration_semantics(
    source: LoadedDeclarationSource,
    namespace: str,
    location: str,
) -> None:
    """Validate one parsed source against its acquisition namespace."""
    _validate_declaration(source.declaration, namespace, location, ())


def _validate_declaration(
    declaration: AnyDeclaration,
    namespace: str,
    location: str,
    root: DocumentPath,
) -> None:
    """Validate one top-level or embedded declaration and every reference."""
    identifier_path = root + ("id",)
    identifier = _identifier_value(
        declaration.id,
        _location(location, identifier_path),
    )
    if identifier.partition("/")[0] != namespace:
        _fail(
            _location(location, identifier_path),
            "declaration identifier namespace differs from source namespace",
        )
    owner_path = root + ("owner",)
    owner = _namespace_value(declaration.owner, _location(location, owner_path))
    if owner != namespace:
        _fail(
            _location(location, owner_path),
            "declaration owner differs from source namespace",
        )
    for index, relation in enumerate(declaration.relations):
        _validate_identifier(
            relation.target,
            location,
            root + ("relations", index, "target"),
        )

    if isinstance(declaration, RuleDeclaration):
        _validate_rule(declaration, location, root)
    elif isinstance(declaration, RuleSetDeclaration):
        for index, rule in enumerate(declaration.rules):
            _validate_declaration(
                rule,
                namespace,
                location,
                root + ("rules", index),
            )
    elif isinstance(declaration, ProcedureDeclaration):
        _validate_procedure(declaration, location, root)
    elif isinstance(declaration, OperationDeclaration):
        _validate_predicates(
            declaration.preconditions,
            location,
            root + ("preconditions",),
        )
        for index, support in enumerate(declaration.support_resources):
            _validate_identifier(
                support.resource,
                location,
                root + ("support-resources", index, "resource"),
            )
    elif isinstance(declaration, ResolutionPolicyDeclaration):
        _validate_policy(declaration, location, root)
    elif isinstance(declaration, CompositionManifestDeclaration):
        _validate_manifest(declaration, location, root)


def _validate_rule(
    rule: RuleDeclaration,
    location: str,
    root: DocumentPath,
) -> None:
    """Validate every evaluator reference owned by one rule."""
    for index, criterion in enumerate(rule.criteria):
        _validate_versioned_reference(
            criterion.evaluator,
            location,
            root + ("criteria", index, "evaluator"),
        )
    for index, identifier in enumerate(rule.decided_by):
        _validate_identifier(identifier, location, root + ("decided-by", index))


def _validate_procedure(
    procedure: ProcedureDeclaration,
    location: str,
    root: DocumentPath,
) -> None:
    """Validate every evaluator and operation reference in one procedure."""
    for field in ("preconditions", "invariants", "postconditions"):
        _validate_predicates(
            getattr(procedure, field),
            location,
            root + (field,),
        )
    for index, action in enumerate(procedure.actions):
        _validate_versioned_reference(
            action.operation,
            location,
            root + ("actions", index, "operation"),
        )


def _validate_predicates(
    predicates: tuple[Predicate, ...],
    location: str,
    root: DocumentPath,
) -> None:
    """Validate every present evaluator reference in one predicate sequence."""
    for index, predicate in enumerate(predicates):
        if predicate.evaluator is not None:
            _validate_versioned_reference(
                predicate.evaluator,
                location,
                root + (index, "evaluator"),
            )


def _validate_policy(
    policy: ResolutionPolicyDeclaration,
    location: str,
    root: DocumentPath,
) -> None:
    """Validate every present strategy reference and conflict member."""
    strategy = policy.strategy
    for field, value in (
        ("retain", strategy.retain),
        ("replace", strategy.replace),
        ("with", strategy.replacement),
        ("result", strategy.result),
    ):
        if value is not None:
            _validate_identifier(value, location, root + ("strategy", field))
    for index, identifier in enumerate(policy.conflicts):
        _validate_identifier(identifier, location, root + ("conflicts", index))


def _validate_manifest(
    manifest: CompositionManifestDeclaration,
    location: str,
    root: DocumentPath,
) -> None:
    """Validate every declaration and policy selected by one manifest."""
    for section_index, section in enumerate(manifest.sections):
        for declaration_index, identifier in enumerate(section.declarations):
            _validate_identifier(
                identifier,
                location,
                root
                + (
                    "sections",
                    section_index,
                    "declarations",
                    declaration_index,
                ),
            )
    for index, identifier in enumerate(manifest.policies):
        _validate_identifier(identifier, location, root + ("policies", index))


def _validate_versioned_reference(
    reference: VersionedReference,
    location: str,
    root: DocumentPath,
) -> None:
    """Validate the identifier part of one schema-validated exact reference."""
    _validate_identifier(reference.id, location, root + ("id",))


def _validate_identifier(
    identifier: str,
    location: str,
    path: DocumentPath,
) -> None:
    """Apply the one canonical external identifier grammar at one field."""
    _identifier_value(identifier, _location(location, path))


def _location(base: str, path: DocumentPath) -> str:
    """Join a contract source location to one declaration document path."""
    return base + format_document_path(path).removeprefix("$")


def _fail(location: str, message: str) -> NoReturn:
    raise AcquisitionContractError(location, message)
