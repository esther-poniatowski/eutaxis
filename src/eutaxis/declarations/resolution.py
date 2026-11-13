"""Resolve one manifest into a certified, context-specific compilation unit."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Mapping, NoReturn, SupportsIndex, cast

from ._authority import IdentityAuthorityStore, identity_value_state
from .applicability import (
    ApplicabilityTrace,
    TruthValue,
    _evaluate_validated_applicability_with_trace,
    conjoin_applicability,
)
from .composite_facets import (
    CompositeFacetRegistry,
    _is_issued_composite_facet_registry,
)
from .models import (
    CompositionManifestDeclaration,
    DeclarationStatus,
    ExceptionClause,
    JsonValue,
    ProcedureDeclaration,
    ResolutionPolicyDeclaration,
    RuleDeclaration,
    RuleSetDeclaration,
)
from .registry import ConflictPair, DeclarationRegistry, RegisteredDeclaration
from .source import DocumentPath, nearest_location

_RESOLUTION_RESULT_ISSUER = object()
_RESOLUTION_AUTHORITIES: IdentityAuthorityStore[ResolutionResult] = (
    IdentityAuthorityStore()
)


@dataclass(frozen=True)
class ManifestAnchor:
    """One authored manifest position used as a stable resolver anchor."""

    section: str
    rank: int


@dataclass(frozen=True)
class ResolvedComponent:
    """One effective record with its resolver-assigned manifest anchor."""

    section: str
    declaration: str
    rank: int


@dataclass(frozen=True)
class ResolvedDependency:
    """One prerequisite edge retained after semantic resolution."""

    prerequisite: str
    dependant: str


@dataclass(frozen=True)
class ResolvedRuleProjection:
    """The effective local norms and criteria of one resolved rule."""

    declaration: str
    norms: tuple[str, ...]
    criteria: tuple[str, ...]


@dataclass(frozen=True)
class ResolutionSource:
    """An exact source position that owns one resolver decision."""

    path: Path
    document_path: DocumentPath
    line: int
    column: int


class ResolutionEventKind(StrEnum):
    """The closed semantic-event vocabulary of version 1 resolution."""

    MANIFEST_EVALUATED = "manifest-evaluated"
    MANIFEST_SELECTED = "manifest-selected"
    RULE_SET_MEMBER_EXPANDED = "rule-set-member-expanded"
    RULE_SET_MEMBER_INACTIVE = "rule-set-member-inactive"
    DEPENDENCY_DISCOVERED = "dependency-discovered"
    POLICY_RESULT_DISCOVERED = "policy-result-discovered"
    DECLARATION_EVALUATED = "declaration-evaluated"
    CONFLICT_DETECTED = "conflict-detected"
    POLICY_EVALUATED = "policy-evaluated"
    CONFLICT_RESOLVED = "conflict-resolved"
    DECLARATION_EXCLUDED = "declaration-excluded"
    ALIAS_CREATED = "alias-created"
    DECLARATION_EFFECTIVE = "declaration-effective"
    NORM_EVALUATED = "norm-evaluated"
    EXCEPTION_EVALUATED = "exception-evaluated"
    NORM_REMOVED = "norm-removed"
    NORM_SUBSTITUTED = "norm-substituted"
    NORM_EFFECTIVE = "norm-effective"
    CRITERION_EFFECTIVE = "criterion-effective"
    CRITERION_INACTIVE = "criterion-inactive"
    UNIT_ISSUED = "unit-issued"


class ResolutionErrorCode(StrEnum):
    """The closed failure vocabulary of version 1 resolution."""

    UNKNOWN_MANIFEST = "unknown-manifest"
    MANIFEST_WRONG_KIND = "manifest-wrong-kind"
    MANIFEST_INACTIVE = "manifest-inactive"
    MANIFEST_INAPPLICABLE = "manifest-inapplicable"
    MANIFEST_APPLICABILITY_INDETERMINATE = "manifest-applicability-indeterminate"
    DEPENDENCY_INAPPLICABLE = "dependency-inapplicable"
    DEPENDENCY_APPLICABILITY_INDETERMINATE = "dependency-applicability-indeterminate"
    DEPENDENCY_UNSATISFIED = "dependency-unsatisfied"
    UNRESOLVED_CONFLICT = "unresolved-conflict"
    CONFLICT_POLICY_INDETERMINATE = "conflict-policy-indeterminate"
    AMBIGUOUS_POLICY_ALIAS = "ambiguous-policy-alias"
    POLICY_SUBSTITUTE_INAPPLICABLE = "policy-substitute-inapplicable"
    POLICY_SUBSTITUTE_INDETERMINATE = "policy-substitute-indeterminate"
    POLICY_COMBINE_RESULT_INAPPLICABLE = "policy-combine-result-inapplicable"
    POLICY_COMBINE_RESULT_INDETERMINATE = "policy-combine-result-indeterminate"
    POLICY_RESULT_EXCLUDED = "policy-result-excluded"
    EXCEPTION_SUBSTITUTE_INAPPLICABLE = "exception-substitute-inapplicable"
    EXCEPTION_SUBSTITUTE_INDETERMINATE = "exception-substitute-indeterminate"
    PARTIAL_CRITERION_APPLICABILITY = "partial-criterion-applicability"


@dataclass(frozen=True, init=False)
class ResolutionEvent:
    """One resolver-issued semantic decision with exact provenance."""

    ordinal: int
    kind: ResolutionEventKind
    declaration: str
    source: ResolutionSource
    causes: tuple[int, ...]
    anchor: ManifestAnchor | None
    relation: str | None
    dependant: str | None
    policy: str | None
    exception: str | None
    norm: str | None
    criterion: str | None
    conflict: ConflictPair | None
    replacement: str | None
    truth: TruthValue | None
    applicability: ApplicabilityTrace | None

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Reject construction outside semantic resolution."""
        raise TypeError("ResolutionEvent instances must be issued by resolution")


