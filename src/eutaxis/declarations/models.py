"""Immutable domain models for schema-validated declarations."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, TypeAlias, cast

from ..json_types import JsonValue


def freeze_json(value: object) -> JsonValue:
    """Return an immutable representation of JSON-compatible ``value``.

    Raises
    ------
    TypeError
        If ``value`` contains a non-JSON type or a non-finite number.
    """
    return _freeze_json(value, set())


def _freeze_json(value: object, active: set[int]) -> JsonValue:
    """Freeze one JSON value while rejecting recursive container graphs."""
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            raise TypeError("cyclic containers are not JSON values")
        active.add(identity)
        frozen: dict[str, JsonValue] = {}
        try:
            for key, item in value.items():
                if type(key) is not str:
                    raise TypeError("JSON object keys must be strings")
                frozen[key] = _freeze_json(item, active)
            return MappingProxyType(frozen)
        finally:
            active.remove(identity)
    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in active:
            raise TypeError("cyclic containers are not JSON values")
        active.add(identity)
        try:
            return tuple(_freeze_json(item, active) for item in value)
        finally:
            active.remove(identity)
    if value is None or type(value) in {bool, int, str}:
        return cast(bool | int | str | None, value)
    if type(value) is float and math.isfinite(value):
        return value
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def json_values_equal(left: object, right: object) -> bool:
    """Compare JSON values structurally with JSON numeric semantics."""
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return left.keys() == right.keys() and all(
            json_values_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            json_values_equal(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        if isinstance(left, float) and not math.isfinite(left):
            return False
        if isinstance(right, float) and not math.isfinite(right):
            return False
        return left == right
    if type(left) is not type(right):
        return False
    return left == right


class DeclarationKind(StrEnum):
    """Kinds admitted by declaration schema version 1."""

    RULE_SET = "rule-set"
    RULE = "rule"
    PROCEDURE = "procedure"
    RESOLUTION_POLICY = "resolution-policy"
    COMPOSITION_MANIFEST = "composition-manifest"
    EVALUATOR = "evaluator"
    OPERATION = "operation"
    DECISION = "decision"


class DeclarationStatus(StrEnum):
    """Lifecycle states admitted by declaration schema version 1."""

    PROPOSED = "proposed"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


EXACT_CONTRACT_KINDS = frozenset({DeclarationKind.EVALUATOR, DeclarationKind.OPERATION})


class RuleAxis(StrEnum):
    """Primary functions admitted for rules."""

    REASONING_TARGET = "reasoning-target"
    OUTPUT_STRUCTURE = "output-structure"
    SURFACE_STYLE = "surface-style"


class CompositionMechanism(StrEnum):
    """Artifact mechanisms admitted by composition manifests."""

    CUMULATIVE = "cumulative"
    SEPARATE_DIRECTORY = "separate-directory"
    SINGLE_SLOT = "single-slot"


class CumulativeMarkdownProfile(StrEnum):
    """Consumer profiles for cumulative Markdown projections."""

    AUDITABLE = "auditable"
    AGENT_INSTRUCTIONS = "agent-instructions"


@dataclass(frozen=True)
class VersionedReference:
    """An opaque identifier paired with its positive contract version."""

    id: str
    version: int


@dataclass(frozen=True)
class Relation:
    """One typed relation to another declaration."""

    type: str
    target: str


@dataclass(frozen=True)
class Action:
    """The operation prescribed or permitted by one norm."""

    verb: str
    object: str
    timing: str | None


@dataclass(frozen=True)
class Norm:
    """One modal constraint carrying its fully inherited applicability."""

    id: str
    modality: str
    subject: str
    action: Action
    applicability: Mapping[str, JsonValue]
    guidance: str | None
    rationale: str | None
    decision_criterion: str | None


@dataclass(frozen=True)
class Criterion:
    """One evaluator-backed success criterion."""

    id: str
    norms: tuple[str, ...]
    evaluator: VersionedReference
    statement: str


@dataclass(frozen=True)
class ExceptionClause:
    """A conditional waiver or substitution of local rule norms."""

    id: str
    when: Mapping[str, JsonValue]
    disposition: str
    affects: tuple[str, ...]
    substitutes: tuple[str, ...]


@dataclass(frozen=True)
class Predicate:
    """A typed, side-effect-free procedure predicate."""

    id: str
    predicate_class: str
    expression: Mapping[str, JsonValue]
    evaluator: VersionedReference | None
    observes: tuple[str, ...]


@dataclass(frozen=True)
class ParameterBinding:
    """Bind one operation input to a declared procedure parameter."""

    parameter: str


@dataclass(frozen=True)
class LiteralBinding:
    """Bind one operation input to an immutable JSON literal."""

    value: JsonValue


Binding: TypeAlias = ParameterBinding | LiteralBinding


@dataclass(frozen=True)
class Declaration:
    """Fields shared by every schema-validated declaration."""

    schema_version: int
    id: str
    kind: DeclarationKind
    owner: str
    status: DeclarationStatus
    source_revision: str
    applicability: Mapping[str, JsonValue]
    relations: tuple[Relation, ...]
    title: str | None
    rationale: str | None
    document: Mapping[str, JsonValue]


@dataclass(frozen=True)
class RuleDeclaration(Declaration):
    """A rule with one axis, modal norms, and evaluator-backed criteria."""

    axis: RuleAxis
    failure_mode: str
    required_visibility: str | None
    decided_by: tuple[str, ...]
    norms: tuple[Norm, ...]
    criteria: tuple[Criterion, ...]
    exceptions: tuple[ExceptionClause, ...]


@dataclass(frozen=True)
class RuleSetDeclaration(Declaration):
    """A coherent group of addressable rules."""

    purpose: str
    rules: tuple[RuleDeclaration, ...]


@dataclass(frozen=True)
class ProcedureNode:
    """One registered operation and its total outcome transitions."""

    id: str
    operation: VersionedReference
    bindings: Mapping[str, Binding]
    on_success: str
    on_failure: Mapping[str, str]


@dataclass(frozen=True)
class ProcedureDeclaration(Declaration):
    """A finite externally observable action graph."""

    purpose: str
    parameters: Mapping[str, JsonValue]
    preconditions: tuple[Predicate, ...]
    actions: tuple[ProcedureNode, ...]
    entry: str
    invariants: tuple[Predicate, ...]
    effects: tuple[str, ...]
    postconditions: tuple[Predicate, ...]
    failures: tuple[str, ...]


@dataclass(frozen=True)
class ResolutionStrategy:
    """The explicit action taken for one matched conflict."""

    kind: str
    retain: str | None
    replace: str | None
    replacement: str | None
    result: str | None


@dataclass(frozen=True)
class ResolutionPolicyDeclaration(Declaration):
    """A deterministic policy for one declared conflict."""

    conflicts: tuple[str, str]
    when: Mapping[str, JsonValue]
    order: int
    strategy: ResolutionStrategy


@dataclass(frozen=True)
class ManifestSection:
    """One ordered manifest section and its declaration selection."""

    id: str
    declarations: tuple[str, ...]


@dataclass(frozen=True)
class CompositionManifestDeclaration(Declaration):
    """The ordered declaration selection for one native-scope artifact."""

    mechanism: CompositionMechanism
    scope: str
    target: str
    invocation: tuple[str, ...]
    sections: tuple[ManifestSection, ...]
    policies: tuple[str, ...]


@dataclass(frozen=True)
class EvaluatorDeclaration(Declaration):
    """A versioned contract for evaluator-backed obligation evidence."""

    version: int
    evaluator_kind: str
    coverage: str
    adjudication: str
    timing: str
    residual_question: str | None
    input_revisions: tuple[str, ...]
    evidence_schema: Mapping[str, JsonValue]
    failure_behavior: str
    known_failure_fixtures: tuple[str, ...]


@dataclass(frozen=True)
class SupportResourceReference:
    """Place one acquired resource inside an operation's Skill artifact."""

    resource: str
    destination: str


