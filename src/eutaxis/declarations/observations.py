"""Observe evaluator-less procedure preconditions at one coherent boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import NoReturn, Protocol, SupportsIndex, cast

from ._runner_support import exception_detail, validate_synchronous_runner
from .applicability import (
    ApplicabilityTrace,
    AtomicApplicabilityTrace,
    BooleanApplicabilityTrace,
    TruthValue,
    _evaluate_validated_applicability_with_trace,
)
from .attention import (
    CompletionRequirement,
    ProcedureObligationSnapshot,
    ProcedurePredicateKey,
)
from .enforcement import PredicatePhase
from .exceptions import (
    FacetContextError,
    ObservationProviderRegistryError,
    ProcedureObservationError,
)
from .facets import FacetRegistry
from .models import JsonValue, freeze_json, json_values_equal
from .procedure_runs import ProcedureRunPlan, _is_issued_procedure_run_plan
from .registry import DeclarationRegistry
from .source import format_document_path

_REGISTRY_ISSUER = object()
_EVIDENCE_ISSUER = object()


@dataclass(frozen=True, init=False)
class ObservationRequest:
    """Expose the minimum immutable input for one coherent boundary snapshot."""

    procedure: str
    phase: PredicatePhase
    occurrence: int
    facets: tuple[str, ...]
    parameters: Mapping[str, JsonValue]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("ObservationRequest instances must be issued by observation")


class ObservationProvider(Protocol):
    """A reviewed synchronous provider of one requested facet snapshot."""

    def __call__(self, request: ObservationRequest, /) -> Mapping[str, object]:
        """Return the present values for the requested boundary facets."""


@dataclass(frozen=True, init=False, eq=False)
class ObservationProviderRegistry:
    """Process-local authority for one coherent batch observation provider."""

    declarations: DeclarationRegistry
    facets: FacetRegistry
    provider: ObservationProvider
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "ObservationProviderRegistry instances must be issued by its builder"
        )

    def __copy__(self) -> NoReturn:
        raise TypeError("ObservationProviderRegistry instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("ObservationProviderRegistry instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("ObservationProviderRegistry instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("ObservationProviderRegistry instances cannot be serialized")


@dataclass(frozen=True)
class ProcedurePredicateObservation:
    """Retain one canonical requirement and its evaluator-owned predicate trace."""

    requirement: CompletionRequirement
    trace: ApplicabilityTrace
    truth: TruthValue


@dataclass(frozen=True, init=False, eq=False)
class ProcedurePreconditionObservation:
    """Process-local evidence from one coherent procedure-precondition snapshot."""

    run: ProcedureRunPlan
    registry: ObservationProviderRegistry
    phase: PredicatePhase
    occurrence: int
    requirements: tuple[CompletionRequirement, ...]
    observations: tuple[ProcedurePredicateObservation, ...]
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError(
            "ProcedurePreconditionObservation instances must be issued by observation"
        )

    def __copy__(self) -> NoReturn:
        raise TypeError("ProcedurePreconditionObservation instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("ProcedurePreconditionObservation instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError(
            "ProcedurePreconditionObservation instances cannot be serialized"
        )

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError(
            "ProcedurePreconditionObservation instances cannot be serialized"
        )


def build_observation_provider_registry(
    declarations: DeclarationRegistry,
    facets: FacetRegistry,
    provider: ObservationProvider,
) -> ObservationProviderRegistry:
    """Bind one reviewed batch provider to exact declaration and facet registries."""
    if declarations.facet_registry is not facets:
        raise ObservationProviderRegistryError(
            "$.facets", "facet registry differs from the declaration registry"
        )
    validate_synchronous_runner(
        provider,
        lambda message: ObservationProviderRegistryError("$.provider", message),
    )
    registry = object.__new__(ObservationProviderRegistry)
    object.__setattr__(registry, "declarations", declarations)
    object.__setattr__(registry, "facets", facets)
    object.__setattr__(registry, "provider", provider)
    object.__setattr__(registry, "_issuer", _REGISTRY_ISSUER)
    return registry


def _is_builder_issued_observation_registry(registry: object) -> bool:
    """Return whether ``registry`` carries this process's builder authority."""
    return (
        type(registry) is ObservationProviderRegistry
        and getattr(registry, "_issuer", None) is _REGISTRY_ISSUER
    )


