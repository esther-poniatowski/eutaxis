"""Build deterministic cross-record indexes for structured declarations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping, NoReturn, TypeAlias, cast

from .embedded_schema import normalize_json_subschema, validate_json_subschema
from .exceptions import DeclarationRegistryError
from .facets import FacetRegistry
from .loader import LoadedDeclarationSource, load_declaration_source
from .models import (
    AnyDeclaration,
    CompositionManifestDeclaration,
    DeclarationKind,
    EvaluatorDeclaration,
    OperationDeclaration,
    ParameterBinding,
    Predicate,
    ProcedureDeclaration,
    ResolutionPolicyDeclaration,
    RuleDeclaration,
    RuleSetDeclaration,
    VersionedReference,
    json_values_equal,
)
from .source import DocumentPath, format_document_path, nearest_location

ContentDeclaration: TypeAlias = (
    RuleSetDeclaration | RuleDeclaration | ProcedureDeclaration
)
ExactDeclaration: TypeAlias = EvaluatorDeclaration | OperationDeclaration
ConflictPair: TypeAlias = tuple[str, str]


@dataclass(frozen=True)
class RegisteredDeclaration:
    """One indexed declaration with source-relative diagnostic provenance."""

    declaration: AnyDeclaration
    source: LoadedDeclarationSource
    root: DocumentPath
    containing_rule_set: str | None


@dataclass(frozen=True)
class ContractFamily:
    """One evaluator or operation family indexed by exact version."""

    id: str
    kind: DeclarationKind
    owner: str
    versions: Mapping[int, RegisteredDeclaration]


@dataclass(frozen=True)
class DeclarationRegistry:
    """An immutable, cross-record validated declaration index."""

    paths: tuple[Path, ...]
    records: Mapping[str, RegisteredDeclaration]
    families: Mapping[str, ContractFamily]
    conflicts: frozenset[ConflictPair]


@dataclass(frozen=True)
class _RelationEdge:
    """One validated directional edge and its referring field."""

    source: str
    target: str
    record: RegisteredDeclaration
    path: DocumentPath


@dataclass
class _FamilyState:
    """Mutable exact-family state used only while the registry is built."""

    kind: DeclarationKind
    owner: str
    versions: dict[int, RegisteredDeclaration]


def load_declaration_registry(
    paths: Iterable[Path], facets: FacetRegistry
) -> DeclarationRegistry:
    """Load and cross-validate a deterministic declaration corpus."""
    return _RegistryBuilder(paths, facets).build()


class _RegistryBuilder:
    """Index sources first, then validate contracts against the closed index."""

    def __init__(self, paths: Iterable[Path], facets: FacetRegistry) -> None:
        self.paths = tuple(
            sorted({path.resolve() for path in paths}, key=lambda path: str(path))
        )
        self.facets = facets
        self.records: dict[str, RegisteredDeclaration] = {}
        self.families: dict[str, _FamilyState] = {}
        self.all_records: list[RegisteredDeclaration] = []
        self.conflicts: dict[ConflictPair, _RelationEdge] = {}
        self.dependency_edges: dict[str, list[_RelationEdge]] = {}
        self.supersedes_edges: dict[str, list[_RelationEdge]] = {}

    def build(self) -> DeclarationRegistry:
        """Return the immutable registry after every validation phase passes."""
        self._index_sources()
        self._validate_relations()
        self._reject_cycles(self.dependency_edges, "dependency")
        self._reject_cycles(self.supersedes_edges, "supersedes")
        self._validate_exact_references()
        self._validate_policies()
        self._validate_manifests()
        families = {
            identifier: ContractFamily(
                id=identifier,
                kind=family.kind,
                owner=family.owner,
                versions=MappingProxyType(dict(family.versions)),
            )
            for identifier, family in self.families.items()
        }
        return DeclarationRegistry(
            paths=self.paths,
            records=MappingProxyType(dict(self.records)),
            families=MappingProxyType(families),
            conflicts=frozenset(self.conflicts),
        )

    def _index_sources(self) -> None:
        """Register top-level declarations and embedded rules in source order."""
        for path in self.paths:
            source = load_declaration_source(path, facets=self.facets)
            declaration = source.declaration
            self._register(declaration, source, (), containing_rule_set=None)
            if isinstance(declaration, RuleSetDeclaration):
                for index, rule in enumerate(declaration.rules):
                    self._register(
                        rule,
                        source,
                        ("rules", index),
                        containing_rule_set=declaration.id,
                    )

    def _register(
        self,
        declaration: AnyDeclaration,
        source: LoadedDeclarationSource,
        root: DocumentPath,
        *,
        containing_rule_set: str | None,
    ) -> None:
        """Insert one record or exact contract at its deterministic position."""
        record = RegisteredDeclaration(
            declaration=declaration,
            source=source,
            root=root,
            containing_rule_set=containing_rule_set,
        )
        identifier = declaration.id
        if isinstance(declaration, (EvaluatorDeclaration, OperationDeclaration)):
            self._register_exact(record, declaration)
            self.all_records.append(record)
            return
        if identifier in self.records or identifier in self.families:
            self._raise(record, ("id",), f"duplicate declaration id {identifier!r}")
        self.records[identifier] = record
        self.all_records.append(record)

    def _register_exact(
        self, record: RegisteredDeclaration, declaration: ExactDeclaration
    ) -> None:
        """Insert one version while preserving its family kind and owner."""
        identifier = declaration.id
        if identifier in self.records:
            self._raise(record, ("id",), f"duplicate declaration id {identifier!r}")
        family = self.families.get(identifier)
        if family is None:
            self.families[identifier] = _FamilyState(
                kind=declaration.kind,
                owner=declaration.owner,
                versions={declaration.version: record},
            )
            return
        if family.kind is not declaration.kind:
            self._raise(
                record,
                ("kind",),
                f"contract family {identifier!r} changes declaration kind",
            )
        if family.owner != declaration.owner:
            self._raise(
                record,
                ("owner",),
                f"contract family {identifier!r} changes owner",
            )
        if declaration.version in family.versions:
            self._raise(
                record,
                ("version",),
                f"duplicate contract version {identifier!r}@{declaration.version}",
            )
        family.versions[declaration.version] = record

    def _validate_relations(self) -> None:
        """Resolve content edges and normalize incompatibility pairs."""
        for record in self.all_records:
            declaration = record.declaration
            if not _is_content(declaration):
                if declaration.relations:
                    self._raise(
                        record,
                        ("relations", 0),
                        f"{declaration.kind.value} records cannot declare relations",
                    )
                continue
            seen: set[tuple[str, str, str]] = set()
            for index, relation in enumerate(declaration.relations):
                path = ("relations", index, "target")
                triple = (declaration.id, relation.type, relation.target)
                if triple in seen:
                    self._raise(record, path, f"duplicate relation {relation.type!r}")
                seen.add(triple)
                target = self._content(record, relation.target, path)
                if target.declaration.id == declaration.id:
                    self._raise(record, path, "a declaration cannot relate to itself")
                edge = _RelationEdge(
                    source=declaration.id,
                    target=relation.target,
                    record=record,
                    path=path,
                )
                if relation.type in {"requires", "refines"}:
                    self.dependency_edges.setdefault(declaration.id, []).append(edge)
                elif relation.type == "supersedes":
                    self.supersedes_edges.setdefault(declaration.id, []).append(edge)
                elif relation.type == "incompatible-with":
                    pair = _conflict_pair(declaration.id, relation.target)
                    if pair in self.conflicts:
                        self._raise(
                            record,
                            path,
                            f"duplicate incompatibility pair {pair!r}",
                        )
                    self.conflicts[pair] = edge

    def _reject_cycles(
        self, edges: Mapping[str, list[_RelationEdge]], graph_name: str
    ) -> None:
        """Reject the deterministic edge that closes a directed graph cycle."""
        states: dict[str, int] = {}

        def visit(identifier: str) -> None:
            states[identifier] = 1
            for edge in edges.get(identifier, []):
                if states.get(edge.target) == 1:
                    self._raise(
                        edge.record,
                        edge.path,
                        f"{graph_name} relation closes a cycle",
                    )
                if states.get(edge.target, 0) == 0:
                    visit(edge.target)
            states[identifier] = 2

        for identifier, record in self.records.items():
            if _is_content(record.declaration) and states.get(identifier, 0) == 0:
                visit(identifier)

    def _validate_exact_references(self) -> None:
        """Resolve every evaluator and operation reference by exact version."""
        for record in self.all_records:
            declaration = record.declaration
            if isinstance(declaration, RuleDeclaration):
                for index, criterion in enumerate(declaration.criteria):
                    self._exact(
                        record,
                        criterion.evaluator,
                        DeclarationKind.EVALUATOR,
                        ("criteria", index, "evaluator"),
                    )
            elif isinstance(declaration, ProcedureDeclaration):
                self._validate_predicate_references(record, declaration)
                self._validate_procedure_actions(record, declaration)
            elif isinstance(declaration, OperationDeclaration):
                for index, predicate in enumerate(declaration.preconditions):
                    self._predicate_reference(
                        record, predicate, ("preconditions", index)
                    )

    def _validate_predicate_references(
        self, record: RegisteredDeclaration, procedure: ProcedureDeclaration
    ) -> None:
        """Resolve evaluator references from every procedure predicate class."""
        for field in ("preconditions", "invariants", "postconditions"):
            predicates = getattr(procedure, field)
            for index, predicate in enumerate(predicates):
                self._predicate_reference(record, predicate, (field, index))

    def _predicate_reference(
        self,
        record: RegisteredDeclaration,
        predicate: Predicate,
        path: DocumentPath,
    ) -> None:
        """Resolve one optional evaluator reference owned by a predicate."""
        if predicate.evaluator is not None:
            self._exact(
                record,
                predicate.evaluator,
                DeclarationKind.EVALUATOR,
                path + ("evaluator",),
            )

    def _validate_procedure_actions(
        self, record: RegisteredDeclaration, procedure: ProcedureDeclaration
    ) -> None:
        """Validate each action against its referenced operation contract."""
        parameter_schemas = _property_schemas(procedure.parameters)
        authorized_effects = set(procedure.effects)
        for action_index, action in enumerate(procedure.actions):
            action_path: DocumentPath = ("actions", action_index)
            operation_record = self._exact(
                record,
                action.operation,
                DeclarationKind.OPERATION,
                action_path + ("operation",),
            )
            operation = operation_record.declaration
            assert isinstance(operation, OperationDeclaration)
            input_schemas = _property_schemas(operation.inputs)
            required_inputs = _required_properties(operation.inputs)

            missing_inputs = tuple(
                name for name in required_inputs if name not in action.bindings
            )
            if missing_inputs:
                source_action = _source_action(record, action_index)
                owner = (
                    action_path + ("with",) if "with" in source_action else action_path
                )
                self._raise(
                    record,
                    owner,
                    f"missing required operation inputs {missing_inputs!r}",
                )

            for input_name, binding in action.bindings.items():
                binding_path = action_path + ("with", input_name)
                input_schema = input_schemas.get(input_name)
                if input_schema is None:
                    self._raise(
                        record,
                        binding_path,
                        f"unknown operation input {input_name!r}",
                    )
                if isinstance(binding, ParameterBinding):
                    parameter_schema = parameter_schemas.get(binding.parameter)
                    if parameter_schema is None:
                        self._raise(
                            record,
                            binding_path + ("parameter",),
                            f"unknown procedure parameter {binding.parameter!r}",
                        )
                    normalized_parameter = normalize_json_subschema(
                        cast(Mapping[str, object], procedure.parameters),
                        ("properties", binding.parameter),
                    )
                    normalized_input = normalize_json_subschema(
                        cast(Mapping[str, object], operation.inputs),
                        ("properties", input_name),
                    )
                    if not json_values_equal(normalized_parameter, normalized_input):
                        self._raise(
                            record,
                            binding_path + ("parameter",),
                            "procedure parameter schema differs from operation input schema",
                        )
                    continue
                error = validate_json_subschema(
                    cast(Mapping[str, object], operation.inputs),
                    ("properties", input_name),
                    binding.value,
                )
                if error is not None:
                    instance_path = cast(DocumentPath, tuple(error.absolute_path))
                    self._raise(
                        record,
                        binding_path + ("literal",) + instance_path,
                        f"literal does not satisfy operation input schema: {error.message}",
                    )

            missing_outcomes = tuple(
                outcome
                for outcome in operation.failure_outcomes
                if outcome not in action.on_failure
            )
            if missing_outcomes:
                self._raise(
                    record,
                    action_path + ("on-failure",),
                    f"missing operation failure outcomes {missing_outcomes!r}",
                )
            for outcome in action.on_failure:
                if outcome not in operation.failure_outcomes:
                    self._raise(
                        record,
                        action_path + ("on-failure", outcome),
                        f"unknown operation failure outcome {outcome!r}",
                    )

            if not set(operation.effects).issubset(authorized_effects):
                self._raise(
                    record,
                    action_path + ("operation",),
                    "operation effects exceed the procedure mutation footprint",
                )
            operation_effects = set(operation.effects)
            for invariant_index, invariant in enumerate(procedure.invariants):
                for observed_index, observed in enumerate(invariant.observes):
                    if observed in operation_effects:
                        self._raise(
                            record,
                            ("invariants", invariant_index, "observes", observed_index),
                            f"operation may mutate invariant-observed state {observed!r}",
                        )

    def _exact(
        self,
        record: RegisteredDeclaration,
        reference: VersionedReference,
        expected_kind: DeclarationKind,
        path: DocumentPath,
    ) -> RegisteredDeclaration:
        """Resolve one typed exact reference with split family/version errors."""
        family = self.families.get(reference.id)
        if family is None:
            self._raise(
                record,
                path + ("id",),
                f"unknown contract family {reference.id!r}",
            )
        if family.kind is not expected_kind:
            self._raise(
                record,
                path + ("id",),
                f"contract family {reference.id!r} is not an {expected_kind.value}",
            )
        target = family.versions.get(reference.version)
        if target is None:
            self._raise(
                record,
                path + ("version",),
                f"unknown contract version {reference.id!r}@{reference.version}",
            )
        return target

    def _validate_policies(self) -> None:
        """Validate conflict pairs and type-preserving strategy targets."""
        for record in self.records.values():
            policy = record.declaration
            if not isinstance(policy, ResolutionPolicyDeclaration):
                continue
            members = tuple(
                self._content(record, identifier, ("conflicts", index))
                for index, identifier in enumerate(policy.conflicts)
            )
            pair = _conflict_pair(*policy.conflicts)
            if pair not in self.conflicts:
                self._raise(
                    record,
                    ("conflicts",),
                    f"conflict pair {pair!r} has no incompatible-with relation",
                )
            strategy = policy.strategy
            if strategy.kind == "substitute":
                assert strategy.replace is not None
                assert strategy.replacement is not None
                replaced = members[policy.conflicts.index(strategy.replace)]
                replacement = self._content(
                    record, strategy.replacement, ("strategy", "with")
                )
                if replacement.declaration.kind is not replaced.declaration.kind:
                    self._raise(
                        record,
                        ("strategy", "with"),
                        "substitute must preserve the replaced declaration kind",
                    )
            elif strategy.kind == "combine":
                assert strategy.result is not None
                if members[0].declaration.kind is not members[1].declaration.kind:
                    self._raise(
                        record,
                        ("strategy", "kind"),
                        "combine requires conflict members of the same kind",
                    )
                result = self._content(record, strategy.result, ("strategy", "result"))
                if result.declaration.kind is not members[0].declaration.kind:
                    self._raise(
                        record,
                        ("strategy", "result"),
                        "combine result must preserve the conflict member kind",
                    )

    def _validate_manifests(self) -> None:
        """Resolve manifest selections, policy authority, and local order ties."""
        for record in self.records.values():
            manifest = record.declaration
            if not isinstance(manifest, CompositionManifestDeclaration):
                continue
            for section_index, section in enumerate(manifest.sections):
                for item_index, identifier in enumerate(section.declarations):
                    self._content(
                        record,
                        identifier,
                        ("sections", section_index, "declarations", item_index),
                    )
            seen_orders: set[tuple[ConflictPair, int]] = set()
            for index, identifier in enumerate(manifest.policies):
                path = ("policies", index)
                target = self.records.get(identifier)
                if target is None or not isinstance(
                    target.declaration, ResolutionPolicyDeclaration
                ):
                    self._raise(
                        record,
                        path,
                        f"manifest policy {identifier!r} is not a resolution-policy",
                    )
                policy = target.declaration
                if policy.owner != manifest.owner:
                    self._raise(
                        record,
                        path,
                        f"policy {identifier!r} is not owned by the manifest owner",
                    )
                key = (_conflict_pair(*policy.conflicts), policy.order)
                if key in seen_orders:
                    self._raise(
                        record,
                        path,
                        f"duplicate policy order {policy.order} for conflict {key[0]!r}",
                    )
                seen_orders.add(key)

    def _content(
        self,
        referring_record: RegisteredDeclaration,
        identifier: str,
        path: DocumentPath,
    ) -> RegisteredDeclaration:
        """Resolve one identifier as an unversioned content record."""
        target = self.records.get(identifier)
        if target is None:
            if identifier in self.families:
                message = f"{identifier!r} is an exact contract, not content"
            else:
                message = f"unknown content declaration {identifier!r}"
            self._raise(referring_record, path, message)
        if not _is_content(target.declaration):
            self._raise(
                referring_record,
                path,
                f"{identifier!r} is not a content declaration",
            )
        return target

    def _raise(
        self, record: RegisteredDeclaration, path: DocumentPath, message: str
    ) -> NoReturn:
        """Raise one located registry error relative to an indexed record."""
        absolute_path = record.root + path
        source = nearest_location(record.source.locations, absolute_path)
        raise DeclarationRegistryError(
            record.source.path,
            format_document_path(absolute_path),
            message,
            line=source.line if source else None,
            column=source.column if source else None,
        )


def _is_content(declaration: AnyDeclaration) -> bool:
    """Return whether a declaration may participate in semantic resolution."""
    return isinstance(
        declaration, (RuleSetDeclaration, RuleDeclaration, ProcedureDeclaration)
    )


def _conflict_pair(left: str, right: str) -> ConflictPair:
    """Return the canonical unordered representation of one conflict pair."""
    return (left, right) if left < right else (right, left)


def _property_schemas(
    schema: Mapping[str, object],
) -> Mapping[str, object]:
    """Return properties from a locally validated closed object schema."""
    properties = schema["properties"]
    assert isinstance(properties, Mapping)
    return cast(Mapping[str, object], properties)


def _required_properties(schema: Mapping[str, object]) -> tuple[str, ...]:
    """Return required property names in their declared order."""
    required = schema.get("required", ())
    assert isinstance(required, (list, tuple))
    return tuple(str(name) for name in required)


def _source_action(
    record: RegisteredDeclaration, action_index: int
) -> Mapping[str, object]:
    """Return one procedure action from the immutable source document."""
    actions = record.source.document["actions"]
    assert isinstance(actions, tuple)
    action = actions[action_index]
    assert isinstance(action, Mapping)
    return cast(Mapping[str, object], action)