@dataclass(frozen=True, init=False)
class ResolutionTrace:
    """One resolver-issued deterministic event sequence."""

    manifest: str
    facet_registry: str
    facet_content_revision: str
    events: tuple[ResolutionEvent, ...]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Reject construction outside semantic resolution."""
        raise TypeError("ResolutionTrace instances must be issued by resolution")


@dataclass(frozen=True, init=False)
class ResolvedCompilationUnit:
    """Certified resolver output consumed by deterministic composition."""

    manifest: str
    components: tuple[ResolvedComponent, ...]
    dependencies: tuple[ResolvedDependency, ...]
    rule_projections: tuple[ResolvedRuleProjection, ...]

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Reject construction outside semantic resolution."""
        raise TypeError(
            "ResolvedCompilationUnit instances must be issued by semantic resolution"
        )


@dataclass(frozen=True, init=False)
class ResolutionResult:
    """One correlated successful compilation unit and explanation trace."""

    registry: DeclarationRegistry = field(compare=False, repr=False)
    manifest_record: RegisteredDeclaration = field(compare=False, repr=False)
    context: Mapping[str, JsonValue] = field(compare=False, repr=False)
    unit: ResolvedCompilationUnit
    trace: ResolutionTrace
    _facet_registry_state: object = field(compare=False, repr=False)
    _token: object = field(compare=False, repr=False)
    _state: tuple[object, ...] = field(compare=False, repr=False)
    _issuer: object = field(compare=False, repr=False)

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Reject construction outside semantic resolution."""
        raise TypeError("ResolutionResult instances must be issued by resolution")

    def __copy__(self) -> NoReturn:
        """Reject reconstruction by shallow copying."""
        raise TypeError("ResolutionResult instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        """Reject reconstruction by deep copying."""
        raise TypeError("ResolutionResult instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        """Reject serialization and reconstruction."""
        raise TypeError("ResolutionResult instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        """Reject protocol-specific serialization and reconstruction."""
        raise TypeError("ResolutionResult instances cannot be serialized")


def _is_issued_resolution_result(result: object) -> bool:
    """Return whether ``result`` retains its complete resolver authority."""
    if (
        type(result) is not ResolutionResult
        or getattr(result, "_issuer", None) is not _RESOLUTION_RESULT_ISSUER
        or type(getattr(result, "_state", None)) is not tuple
    ):
        return False
    try:
        issued = _RESOLUTION_AUTHORITIES.lookup(result)
        return (
            issued is not None
            and result._token is issued[0]
            and result._state == issued[1]
            and result._state == _capture_resolution_authority_state(result)
            and _facet_registry_state_matches(
                result.registry, result._facet_registry_state
            )
        )
    except Exception:
        return False


def _capture_resolution_authority_state(
    result: ResolutionResult,
) -> tuple[object, ...]:
    """Capture the complete resolved unit and trace without retaining the result."""
    registry = result.registry
    unit = result.unit
    manifest_record = result.manifest_record
    if registry.records[unit.manifest] is not manifest_record:
        raise ValueError("resolved manifest record changed")
    manifest = manifest_record.declaration
    if any(
        type(value) is not str for value in (unit.manifest, manifest.id, manifest.owner)
    ):
        raise ValueError("resolved manifest identity is not exact text")
    components: list[object] = []
    for component in unit.components:
        record = registry.records[component.declaration]
        declaration = record.declaration
        components.append(
            (
                id(component),
                component.section,
                component.declaration,
                component.rank,
                id(record),
                id(declaration),
                getattr(declaration, "version", None),
                declaration.kind.value,
            )
        )
    trace = result.trace
    return (
        id(registry),
        id(registry.records),
        _resolution_facet_authority_state(registry),
        id(unit),
        identity_value_state(unit.manifest),
        id(manifest_record),
        id(manifest),
        identity_value_state(manifest.id),
        identity_value_state(manifest.owner),
        manifest.kind.value,
        id(result.context),
        identity_value_state(result.context),
        id(unit.components),
        tuple(components),
        id(unit.dependencies),
        tuple(identity_value_state(item) for item in unit.dependencies),
        id(unit.rule_projections),
        tuple(identity_value_state(item) for item in unit.rule_projections),
        id(trace),
        trace.manifest,
        trace.facet_registry,
        trace.facet_content_revision,
        id(trace.events),
        tuple(identity_value_state(event) for event in trace.events),
        id(result._issuer),
    )


def _resolution_facet_authority_state(
    registry: DeclarationRegistry,
) -> tuple[object, ...]:
    """Capture facet carriers and values without reading external resources."""
    facets = registry.facet_registry
    if not _is_issued_composite_facet_registry(facets):
        raise ValueError("resolution facet registry is not issued")
    return (identity_value_state(facets),)


def _capture_facet_registry_state(registry: DeclarationRegistry) -> tuple[object, ...]:
    facets = registry.facet_registry
    if not _is_issued_composite_facet_registry(facets):
        raise ValueError("resolution facet registry is not issued")
    return (facets, identity_value_state(facets))


def _facet_registry_state_matches(
    registry: DeclarationRegistry, expected: object
) -> bool:
    if type(expected) is not tuple or len(expected) != 2:
        return False
    try:
        current = _capture_facet_registry_state(registry)
    except Exception:
        return False
    return current[0] is expected[0] and current[1] == expected[1]


class ResolutionError(Exception):
    """Report one closed semantic-resolution failure."""

    def __init__(
        self,
        code: ResolutionErrorCode,
        detail: str,
        *,
        source: ResolutionSource | None = None,
        trace: ResolutionTrace | None = None,
        truth: TruthValue | None = None,
        applicability: ApplicabilityTrace | None = None,
    ) -> None:
        if (truth is None) is not (applicability is None):
            raise TypeError("truth and applicability must occur together")
        predicate_failure = code.value.endswith(("inapplicable", "indeterminate"))
        if predicate_failure != (truth is not None):
            raise TypeError(
                "predicate-dependent resolution errors require truth and applicability"
            )
        super().__init__(f"Resolution failed [{code.value}]: {detail}")
        self.code = code
        self.detail = detail
        self.source = source
        self.trace = trace
        self.truth = truth
        self.applicability = applicability


@dataclass(frozen=True)
class _Dependency:
    """One discovered dependency with its authored relation provenance."""

    prerequisite: str
    dependant: str
    relation: str
    record: RegisteredDeclaration
    path: DocumentPath


@dataclass(frozen=True)
class _ConflictProposal:
    """One winning policy and its state changes within a round snapshot."""

    pair: ConflictPair
    policy_record: RegisteredDeclaration
    policy_event: int
    exclusions: tuple[str, ...]
    aliases: tuple[tuple[str, str], ...]
    result: str | None
    result_path: DocumentPath | None
    result_anchor: ManifestAnchor | None


_EVENT_FIELDS: Mapping[ResolutionEventKind, frozenset[str]] = {
    ResolutionEventKind.MANIFEST_EVALUATED: frozenset({"truth", "applicability"}),
    ResolutionEventKind.MANIFEST_SELECTED: frozenset({"anchor"}),
    ResolutionEventKind.RULE_SET_MEMBER_EXPANDED: frozenset({"anchor"}),
    ResolutionEventKind.RULE_SET_MEMBER_INACTIVE: frozenset({"anchor"}),
    ResolutionEventKind.DEPENDENCY_DISCOVERED: frozenset(
        {"anchor", "relation", "dependant"}
    ),
    ResolutionEventKind.POLICY_RESULT_DISCOVERED: frozenset(
        {"anchor", "policy", "conflict"}
    ),
    ResolutionEventKind.DECLARATION_EVALUATED: frozenset(
        {"anchor", "truth", "applicability"}
    ),
    ResolutionEventKind.CONFLICT_DETECTED: frozenset({"conflict"}),
    ResolutionEventKind.POLICY_EVALUATED: frozenset(
        {"conflict", "truth", "applicability"}
    ),
    ResolutionEventKind.CONFLICT_RESOLVED: frozenset({"policy", "conflict"}),
    ResolutionEventKind.DECLARATION_EXCLUDED: frozenset({"policy", "conflict"}),
    ResolutionEventKind.ALIAS_CREATED: frozenset({"policy", "conflict", "replacement"}),
    ResolutionEventKind.DECLARATION_EFFECTIVE: frozenset({"anchor"}),
    ResolutionEventKind.NORM_EVALUATED: frozenset({"norm", "truth", "applicability"}),
    ResolutionEventKind.EXCEPTION_EVALUATED: frozenset(
        {"exception", "truth", "applicability"}
    ),
    ResolutionEventKind.NORM_REMOVED: frozenset({"norm", "exception"}),
    ResolutionEventKind.NORM_SUBSTITUTED: frozenset({"norm", "exception"}),
    ResolutionEventKind.NORM_EFFECTIVE: frozenset({"norm"}),
    ResolutionEventKind.CRITERION_EFFECTIVE: frozenset({"criterion"}),
    ResolutionEventKind.CRITERION_INACTIVE: frozenset({"criterion"}),
    ResolutionEventKind.UNIT_ISSUED: frozenset(),
}
_OPTIONAL_EVENT_FIELDS = frozenset(
    {
        "anchor",
        "relation",
        "dependant",
        "policy",
        "exception",
        "norm",
        "criterion",
        "conflict",
        "replacement",
        "truth",
        "applicability",
    }
)


def resolve_compilation_unit(
    registry: DeclarationRegistry,
    manifest_id: str,
    context: Mapping[str, object],
) -> ResolutionResult:
    """Resolve one composition manifest under its registry-bound context."""
    if type(
        registry.facet_registry
    ) is not CompositeFacetRegistry or not _is_issued_composite_facet_registry(
        registry.facet_registry
    ):
        raise TypeError("semantic resolution requires an issued composite registry")
    return _Resolver(registry, manifest_id, context).resolve()


class _Resolver:
    """Mutable state machine hidden behind one immutable resolver result."""

    def __init__(
        self,
        registry: DeclarationRegistry,
        manifest_id: str,
        context: Mapping[str, object],
    ) -> None:
        self.registry = registry
        self.manifest_id = manifest_id
        self.input_context = context
        self.context: Mapping[str, JsonValue] | None = None
        self.manifest_record: RegisteredDeclaration | None = None
        self.manifest: CompositionManifestDeclaration | None = None
        self.events: list[ResolutionEvent] = []
        self.anchors: dict[str, ManifestAnchor] = {}
        self.direct_anchors: dict[str, ManifestAnchor] = {}
        self.discovery_causes: dict[str, list[int]] = {}
        self.evaluations: dict[str, ApplicabilityTrace] = {}
        self.candidate: set[str] = set()
        self.required: set[str] = set()
        self.excluded: set[str] = set()
        self.aliases: dict[str, str] = {}
        self.dependencies: list[_Dependency] = []
        self.processed_discoveries: set[tuple[str, str, str, str, int]] = set()

    def resolve(self) -> ResolutionResult:
        """Run every semantic phase and issue one correlated result."""
        self._resolve_manifest()
        assert self.manifest is not None
        assert self.manifest_record is not None
        assert self.context is not None
        self._discover_manifest_selections()
        self._resolve_fixed_point()
        effective = (self.candidate | self.required) - self.excluded
        dependencies = self._final_dependencies(effective)
        components, effective_events = self._effective_components(effective)
        projections, projection_events = self._project_rules(components)
        unit_event = self._emit(
            ResolutionEventKind.UNIT_ISSUED,
            self.manifest.id,
            self.manifest_record,
            (),
            causes=tuple(sorted((*effective_events, *projection_events))),
        )
        unit = _issue_compilation_unit(
            self.manifest.id, components, dependencies, projections
        )
        trace = self._trace()
        assert trace.events[unit_event].kind is ResolutionEventKind.UNIT_ISSUED
        return _issue_result(
            self.registry,
            self.manifest_record,
            self.context,
            unit,
            trace,
        )

    def _resolve_manifest(self) -> None:
        record = self.registry.records.get(self.manifest_id)
        if record is None:
            raise ResolutionError(
                ResolutionErrorCode.UNKNOWN_MANIFEST,
                f"unknown composition manifest {self.manifest_id!r}",
            )
        if not isinstance(record.declaration, CompositionManifestDeclaration):
            raise ResolutionError(
                ResolutionErrorCode.MANIFEST_WRONG_KIND,
                f"record {self.manifest_id!r} is not a composition manifest",
                source=self._source(record, ("kind",)),
            )
        self.manifest_record = record
        self.manifest = cast(CompositionManifestDeclaration, record.declaration)
        if self.manifest.status is not DeclarationStatus.ACTIVE:
            self._fail(
                ResolutionErrorCode.MANIFEST_INACTIVE,
                "composition manifest is not active",
                record,
                ("status",),
            )
        self.context = self.registry.facet_registry.validate_context(self.input_context)
        trace = self._evaluate_predicate(self.manifest.applicability)
        event = self._emit(
            ResolutionEventKind.MANIFEST_EVALUATED,
            self.manifest.id,
            record,
            ("applicability",),
            truth=trace.result,
            applicability=trace,
        )
        if trace.result is TruthValue.FALSE:
            self._fail(
                ResolutionErrorCode.MANIFEST_INAPPLICABLE,
                "composition manifest is not applicable",
                record,
                ("applicability",),
                truth=trace.result,
                applicability=trace,
            )
        if trace.result is TruthValue.UNKNOWN:
            self._fail(
                ResolutionErrorCode.MANIFEST_APPLICABILITY_INDETERMINATE,
                "composition manifest applicability is indeterminate",
                record,
                ("applicability",),
                truth=trace.result,
                applicability=trace,
            )
        assert event == 0

    def _discover_manifest_selections(self) -> None:
        assert self.manifest is not None
        assert self.manifest_record is not None
        rank = 0
        for section_index, section in enumerate(self.manifest.sections):
            for item_index, identifier in enumerate(section.declarations):
                anchor = ManifestAnchor(section.id, rank)
                selected = self.registry.records[identifier]
                selection_event = self._emit(
                    ResolutionEventKind.MANIFEST_SELECTED,
                    identifier,
                    self.manifest_record,
                    ("sections", section_index, "declarations", item_index),
                    causes=(0,),
                    anchor=anchor,
                )
                declaration = selected.declaration
                if isinstance(declaration, RuleSetDeclaration):
                    for member_offset, rule in enumerate(declaration.rules):
                        member_anchor = ManifestAnchor(
                            section.id,
                            rank + member_offset,
                        )
                        member = self.registry.records[rule.id]
                        if rule.status is not DeclarationStatus.ACTIVE:
                            self._emit(
                                ResolutionEventKind.RULE_SET_MEMBER_INACTIVE,
                                rule.id,
                                member,
                                ("status",),
                                causes=(selection_event,),
                                anchor=member_anchor,
                            )
                            continue
                        expanded = self._emit(
                            ResolutionEventKind.RULE_SET_MEMBER_EXPANDED,
                            rule.id,
                            member,
                            (),
                            causes=(selection_event,),
                            anchor=member_anchor,
                        )
                        self._register_discovery(rule.id, member_anchor, expanded)
                    rank += len(declaration.rules)
                else:
                    self.direct_anchors[identifier] = anchor
                    self._register_discovery(identifier, anchor, selection_event)
                    rank += 1
        for identifier in sorted(
            self.discovery_causes,
            key=lambda item: (self.anchors[item].rank, item),
        ):
            trace = self._evaluate_declaration(identifier)
            if trace.result is TruthValue.TRUE:
                self.candidate.add(identifier)

    def _resolve_fixed_point(self) -> None:
        while True:
            changed = self._expand_dependencies()
            proposals = self._select_conflict_batch()
            if proposals:
                self._validate_and_apply_batch(proposals)
                changed = True
            if not changed:
                return

    def _expand_dependencies(self) -> bool:
        changed = False
        active = (self.candidate | self.required) - self.excluded
        for dependant in sorted(
            active, key=lambda item: (self.anchors[item].rank, item)
        ):
            record = self.registry.records[dependant]
            for relation_index, relation in enumerate(record.declaration.relations):
                if relation.type not in {"requires", "refines"}:
                    continue
                anchor = self.anchors[dependant]
                key = (
                    dependant,
                    relation.type,
                    relation.target,
                    anchor.section,
                    anchor.rank,
                )
                if key in self.processed_discoveries:
                    continue
                self.processed_discoveries.add(key)
                target_record = self.registry.records[relation.target]
                event = self._emit(
                    ResolutionEventKind.DEPENDENCY_DISCOVERED,
                    relation.target,
                    record,
                    ("relations", relation_index, "target"),
                    causes=tuple(self.discovery_causes[dependant]),
                    anchor=anchor,
                    relation=relation.type,
                    dependant=dependant,
                )
                self._register_discovery(relation.target, anchor, event)
                dependency = _Dependency(
                    prerequisite=relation.target,
                    dependant=dependant,
                    relation=relation.type,
                    record=record,
                    path=("relations", relation_index, "target"),
                )
                self.dependencies.append(dependency)
                trace = self._evaluate_declaration(relation.target)
                if trace.result is TruthValue.FALSE:
                    self._fail(
                        ResolutionErrorCode.DEPENDENCY_INAPPLICABLE,
                        f"dependency {relation.target!r} is not applicable",
                        record,
                        dependency.path,
                        truth=trace.result,
                        applicability=trace,
                    )
                if trace.result is TruthValue.UNKNOWN:
                    self._fail(
                        ResolutionErrorCode.DEPENDENCY_APPLICABILITY_INDETERMINATE,
                        f"dependency {relation.target!r} is indeterminate",
                        record,
                        dependency.path,
                        truth=trace.result,
                        applicability=trace,
                    )
                if relation.target not in self.excluded:
                    before = len(self.required)
                    self.required.add(relation.target)
                    changed |= len(self.required) != before
                changed |= self._update_anchor(relation.target, anchor)
        return changed

    def _select_conflict_batch(self) -> tuple[_ConflictProposal, ...]:
        active = (self.candidate | self.required) - self.excluded
        pairs = sorted(
            pair
            for pair in self.registry.conflicts
            if pair[0] in active and pair[1] in active
        )
        proposals: list[_ConflictProposal] = []
        for pair in pairs:
            relation_record, relation_path = self._conflict_source(pair)
            detected = self._emit(
                ResolutionEventKind.CONFLICT_DETECTED,
                relation_record.declaration.id,
                relation_record,
                relation_path,
                causes=tuple(
                    sorted(
                        {
                            *self.discovery_causes[pair[0]],
                            *self.discovery_causes[pair[1]],
                        }
                    )
                ),
                conflict=pair,
            )
            policies = self._policies_for(pair)
            winner: tuple[RegisteredDeclaration, int] | None = None
            first_unknown: tuple[RegisteredDeclaration, ApplicabilityTrace] | None = (
                None
            )
            for policy_record in policies:
                policy = cast(ResolutionPolicyDeclaration, policy_record.declaration)
                predicate = conjoin_applicability(policy.applicability, policy.when)
                trace = self._evaluate_predicate(predicate)
                policy_event = self._emit(
                    ResolutionEventKind.POLICY_EVALUATED,
                    policy.id,
                    policy_record,
                    (),
                    causes=(detected,),
                    conflict=pair,
                    truth=trace.result,
                    applicability=trace,
                )
                if trace.result is TruthValue.TRUE:
                    winner = (policy_record, policy_event)
                    break
                if trace.result is TruthValue.UNKNOWN and first_unknown is None:
                    first_unknown = (policy_record, trace)
            if winner is None:
                if first_unknown is not None:
                    unknown_record, unknown_trace = first_unknown
                    self._fail(
                        ResolutionErrorCode.CONFLICT_POLICY_INDETERMINATE,
                        f"conflict {pair!r} has an indeterminate policy",
                        unknown_record,
                        (),
                        truth=unknown_trace.result,
                        applicability=unknown_trace,
                    )
                self._fail(
                    ResolutionErrorCode.UNRESOLVED_CONFLICT,
                    f"conflict {pair!r} has no matching policy",
                    relation_record,
                    relation_path,
                )
            policy_record, policy_event = winner
            policy = cast(ResolutionPolicyDeclaration, policy_record.declaration)
            if policy.strategy.kind == "error":
                self._fail(
                    ResolutionErrorCode.UNRESOLVED_CONFLICT,
                    f"policy {policy.id!r} requires an error",
                    policy_record,
                    ("strategy", "kind"),
                )
            proposals.append(self._proposal(pair, policy_record, policy_event))
        return tuple(proposals)

    def _proposal(
        self,
        pair: ConflictPair,
        record: RegisteredDeclaration,
        policy_event: int,
    ) -> _ConflictProposal:
        policy = cast(ResolutionPolicyDeclaration, record.declaration)
        strategy = policy.strategy
        if strategy.kind == "retain":
            assert strategy.retain is not None
            exclusions = tuple(item for item in pair if item != strategy.retain)
            return _ConflictProposal(
                pair,
                record,
                policy_event,
                exclusions,
                (),
                None,
                None,
                None,
            )
        if strategy.kind == "substitute":
            assert strategy.replace is not None
            assert strategy.replacement is not None
            return _ConflictProposal(
                pair,
                record,
                policy_event,
                (strategy.replace,),
                ((strategy.replace, strategy.replacement),),
                strategy.replacement,
                ("strategy", "with"),
                self.anchors[strategy.replace],
            )
        assert strategy.kind == "combine"
        assert strategy.result is not None
        anchor = min((self.anchors[item] for item in pair), key=lambda item: item.rank)
        return _ConflictProposal(
            pair,
            record,
            policy_event,
            pair,
            tuple((item, strategy.result) for item in sorted(pair)),
            strategy.result,
            ("strategy", "result"),
            anchor,
        )

    def _validate_and_apply_batch(
        self, proposals: tuple[_ConflictProposal, ...]
    ) -> None:
        batch_exclusions = {
            identifier for proposal in proposals for identifier in proposal.exclusions
        }
        batch_aliases: dict[str, str] = {}
        alias_proposals: list[tuple[_ConflictProposal, str, str]] = []
        for proposal in proposals:
            if proposal.result is not None:
                assert proposal.result_path is not None
                assert proposal.result_anchor is not None
                policy = cast(
                    ResolutionPolicyDeclaration,
                    proposal.policy_record.declaration,
                )
                discovered = self._emit(
                    ResolutionEventKind.POLICY_RESULT_DISCOVERED,
                    proposal.result,
                    proposal.policy_record,
                    proposal.result_path,
                    causes=(proposal.policy_event,),
                    anchor=proposal.result_anchor,
                    policy=policy.id,
                    conflict=proposal.pair,
                )
                self._register_discovery(
                    proposal.result, proposal.result_anchor, discovered
                )
                trace = self._evaluate_declaration(proposal.result)
                if trace.result is not TruthValue.TRUE:
                    self._fail_policy_result(proposal, trace)
                if proposal.result in self.excluded | batch_exclusions:
                    self._fail(
                        ResolutionErrorCode.POLICY_RESULT_EXCLUDED,
                        f"policy result {proposal.result!r} is excluded",
                        proposal.policy_record,
                        proposal.result_path,
                    )
            for source, target in sorted(proposal.aliases):
                prior = batch_aliases.get(source, self.aliases.get(source))
                if prior is not None and prior != target:
                    assert proposal.result_path is not None
                    self._fail(
                        ResolutionErrorCode.AMBIGUOUS_POLICY_ALIAS,
                        f"alias {source!r} maps to both {prior!r} and {target!r}",
                        proposal.policy_record,
                        proposal.result_path,
                    )
                batch_aliases[source] = target
                alias_proposals.append((proposal, source, target))
        self.excluded.update(batch_exclusions)
        self.aliases.update(batch_aliases)
        self.candidate.update(
            proposal.result for proposal in proposals if proposal.result is not None
        )
        for proposal in proposals:
            policy = cast(
                ResolutionPolicyDeclaration,
                proposal.policy_record.declaration,
            )
            resolved = self._emit(
                ResolutionEventKind.CONFLICT_RESOLVED,
                policy.id,
                proposal.policy_record,
                ("strategy", "kind"),
                causes=(proposal.policy_event,),
                policy=policy.id,
                conflict=proposal.pair,
            )
            for identifier in sorted(proposal.exclusions):
                self._emit(
                    ResolutionEventKind.DECLARATION_EXCLUDED,
                    identifier,
                    proposal.policy_record,
                    self._exclusion_path(policy),
                    causes=(resolved,),
                    policy=policy.id,
                    conflict=proposal.pair,
                )
            for _, source, target in sorted(
                (item for item in alias_proposals if item[0] == proposal),
                key=lambda item: item[1],
            ):
                self._emit(
                    ResolutionEventKind.ALIAS_CREATED,
                    source,
                    proposal.policy_record,
                    cast(DocumentPath, proposal.result_path),
                    causes=(resolved,),
                    policy=policy.id,
                    conflict=proposal.pair,
                    replacement=target,
                )

    def _final_dependencies(
        self, effective: set[str]
    ) -> tuple[ResolvedDependency, ...]:
        edges: set[tuple[str, str]] = set()
        for dependency in self.dependencies:
            if dependency.dependant not in effective:
                continue
            prerequisite = dependency.prerequisite
            if prerequisite not in effective:
                replacement = self.aliases.get(prerequisite)
                if replacement is None or replacement not in effective:
                    self._fail(
                        ResolutionErrorCode.DEPENDENCY_UNSATISFIED,
                        f"dependency {prerequisite!r} is not satisfied",
                        dependency.record,
                        dependency.path,
                    )
                prerequisite = replacement
            edges.add((prerequisite, dependency.dependant))
        return tuple(
            ResolvedDependency(prerequisite, dependant)
            for prerequisite, dependant in sorted(
                edges, key=lambda item: (item[1], item[0])
            )
        )

    def _effective_components(
        self, effective: set[str]
    ) -> tuple[tuple[ResolvedComponent, ...], tuple[int, ...]]:
        components: list[ResolvedComponent] = []
        events: list[int] = []
        for identifier in sorted(
            effective, key=lambda item: (self.anchors[item].rank, item)
        ):
            anchor = self.anchors[identifier]
            components.append(
                ResolvedComponent(anchor.section, identifier, anchor.rank)
            )
            record = self.registry.records[identifier]
            if record.declaration.status is not DeclarationStatus.ACTIVE:
                raise AssertionError("only active declarations may become effective")
            events.append(
                self._emit(
                    ResolutionEventKind.DECLARATION_EFFECTIVE,
                    identifier,
                    record,
                    (),
                    causes=tuple(self.discovery_causes[identifier]),
                    anchor=anchor,
                )
            )
        return tuple(components), tuple(events)

    def _project_rules(
        self, components: tuple[ResolvedComponent, ...]
    ) -> tuple[tuple[ResolvedRuleProjection, ...], tuple[int, ...]]:
        projections: list[ResolvedRuleProjection] = []
        final_events: list[int] = []
        for component in components:
            record = self.registry.records[component.declaration]
            if not isinstance(record.declaration, RuleDeclaration):
                continue
            rule = cast(RuleDeclaration, record.declaration)
            projection, events = self._project_rule(record, rule)
            projections.append(projection)
            final_events.extend(events)
        return tuple(projections), tuple(final_events)

    def _project_rule(
        self, record: RegisteredDeclaration, rule: RuleDeclaration
    ) -> tuple[ResolvedRuleProjection, tuple[int, ...]]:
        norm_traces: dict[str, ApplicabilityTrace] = {}
        norm_events: dict[str, int] = {}
        initial: set[str] = set()
        for index, norm in enumerate(rule.norms):
            trace = self._evaluate_predicate(norm.applicability)
            norm_traces[norm.id] = trace
            norm_events[norm.id] = self._emit(
                ResolutionEventKind.NORM_EVALUATED,
                rule.id,
                record,
                ("norms", index),
                norm=norm.id,
                truth=trace.result,
                applicability=trace,
            )
            if trace.result is TruthValue.TRUE:
                initial.add(norm.id)
        matching: list[tuple[int, ExceptionClause, int]] = []
        for index, exception in enumerate(rule.exceptions):
            trace = self._evaluate_predicate(exception.when)
            event = self._emit(
                ResolutionEventKind.EXCEPTION_EVALUATED,
                rule.id,
                record,
                ("exceptions", index, "when"),
                exception=exception.id,
                truth=trace.result,
                applicability=trace,
            )
            if trace.result is TruthValue.TRUE:
                matching.append((index, exception, event))
        removed: set[str] = set()
        substituted: set[str] = set()
        transformation_events: list[int] = []
        for exception_index, exception, exception_event in matching:
            for affects_index, identifier in enumerate(exception.affects):
                removed.add(identifier)
                if identifier in initial:
                    transformation_events.append(
                        self._emit(
                            ResolutionEventKind.NORM_REMOVED,
                            rule.id,
                            record,
                            (
                                "exceptions",
                                exception_index,
                                "affects",
                                affects_index,
                            ),
                            causes=(
                                norm_events[identifier],
                                exception_event,
                            ),
                            norm=identifier,
                            exception=exception.id,
                        )
                    )
            for substitutes_index, identifier in enumerate(exception.substitutes):
                trace = norm_traces[identifier]
                if trace.result is TruthValue.FALSE:
                    self._fail(
                        ResolutionErrorCode.EXCEPTION_SUBSTITUTE_INAPPLICABLE,
                        f"substitute norm {identifier!r} is not applicable",
                        record,
                        (
                            "exceptions",
                            exception_index,
                            "substitutes",
                            substitutes_index,
                        ),
                        truth=trace.result,
                        applicability=trace,
                    )
                if trace.result is TruthValue.UNKNOWN:
                    self._fail(
                        ResolutionErrorCode.EXCEPTION_SUBSTITUTE_INDETERMINATE,
                        f"substitute norm {identifier!r} is indeterminate",
                        record,
                        (
                            "exceptions",
                            exception_index,
                            "substitutes",
                            substitutes_index,
                        ),
                        truth=trace.result,
                        applicability=trace,
                    )
                substituted.add(identifier)
                transformation_events.append(
                    self._emit(
                        ResolutionEventKind.NORM_SUBSTITUTED,
                        rule.id,
                        record,
                        (
                            "exceptions",
                            exception_index,
                            "substitutes",
                            substitutes_index,
                        ),
                        causes=(norm_events[identifier], exception_event),
                        norm=identifier,
                        exception=exception.id,
                    )
                )
        final = (initial - removed) | substituted
        final_norm_events: dict[str, int] = {}
        for index, norm in enumerate(rule.norms):
            if norm.id not in final:
                continue
            causes = [norm_events[norm.id]]
            causes.extend(
                event
                for event in transformation_events
                if self.events[event].norm == norm.id
            )
            final_norm_events[norm.id] = self._emit(
                ResolutionEventKind.NORM_EFFECTIVE,
                rule.id,
                record,
                ("norms", index),
                causes=tuple(sorted(set(causes))),
                norm=norm.id,
            )
        effective_criteria: list[str] = []
        criterion_events: list[int] = []
        for index, criterion in enumerate(rule.criteria):
            selected = tuple(item for item in criterion.norms if item in final)
            if len(selected) == len(criterion.norms):
                effective_criteria.append(criterion.id)
                criterion_events.append(
                    self._emit(
                        ResolutionEventKind.CRITERION_EFFECTIVE,
                        rule.id,
                        record,
                        ("criteria", index),
                        causes=tuple(
                            final_norm_events[item] for item in criterion.norms
                        ),
                        criterion=criterion.id,
                    )
                )
            elif not selected:
                criterion_events.append(
                    self._emit(
                        ResolutionEventKind.CRITERION_INACTIVE,
                        rule.id,
                        record,
                        ("criteria", index),
                        causes=tuple(norm_events[item] for item in criterion.norms),
                        criterion=criterion.id,
                    )
                )
            else:
                self._fail(
                    ResolutionErrorCode.PARTIAL_CRITERION_APPLICABILITY,
                    f"criterion {criterion.id!r} has only some effective norms",
                    record,
                    ("criteria", index),
                )
        projection = ResolvedRuleProjection(
            rule.id,
            tuple(norm.id for norm in rule.norms if norm.id in final),
            tuple(effective_criteria),
        )
        return projection, tuple((*final_norm_events.values(), *criterion_events))

    def _evaluate_declaration(self, identifier: str) -> ApplicabilityTrace:
        cached = self.evaluations.get(identifier)
        if cached is not None:
            return cached
        record = self.registry.records[identifier]
        trace = self._evaluate_predicate(record.declaration.applicability)
        self.evaluations[identifier] = trace
        self._emit(
            ResolutionEventKind.DECLARATION_EVALUATED,
            identifier,
            record,
            ("applicability",),
            causes=tuple(self.discovery_causes[identifier]),
            anchor=self.anchors[identifier],
            truth=trace.result,
            applicability=trace,
        )
        return trace

    def _evaluate_predicate(
        self, predicate: Mapping[str, object]
    ) -> ApplicabilityTrace:
        assert self.context is not None
        return _evaluate_validated_applicability_with_trace(predicate, self.context)

    def _register_discovery(
        self, identifier: str, anchor: ManifestAnchor, event: int
    ) -> None:
        self.discovery_causes.setdefault(identifier, []).append(event)
        self._update_anchor(identifier, anchor)

    def _update_anchor(self, identifier: str, anchor: ManifestAnchor) -> bool:
        direct = self.direct_anchors.get(identifier)
        chosen = direct or anchor
        current = self.anchors.get(identifier)
        if current is None or (direct is None and chosen.rank < current.rank):
            self.anchors[identifier] = chosen
            return True
        if direct is not None and current != direct:
            self.anchors[identifier] = direct
            return True
        return False

    def _policies_for(self, pair: ConflictPair) -> tuple[RegisteredDeclaration, ...]:
        assert self.manifest is not None
        policies: list[RegisteredDeclaration] = []
        for identifier in self.manifest.policies:
            record = self.registry.records[identifier]
            policy = cast(ResolutionPolicyDeclaration, record.declaration)
            if tuple(sorted(policy.conflicts)) == pair:
                policies.append(record)
        return tuple(
            sorted(
                policies,
                key=lambda item: (
                    cast(ResolutionPolicyDeclaration, item.declaration).order,
                    item.declaration.id,
                ),
            )
        )

    def _conflict_source(
        self, pair: ConflictPair
    ) -> tuple[RegisteredDeclaration, DocumentPath]:
        for identifier in pair:
            record = self.registry.records[identifier]
            for index, relation in enumerate(record.declaration.relations):
                if relation.type == "incompatible-with" and relation.target in pair:
                    return record, ("relations", index, "target")
        raise AssertionError(f"registry conflict {pair!r} lacks provenance")

    def _fail_policy_result(
        self,
        proposal: _ConflictProposal,
        trace: ApplicabilityTrace,
    ) -> NoReturn:
        policy = cast(ResolutionPolicyDeclaration, proposal.policy_record.declaration)
        if policy.strategy.kind == "substitute":
            code = (
                ResolutionErrorCode.POLICY_SUBSTITUTE_INAPPLICABLE
                if trace.result is TruthValue.FALSE
                else ResolutionErrorCode.POLICY_SUBSTITUTE_INDETERMINATE
            )
        else:
            code = (
                ResolutionErrorCode.POLICY_COMBINE_RESULT_INAPPLICABLE
                if trace.result is TruthValue.FALSE
                else ResolutionErrorCode.POLICY_COMBINE_RESULT_INDETERMINATE
            )
        assert proposal.result is not None
        assert proposal.result_path is not None
        self._fail(
            code,
            f"policy result {proposal.result!r} is not applicable",
            proposal.policy_record,
            proposal.result_path,
            truth=trace.result,
            applicability=trace,
        )

    @staticmethod
    def _exclusion_path(policy: ResolutionPolicyDeclaration) -> DocumentPath:
        strategy = policy.strategy
        if strategy.kind == "retain":
            return ("strategy", "retain")
        if strategy.kind == "substitute":
            return ("strategy", "replace")
        return ("strategy", "kind")

    def _emit(
        self,
        kind: ResolutionEventKind,
        declaration: str,
        record: RegisteredDeclaration,
        path: DocumentPath,
        *,
        causes: tuple[int, ...] = (),
        **fields: object,
    ) -> int:
        admitted = _EVENT_FIELDS[kind]
        if frozenset(fields) != admitted:
            raise AssertionError(
                f"{kind.value} fields {sorted(fields)!r} do not match "
                f"{sorted(admitted)!r}"
            )
        ordinal = len(self.events)
        normalized_causes = tuple(sorted(set(causes)))
        if any(cause < 0 or cause >= ordinal for cause in normalized_causes):
            raise AssertionError("event causes must identify earlier events")
        values: dict[str, object] = {field: None for field in _OPTIONAL_EVENT_FIELDS}
        values.update(fields)
        event = object.__new__(ResolutionEvent)
        object.__setattr__(event, "ordinal", ordinal)
        object.__setattr__(event, "kind", kind)
        object.__setattr__(event, "declaration", declaration)
        object.__setattr__(event, "source", self._source(record, path))
        object.__setattr__(event, "causes", normalized_causes)
        for field, value in values.items():
            object.__setattr__(event, field, value)
        self.events.append(event)
        return ordinal

    def _source(
        self, record: RegisteredDeclaration, path: DocumentPath
    ) -> ResolutionSource:
        absolute = record.root + path
        location = nearest_location(record.source.locations, absolute)
        if location is None:
            raise AssertionError(f"source location missing for {absolute!r}")
        return ResolutionSource(
            record.source.path.resolve(),
            absolute,
            location.line,
            location.column,
        )

    def _trace(self) -> ResolutionTrace:
        facets = cast(CompositeFacetRegistry, self.registry.facet_registry)
        facets.require_authority()
        facet_registry = facets.id
        facet_content_revision = facets.content_revision
        facets.require_authority()
        trace = object.__new__(ResolutionTrace)
        object.__setattr__(trace, "manifest", self.manifest_id)
        object.__setattr__(trace, "facet_registry", facet_registry)
        object.__setattr__(
            trace,
            "facet_content_revision",
            facet_content_revision,
        )
        object.__setattr__(trace, "events", tuple(self.events))
        return trace

    def _fail(
        self,
        code: ResolutionErrorCode,
        detail: str,
        record: RegisteredDeclaration,
        path: DocumentPath,
        *,
        truth: TruthValue | None = None,
        applicability: ApplicabilityTrace | None = None,
    ) -> NoReturn:
        raise ResolutionError(
            code,
            detail,
            source=self._source(record, path),
            trace=self._trace(),
            truth=truth,
            applicability=applicability,
        )


def _issue_compilation_unit(
    manifest: str,
    components: tuple[ResolvedComponent, ...],
    dependencies: tuple[ResolvedDependency, ...],
    projections: tuple[ResolvedRuleProjection, ...],
) -> ResolvedCompilationUnit:
    """Issue one compilation unit after every semantic phase succeeds."""
    unit = object.__new__(ResolvedCompilationUnit)
    object.__setattr__(unit, "manifest", manifest)
    object.__setattr__(unit, "components", components)
    object.__setattr__(unit, "dependencies", dependencies)
    object.__setattr__(unit, "rule_projections", projections)
    return unit


def _issue_result(
    registry: DeclarationRegistry,
    manifest_record: RegisteredDeclaration,
    context: Mapping[str, JsonValue],
    unit: ResolvedCompilationUnit,
    trace: ResolutionTrace,
) -> ResolutionResult:
    """Issue one successful result with its correlated immutable trace."""
    result = object.__new__(ResolutionResult)
    object.__setattr__(result, "registry", registry)
    object.__setattr__(result, "manifest_record", manifest_record)
    object.__setattr__(result, "context", context)
    object.__setattr__(result, "unit", unit)
    object.__setattr__(result, "trace", trace)
    object.__setattr__(
        result, "_facet_registry_state", _capture_facet_registry_state(registry)
    )
    object.__setattr__(result, "_issuer", _RESOLUTION_RESULT_ISSUER)
    state = _capture_resolution_authority_state(result)
    token = _RESOLUTION_AUTHORITIES.issue(result, state)
    object.__setattr__(result, "_token", token)
    object.__setattr__(result, "_state", state)
    return result