def _is_issued_procedure_precondition_observation(evidence: object) -> bool:
    """Return whether ``evidence`` retains every issued correlation invariant."""
    if (
        type(evidence) is not ProcedurePreconditionObservation
        or getattr(evidence, "_issuer", None) is not _EVIDENCE_ISSUER
    ):
        return False
    try:
        run = evidence.run
        registry = evidence.registry
        requirements = evidence.requirements
        observations = evidence.observations
        if not _is_issued_procedure_run_plan(run):
            return False
        if not _is_builder_issued_observation_registry(registry):
            return False
        declarations = run.attention.resolution.registry
        if registry.declarations is not declarations:
            return False
        if registry.facets is not declarations.facet_registry:
            return False
        if evidence.phase is not PredicatePhase.PRECONDITION:
            return False
        if type(evidence.occurrence) is not int or evidence.occurrence != 0:
            return False
        if type(requirements) is not tuple or type(observations) is not tuple:
            return False
        canonical = _procedure_precondition_requirements(run)
        if len(requirements) != len(canonical):
            return False
        if any(
            actual is not expected for actual, expected in zip(requirements, canonical)
        ):
            return False
        if len(observations) != len(requirements):
            return False
        for requirement, observation in zip(requirements, observations):
            if type(observation) is not ProcedurePredicateObservation:
                return False
            if observation.requirement is not requirement:
                return False
            if observation.truth is not observation.trace.result:
                return False
        context = _validated_trace_context(observations, registry.facets)
        for requirement, observation in zip(requirements, observations):
            if not _trace_matches_requirement(observation.trace, requirement, context):
                return False
    except Exception:
        return False
    return True


def _validated_trace_context(
    observations: tuple[ProcedurePredicateObservation, ...],
    facets: FacetRegistry,
) -> Mapping[str, JsonValue]:
    """Reconstruct and validate one context shared by every retained trace."""
    observed: dict[str, tuple[bool, JsonValue]] = {}

    def collect(node: object) -> None:
        if type(node) is AtomicApplicabilityTrace:
            atomic = cast(AtomicApplicabilityTrace, node)
            if (
                type(atomic.facet) is not str
                or type(atomic.observed_present) is not bool
            ):
                raise ValueError("invalid atomic trace")
            current = (atomic.observed_present, atomic.observed)
            if atomic.facet in observed:
                previous = observed[atomic.facet]
                if previous[0] is not current[0]:
                    raise ValueError("inconsistent facet presence across traces")
                if current[0] and not json_values_equal(previous[1], current[1]):
                    raise ValueError("inconsistent facet value across traces")
            else:
                observed[atomic.facet] = current
            return
        if type(node) is BooleanApplicabilityTrace:
            boolean = cast(BooleanApplicabilityTrace, node)
            if type(boolean.children) is not tuple:
                raise ValueError("invalid Boolean trace")
            for child in boolean.children:
                collect(child)
            return
        raise ValueError("invalid applicability trace")

    for observation in observations:
        collect(observation.trace)
    context = {facet: value for facet, (present, value) in observed.items() if present}
    return facets.validate_context(context)


def _trace_matches_requirement(
    trace: object,
    requirement: CompletionRequirement,
    context: Mapping[str, JsonValue],
) -> bool:
    """Check one trace against its exact predicate under the shared context."""
    obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
    expected = _evaluate_validated_applicability_with_trace(
        obligation.predicate.expression, context
    )
    return trace == expected


def observe_procedure_preconditions(
    run: ProcedureRunPlan,
    registry: ObservationProviderRegistry,
) -> ProcedurePreconditionObservation:
    """Observe evaluator-less procedure preconditions once before procedure entry."""
    if not _is_issued_procedure_run_plan(run):
        _fail(("run",), "procedure run plan was not issued by preflight")
    if not _is_builder_issued_observation_registry(registry):
        _fail(("registry",), "observation registry was not issued by its builder")
    declarations = run.attention.resolution.registry
    if registry.declarations is not declarations:
        _fail(
            ("registry",),
            "observation registry belongs to another declaration registry",
        )
    if registry.facets is not declarations.facet_registry:
        _fail(("registry", "facets"), "observation facet registry identity differs")

    requirements = _procedure_precondition_requirements(run)
    if not requirements:
        return _issue_observation(run, registry, requirements, ())

    requested = _requested_facets(requirements)
    request = _issue_request(run, requested)
    try:
        returned = registry.provider(request)
    except Exception as exc:
        _fail(
            ("provider",),
            f"provider raised {exception_detail(exc)}",
            cause=exc,
        )
    context = _snapshot_observation(returned, requested, registry.facets)
    observations = tuple(
        _evaluate_requirement(requirement, context) for requirement in requirements
    )
    return _issue_observation(run, registry, requirements, observations)