@dataclass(frozen=True)
class OperationDeclaration(Declaration):
    """A versioned operation contract referenced by procedures."""

    version: int
    inputs: Mapping[str, JsonValue]
    outputs: Mapping[str, JsonValue]
    preconditions: tuple[Predicate, ...]
    method: str | None
    support_resources: tuple[SupportResourceReference, ...]
    effects: tuple[str, ...]
    failure_outcomes: tuple[str, ...]
    recovery: str


@dataclass(frozen=True)
class DecisionDriver:
    """One criterion used to compare every option of a decision."""

    id: str
    statement: str


@dataclass(frozen=True)
class DecisionAssessment:
    """One option-specific judgment against a declared decision driver."""

    driver: str
    judgment: str


@dataclass(frozen=True)
class DecisionOption:
    """One explicitly considered option of a governance decision."""

    id: str
    description: str
    assessments: tuple[DecisionAssessment, ...]


@dataclass(frozen=True)
class DecisionDeclaration(Declaration):
    """A governance decision with an explicit selected outcome."""

    context: str
    drivers: tuple[DecisionDriver, ...]
    options: tuple[DecisionOption, ...]
    outcome: str
    consequences: str


AnyDeclaration: TypeAlias = (
    RuleSetDeclaration
    | RuleDeclaration
    | ProcedureDeclaration
    | ResolutionPolicyDeclaration
    | CompositionManifestDeclaration
    | EvaluatorDeclaration
    | OperationDeclaration
    | DecisionDeclaration
)
