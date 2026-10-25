"""Derive declared enforcement classes from exact evaluator contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Mapping, TypeAlias

from .models import (
    AnyDeclaration,
    EvaluatorDeclaration,
    OperationDeclaration,
    ProcedureDeclaration,
    RuleDeclaration,
    VersionedReference,
)


class EnforcementClass(StrEnum):
    """The closed declared enforcement classes for evaluator-backed work."""

    MECHANICAL = "mechanical"
    ASSISTED = "assisted"
    DELIBERATIVE = "deliberative"


class PredicatePhase(StrEnum):
    """The authored phase of one procedure predicate."""

    PRECONDITION = "precondition"
    INVARIANT = "invariant"
    POSTCONDITION = "postcondition"


@dataclass(frozen=True)
class RuleCriterionEnforcement:
    """One rule-local criterion and its declared enforcement class."""

    declaration: str
    criterion: str
    evaluator: VersionedReference
    enforcement: EnforcementClass


@dataclass(frozen=True)
class ProcedurePredicateEnforcement:
    """One evaluator-backed procedure predicate and its declared class."""

    declaration: str
    phase: PredicatePhase
    predicate: str
    evaluator: VersionedReference
    enforcement: EnforcementClass


@dataclass(frozen=True)
class OperationPredicateEnforcement:
    """One exact operation precondition and its declared enforcement class."""

    operation: VersionedReference
    predicate: str
    evaluator: VersionedReference
    enforcement: EnforcementClass


EnforcementLocator: TypeAlias = (
    RuleCriterionEnforcement
    | ProcedurePredicateEnforcement
    | OperationPredicateEnforcement
)


class EnforcementClassificationError(ValueError):
    """Report an evaluator contract outside the closed class mapping."""


@dataclass(frozen=True)
class _EnforcementRecordSource:
    """Read-only declaration values needed by canonical enumeration."""

    declarations: Mapping[str, AnyDeclaration]
    operations: tuple[tuple[VersionedReference, OperationDeclaration], ...]
    evaluator: Callable[[VersionedReference], EvaluatorDeclaration]


def derive_enforcement_class(
    evaluator: EvaluatorDeclaration,
) -> EnforcementClass:
    """Derive one declared class without claiming evaluator readiness."""
    capabilities = (
        evaluator.evaluator_kind,
        evaluator.coverage,
        evaluator.adjudication,
    )
    if capabilities == ("checker", "total", "authoritative"):
        if evaluator.known_failure_fixtures and evaluator.residual_question is None:
            return EnforcementClass.MECHANICAL
    elif capabilities == ("detector", "partial", "candidate"):
        if (
            evaluator.residual_question is not None
            and not evaluator.known_failure_fixtures
        ):
            return EnforcementClass.ASSISTED
    elif capabilities == ("manual", "none", "manual"):
        if evaluator.residual_question is None and not evaluator.known_failure_fixtures:
            return EnforcementClass.DELIBERATIVE
    raise EnforcementClassificationError(
        f"evaluator {evaluator.id!r}@{evaluator.version} has no admitted "
        "enforcement class"
    )


def _enumerate_enforcement(
    source: _EnforcementRecordSource,
) -> tuple[EnforcementLocator, ...]:
    """Enumerate every authored evaluator-backed obligation canonically."""
    locators: list[EnforcementLocator] = []
    for identifier, declaration in sorted(source.declarations.items()):
        if isinstance(declaration, RuleDeclaration):
            for criterion in declaration.criteria:
                enforcement = derive_enforcement_class(
                    source.evaluator(criterion.evaluator)
                )
                locators.append(
                    RuleCriterionEnforcement(
                        identifier,
                        criterion.id,
                        criterion.evaluator,
                        enforcement,
                    )
                )
        elif isinstance(declaration, ProcedureDeclaration):
            phases = (
                (PredicatePhase.PRECONDITION, declaration.preconditions),
                (PredicatePhase.INVARIANT, declaration.invariants),
                (PredicatePhase.POSTCONDITION, declaration.postconditions),
            )
            for phase, predicates in phases:
                for predicate in predicates:
                    if predicate.evaluator is None:
                        continue
                    enforcement = derive_enforcement_class(
                        source.evaluator(predicate.evaluator)
                    )
                    locators.append(
                        ProcedurePredicateEnforcement(
                            identifier,
                            phase,
                            predicate.id,
                            predicate.evaluator,
                            enforcement,
                        )
                    )

    for operation_reference, operation in source.operations:
        for predicate in operation.preconditions:
            if predicate.evaluator is None:
                continue
            enforcement = derive_enforcement_class(
                source.evaluator(predicate.evaluator)
            )
            locators.append(
                OperationPredicateEnforcement(
                    operation_reference,
                    predicate.id,
                    predicate.evaluator,
                    enforcement,
                )
            )
    return tuple(locators)