def _procedure_precondition_requirements(
    run: ProcedureRunPlan,
) -> tuple[CompletionRequirement, ...]:
    """Select canonical evaluator-less procedure preconditions from ``run``."""
    return tuple(
        requirement
        for requirement in run.procedure_precondition_requirements
        if requirement.evaluator is None
    )


def _requested_facets(
    requirements: tuple[CompletionRequirement, ...],
) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()
    for requirement in requirements:
        obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
        for facet in _expression_facets(obligation.predicate.expression):
            if facet not in seen:
                seen.add(facet)
                ordered.append(facet)
    return tuple(ordered)


def _expression_facets(expression: Mapping[str, JsonValue]) -> tuple[str, ...]:
    for operator in ("all", "any"):
        if operator in expression:
            return tuple(
                facet
                for child in cast(tuple[JsonValue, ...], expression[operator])
                for facet in _expression_facets(cast(Mapping[str, JsonValue], child))
            )
    if "not" in expression:
        return _expression_facets(cast(Mapping[str, JsonValue], expression["not"]))
    return (cast(str, expression["facet"]),)


def _issue_request(
    run: ProcedureRunPlan, facets: tuple[str, ...]
) -> ObservationRequest:
    request = object.__new__(ObservationRequest)
    object.__setattr__(request, "procedure", run.procedure.id)
    object.__setattr__(request, "phase", PredicatePhase.PRECONDITION)
    object.__setattr__(request, "occurrence", 0)
    object.__setattr__(request, "facets", facets)
    object.__setattr__(request, "parameters", run.parameters)
    return request


def _snapshot_observation(
    returned: object,
    requested: tuple[str, ...],
    facets: FacetRegistry,
) -> Mapping[str, JsonValue]:
    if not isinstance(returned, Mapping):
        _fail(("provider", "result"), "provider result must be a mapping")
    try:
        pairs = tuple(returned.items())
    except Exception as exc:
        _fail(
            ("provider", "result"),
            f"provider result could not be read: {exception_detail(exc)}",
            cause=exc,
        )
    requested_set = set(requested)
    snapshot: dict[str, object] = {}
    for index, pair in enumerate(pairs):
        try:
            key, value = pair
        except Exception as exc:
            _fail(
                ("provider", "result", index),
                f"provider item is not a key-value pair: {exception_detail(exc)}",
                cause=exc,
            )
        if type(key) is not str:
            _fail(("provider", "result", index, "key"), "facet key must be text")
        if key in snapshot:
            _fail(("provider", "result", index, "key"), "facet key is duplicated")
        if key not in requested_set:
            _fail(("provider", "result", index, "key"), "facet was not requested")
        try:
            snapshot[key] = freeze_json(value)
        except Exception as exc:
            _fail(
                ("provider", "result", key),
                f"facet value is not finite JSON: {exception_detail(exc)}",
                cause=exc,
            )
    try:
        return facets.validate_context(snapshot)
    except FacetContextError as exc:
        _fail(("provider", "result"), str(exc), cause=exc)


def _evaluate_requirement(
    requirement: CompletionRequirement,
    context: Mapping[str, JsonValue],
) -> ProcedurePredicateObservation:
    obligation = cast(ProcedureObligationSnapshot, requirement.obligation)
    trace = _evaluate_validated_applicability_with_trace(
        obligation.predicate.expression, context
    )
    return ProcedurePredicateObservation(requirement, trace, trace.result)


def _issue_observation(
    run: ProcedureRunPlan,
    registry: ObservationProviderRegistry,
    requirements: tuple[CompletionRequirement, ...],
    observations: tuple[ProcedurePredicateObservation, ...],
) -> ProcedurePreconditionObservation:
    evidence = object.__new__(ProcedurePreconditionObservation)
    object.__setattr__(evidence, "run", run)
    object.__setattr__(evidence, "registry", registry)
    object.__setattr__(evidence, "phase", PredicatePhase.PRECONDITION)
    object.__setattr__(evidence, "occurrence", 0)
    object.__setattr__(evidence, "requirements", requirements)
    object.__setattr__(evidence, "observations", observations)
    object.__setattr__(evidence, "_issuer", _EVIDENCE_ISSUER)
    return evidence


def _fail(
    parts: tuple[str | int, ...], message: str, *, cause: Exception | None = None
) -> NoReturn:
    error = ProcedureObservationError(format_document_path(parts), message)
    if cause is not None:
        raise error from cause
    raise error
