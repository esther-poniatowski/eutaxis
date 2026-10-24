"""Load canonical YAML declarations into immutable domain models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, NoReturn, TypedDict, cast

from .applicability import conjoin_applicability
from .exceptions import DeclarationSemanticError
from .facets import FacetRegistry, validate_declaration_facets
from .models import (
    Action,
    AnyDeclaration,
    Binding,
    CompositionManifestDeclaration,
    Criterion,
    DeclarationKind,
    EvaluatorDeclaration,
    ExceptionClause,
    JsonValue,
    LiteralBinding,
    ManifestSection,
    Norm,
    OperationDeclaration,
    ParameterBinding,
    Predicate,
    ProcedureDeclaration,
    ProcedureNode,
    Relation,
    ResolutionPolicyDeclaration,
    ResolutionStrategy,
    RuleAxis,
    RuleDeclaration,
    RuleSetDeclaration,
    VersionedReference,
    freeze_json,
)
from .schema import validate_document, validate_embedded_schema
from .source import (
    DocumentPath,
    SourceMap,
    format_document_path,
    load_yaml_document,
    nearest_location,
)


class _BaseFields(TypedDict):
    """Constructor fields shared by every declaration model."""

    schema_version: int
    id: str
    kind: DeclarationKind
    owner: str
    status: str
    source_revision: str
    applicability: Mapping[str, JsonValue]
    relations: tuple[Relation, ...]
    title: str | None
    rationale: str | None
    document: Mapping[str, JsonValue]


@dataclass(frozen=True)
class LoadedDeclarationSource:
    """One validated declaration with the source data needed by registries."""

    path: Path
    declaration: AnyDeclaration
    document: Mapping[str, JsonValue]
    locations: SourceMap


def load_declaration(path: Path) -> AnyDeclaration:
    """Load one declaration through its local source-boundary validation."""
    return load_declaration_source(path).declaration


def load_facet_validated_declaration(
    path: Path, facets: FacetRegistry
) -> AnyDeclaration:
    """Load a declaration after validating every applicability facet."""
    return load_declaration_source(path, facets=facets).declaration


def load_declaration_source(
    path: Path, *, facets: FacetRegistry | None = None
) -> LoadedDeclarationSource:
    """Load one declaration and retain its immutable document and source map."""
    document, locations = load_yaml_document(path)
    validated = validate_document(document, path=path, locations=locations)
    if facets is not None:
        validate_declaration_facets(
            validated,
            facets,
            path=path,
            locations=locations,
        )
    _validate_semantics(validated, path=path, locations=locations)
    declaration = _build_declaration(validated)
    return LoadedDeclarationSource(
        path=path,
        declaration=declaration,
        document=declaration.document,
        locations=MappingProxyType(locations),
    )


def _mapping(value: object) -> Mapping[str, object]:
    """Narrow a mapping already guaranteed by schema validation."""
    return cast(Mapping[str, object], value)


def _frozen_mapping(value: object) -> Mapping[str, JsonValue]:
    """Freeze a schema-validated JSON object."""
    return cast(Mapping[str, JsonValue], freeze_json(value))


def _reference(value: object) -> VersionedReference:
    """Build one structured versioned reference."""
    item = _mapping(value)
    return VersionedReference(id=str(item["id"]), version=cast(int, item["version"]))


def _predicate(value: object) -> Predicate:
    """Build one typed predicate."""
    item = _mapping(value)
    evaluator = item.get("evaluator")
    return Predicate(
        id=str(item["id"]),
        predicate_class=str(item["class"]),
        expression=_frozen_mapping(item["expression"]),
        evaluator=_reference(evaluator) if evaluator is not None else None,
        observes=tuple(
            str(state) for state in cast(list[object], item.get("observes", []))
        ),
    )


def _binding(value: object) -> Binding:
    """Build one explicit parameter or literal binding."""
    item = _mapping(value)
    if "parameter" in item:
        return ParameterBinding(parameter=str(item["parameter"]))
    return LiteralBinding(value=freeze_json(item["literal"]))


def _bindings(value: object) -> Mapping[str, Binding]:
    """Build an immutable mapping of operation inputs to bindings."""
    return MappingProxyType(
        {str(name): _binding(binding) for name, binding in _mapping(value).items()}
    )


def _base(
    document: Mapping[str, object],
    *,
    applicability: Mapping[str, object] | None = None,
) -> _BaseFields:
    """Build fields shared by every declaration model."""
    return {
        "schema_version": cast(int, document["schema-version"]),
        "id": str(document["id"]),
        "kind": DeclarationKind(str(document["kind"])),
        "owner": str(document["owner"]),
        "status": str(document["status"]),
        "source_revision": str(document["source-revision"]),
        "applicability": _frozen_mapping(
            applicability if applicability is not None else document["applicability"]
        ),
        "relations": tuple(
            Relation(type=str(item["type"]), target=str(item["target"]))
            for item in map(_mapping, cast(list[object], document["relations"]))
        ),
        "title": str(document["title"]) if "title" in document else None,
        "rationale": (str(document["rationale"]) if "rationale" in document else None),
        "document": _frozen_mapping(document),
    }


def _build_rule(
    document: Mapping[str, object],
    *,
    inherited_applicability: Mapping[str, object] | None = None,
) -> RuleDeclaration:
    """Build one rule and expand every inherited applicability predicate."""
    applicability = _mapping(document["applicability"])
    if inherited_applicability is not None:
        applicability = conjoin_applicability(inherited_applicability, applicability)

    norms: list[Norm] = []
    for value in cast(list[object], document["norms"]):
        item = _mapping(value)
        norm_applicability = applicability
        if "applies-when" in item:
            norm_applicability = conjoin_applicability(
                applicability, _mapping(item["applies-when"])
            )
        action = _mapping(item["action"])
        norms.append(
            Norm(
                id=str(item["id"]),
                modality=str(item["modality"]),
                subject=str(item["subject"]),
                action=Action(
                    verb=str(action["verb"]),
                    object=str(action["object"]),
                    timing=str(action["timing"]) if "timing" in action else None,
                ),
                applicability=_frozen_mapping(norm_applicability),
                guidance=str(item["guidance"]) if "guidance" in item else None,
                rationale=str(item["rationale"]) if "rationale" in item else None,
                decision_criterion=(
                    str(item["decision-criterion"])
                    if "decision-criterion" in item
                    else None
                ),
            )
        )

    criteria = tuple(
        Criterion(
            id=str(item["id"]),
            norms=tuple(str(norm) for norm in cast(list[object], item["norms"])),
            evaluator=_reference(item["evaluator"]),
            statement=str(item["statement"]),
        )
        for item in map(_mapping, cast(list[object], document["criteria"]))
    )
    exceptions = tuple(
        ExceptionClause(
            id=str(item["id"]),
            when=_frozen_mapping(
                conjoin_applicability(applicability, _mapping(item["when"]))
            ),
            disposition=str(item["disposition"]),
            affects=tuple(
                str(identifier) for identifier in cast(list[object], item["affects"])
            ),
            substitutes=tuple(
                str(identifier)
                for identifier in cast(list[object], item.get("substitutes", []))
            ),
        )
        for item in map(_mapping, cast(list[object], document.get("exceptions", [])))
    )
    return RuleDeclaration(
        **_base(document, applicability=applicability),
        axis=RuleAxis(str(document["axis"])),
        failure_mode=str(document["failure-mode"]),
        required_visibility=(
            str(document["required-visibility"])
            if "required-visibility" in document
            else None
        ),
        norms=tuple(norms),
        criteria=criteria,
        exceptions=exceptions,
    )


def _build_declaration(document: Mapping[str, object]) -> AnyDeclaration:
    """Dispatch one validated mapping to its complete typed model."""
    kind = DeclarationKind(str(document["kind"]))
    if kind is DeclarationKind.RULE:
        return _build_rule(document)
    if kind is DeclarationKind.RULE_SET:
        return RuleSetDeclaration(
            **_base(document),
            purpose=str(document["purpose"]),
            rules=tuple(
                _build_rule(
                    item,
                    inherited_applicability=_mapping(document["applicability"]),
                )
                for item in map(_mapping, cast(list[object], document["rules"]))
            ),
        )
    if kind is DeclarationKind.PROCEDURE:
        return ProcedureDeclaration(
            **_base(document),
            purpose=str(document["purpose"]),
            parameters=_frozen_mapping(document["parameters"]),
            preconditions=tuple(
                _predicate(item)
                for item in cast(list[object], document["preconditions"])
            ),
            actions=tuple(
                ProcedureNode(
                    id=str(item["id"]),
                    operation=_reference(item["operation"]),
                    bindings=_bindings(item.get("with", {})),
                    on_success=str(item["on-success"]),
                    on_failure=MappingProxyType(
                        {
                            str(outcome): str(target)
                            for outcome, target in _mapping(item["on-failure"]).items()
                        }
                    ),
                )
                for item in map(_mapping, cast(list[object], document["actions"]))
            ),
            entry=str(document["entry"]),
            invariants=tuple(
                _predicate(item) for item in cast(list[object], document["invariants"])
            ),
            effects=tuple(
                str(item) for item in cast(list[object], document["effects"])
            ),
            postconditions=tuple(
                _predicate(item)
                for item in cast(list[object], document["postconditions"])
            ),
            failures=tuple(
                str(item) for item in cast(list[object], document["failures"])
            ),
        )
    if kind is DeclarationKind.RESOLUTION_POLICY:
        conflicts = tuple(
            str(item) for item in cast(list[object], document["conflicts"])
        )
        strategy = _mapping(document["strategy"])
        return ResolutionPolicyDeclaration(
            **_base(document),
            conflicts=(conflicts[0], conflicts[1]),
            when=_frozen_mapping(document["when"]),
            order=cast(int, document["order"]),
            strategy=ResolutionStrategy(
                kind=str(strategy["kind"]),
                retain=str(strategy["retain"]) if "retain" in strategy else None,
                replace=str(strategy["replace"]) if "replace" in strategy else None,
                replacement=str(strategy["with"]) if "with" in strategy else None,
                result=str(strategy["result"]) if "result" in strategy else None,
            ),
        )
    if kind is DeclarationKind.COMPOSITION_MANIFEST:
        return CompositionManifestDeclaration(
            **_base(document),
            scope=str(document["scope"]),
            target=str(document["target"]),
            sections=tuple(
                ManifestSection(
                    id=str(item["id"]),
                    declarations=tuple(
                        str(identifier)
                        for identifier in cast(list[object], item["declarations"])
                    ),
                )
                for item in map(_mapping, cast(list[object], document["sections"]))
            ),
            policies=tuple(
                str(item) for item in cast(list[object], document.get("policies", []))
            ),
        )
    if kind is DeclarationKind.EVALUATOR:
        return EvaluatorDeclaration(
            **_base(document),
            version=cast(int, document["version"]),
            evaluator_kind=str(document["evaluator-kind"]),
            coverage=str(document["coverage"]),
            adjudication=str(document["adjudication"]),
            timing=str(document["timing"]),
            input_revisions=tuple(
                str(item) for item in cast(list[object], document["input-revisions"])
            ),
            evidence_schema=_frozen_mapping(document["evidence-schema"]),
            failure_behavior=str(document["failure-behavior"]),
            known_failure_fixtures=tuple(
                str(item)
                for item in cast(
                    list[object], document.get("known-failure-fixtures", [])
                )
            ),
        )
    if kind is DeclarationKind.OPERATION:
        return OperationDeclaration(
            **_base(document),
            version=cast(int, document["version"]),
            inputs=_frozen_mapping(document["inputs"]),
            outputs=_frozen_mapping(document["outputs"]),
            preconditions=tuple(
                _predicate(item)
                for item in cast(list[object], document["preconditions"])
            ),
            effects=tuple(
                str(item) for item in cast(list[object], document["effects"])
            ),
            failure_outcomes=tuple(
                str(item) for item in cast(list[object], document["failure-outcomes"])
            ),
            recovery=str(document["recovery"]),
        )
    raise AssertionError(f"Unhandled declaration kind: {kind}")


def _validate_semantics(
    document: Mapping[str, object], *, path: Path, locations: SourceMap
) -> None:
    """Validate cross-field invariants outside JSON Schema's scope."""
    _validate_unique_ids(document, path=path, locations=locations)
    kind = document["kind"]
    if kind == "rule":
        _validate_rule_references(document, (), path=path, locations=locations)
    elif kind == "rule-set":
        for index, rule in enumerate(cast(list[object], document["rules"])):
            _validate_rule_references(
                _mapping(rule),
                ("rules", index),
                path=path,
                locations=locations,
            )
    elif kind == "procedure":
        validate_embedded_schema(
            document["parameters"],
            path=path,
            document_path=("parameters",),
            locations=locations,
        )
        _validate_closed_object_schema(
            document["parameters"],
            ("parameters",),
            path=path,
            locations=locations,
        )
        _validate_predicate_roles(document, path=path, locations=locations)
        _validate_procedure_bindings(document, path=path, locations=locations)
        _validate_procedure_graph(document, path=path, locations=locations)
    elif kind == "resolution-policy":
        _validate_resolution_policy(document, path=path, locations=locations)
    elif kind == "evaluator":
        validate_embedded_schema(
            document["evidence-schema"],
            path=path,
            document_path=("evidence-schema",),
            locations=locations,
        )
    elif kind == "operation":
        for field in ("inputs", "outputs"):
            validate_embedded_schema(
                document[field],
                path=path,
                document_path=(field,),
                locations=locations,
            )
        _validate_closed_object_schema(
            document["inputs"],
            ("inputs",),
            path=path,
            locations=locations,
        )
        _validate_predicate_list(
            cast(list[object], document["preconditions"]),
            allowed={"guard", "authorization", "assumption", "dependency"},
            parts=("preconditions",),
            path=path,
            locations=locations,
        )


def _validate_unique_ids(
    document: Mapping[str, object], *, path: Path, locations: SourceMap
) -> None:
    """Validate identifier uniqueness within every local scope."""
    kind = document["kind"]
    if kind == "rule":
        _validate_rule_local_ids(document, (), path=path, locations=locations)
    elif kind == "rule-set":
        rules = [_mapping(item) for item in cast(list[object], document["rules"])]
        identifiers = [
            (str(document["id"]), ("id",)),
            *(
                (str(rule["id"]), ("rules", index, "id"))
                for index, rule in enumerate(rules)
            ),
        ]
        _ensure_unique(
            identifiers,
            scope="rule set and its members",
            path=path,
            locations=locations,
        )
        for index, rule in enumerate(rules):
            _validate_rule_local_ids(
                rule, ("rules", index), path=path, locations=locations
            )
    elif kind == "procedure":
        identifiers = [
            (str(_mapping(item)["id"]), ("actions", index, "id"))
            for index, item in enumerate(cast(list[object], document["actions"]))
        ]
        for field in ("preconditions", "invariants", "postconditions"):
            identifiers.extend(
                (str(_mapping(item)["id"]), (field, index, "id"))
                for index, item in enumerate(cast(list[object], document[field]))
            )
        identifiers.extend(
            (str(item), ("failures", index))
            for index, item in enumerate(cast(list[object], document["failures"]))
        )
        _ensure_unique(
            identifiers,
            scope="procedure",
            path=path,
            locations=locations,
        )
    elif kind == "composition-manifest":
        _ensure_unique(
            [
                (str(_mapping(item)["id"]), ("sections", index, "id"))
                for index, item in enumerate(cast(list[object], document["sections"]))
            ],
            scope="composition manifest",
            path=path,
            locations=locations,
        )
    elif kind == "operation":
        _ensure_unique(
            [
                (str(_mapping(item)["id"]), ("preconditions", index, "id"))
                for index, item in enumerate(
                    cast(list[object], document["preconditions"])
                )
            ],
            scope="operation preconditions",
            path=path,
            locations=locations,
        )


def _validate_rule_local_ids(
    rule: Mapping[str, object],
    parts: DocumentPath,
    *,
    path: Path,
    locations: SourceMap,
) -> None:
    """Require local identifiers to be unique inside one rule."""
    identifiers = [
        (str(_mapping(item)["id"]), parts + ("norms", index, "id"))
        for index, item in enumerate(cast(list[object], rule["norms"]))
    ]
    identifiers.extend(
        (str(_mapping(item)["id"]), parts + ("criteria", index, "id"))
        for index, item in enumerate(cast(list[object], rule["criteria"]))
    )
    identifiers.extend(
        (str(_mapping(item)["id"]), parts + ("exceptions", index, "id"))
        for index, item in enumerate(cast(list[object], rule.get("exceptions", [])))
    )
    _ensure_unique(
        identifiers,
        scope=f"rule {rule['id']!r}",
        path=path,
        locations=locations,
    )


def _ensure_unique(
    identifiers: list[tuple[str, DocumentPath]],
    *,
    scope: str,
    path: Path,
    locations: SourceMap,
) -> None:
    """Reject the first repeated identifier in one declared scope."""
    seen: set[str] = set()
    for identifier, identifier_parts in identifiers:
        if identifier in seen:
            _semantic_error(
                path,
                locations,
                identifier_parts,
                f"duplicate id {identifier!r} in {scope}",
            )
        seen.add(identifier)


def _validate_rule_references(
    rule: Mapping[str, object],
    parts: DocumentPath,
    *,
    path: Path,
    locations: SourceMap,
) -> None:
    """Resolve every reference local to one rule."""
    norms = [_mapping(item) for item in cast(list[object], rule["norms"])]
    criteria = [_mapping(item) for item in cast(list[object], rule["criteria"])]
    exceptions = [
        _mapping(item) for item in cast(list[object], rule.get("exceptions", []))
    ]
    norm_ids = {str(item["id"]) for item in norms}
    criterion_ids = {str(item["id"]) for item in criteria}
    criteria_by_id = {str(item["id"]): item for item in criteria}
    exception_coverage: set[str] = set()
    affected_by: dict[str, str] = {}
    substituted_norms: set[str] = set()

    for index, exception in enumerate(exceptions):
        affects = {str(item) for item in cast(list[object], exception["affects"])}
        substitutes = {
            str(item) for item in cast(list[object], exception.get("substitutes", []))
        }
        unknown = sorted((affects | substitutes) - norm_ids)
        if unknown:
            _semantic_error(
                path,
                locations,
                parts + ("exceptions", index),
                f"exception {exception['id']!r} references unknown norms {unknown!r}",
            )
        overlap = sorted(affects & substitutes)
        if overlap:
            _semantic_error(
                path,
                locations,
                parts + ("exceptions", index),
                f"exception {exception['id']!r} substitutes affected norms {overlap!r} with themselves",
            )
        for norm_id in affects:
            previous = affected_by.get(norm_id)
            if previous is not None:
                _semantic_error(
                    path,
                    locations,
                    parts + ("exceptions", index, "affects"),
                    f"norm {norm_id!r} is affected by both {previous!r} and {exception['id']!r}",
                )
            affected_by[norm_id] = str(exception["id"])
        substituted_norms.update(substitutes)
        exception_coverage.update(affects)

    chained = sorted(set(affected_by) & substituted_norms)
    if chained:
        _semantic_error(
            path,
            locations,
            parts + ("exceptions",),
            f"version 1 exceptions require one-step substitutions; replacement norms are also affected {chained!r}",
        )

    for index, norm in enumerate(norms):
        decision = norm.get("decision-criterion")
        if decision is not None and str(decision) not in criterion_ids:
            _semantic_error(
                path,
                locations,
                parts + ("norms", index, "decision-criterion"),
                f"norm {norm['id']!r} references unknown decision criterion {decision!r}",
            )
        if decision is not None:
            criterion_norms = {
                str(item)
                for item in cast(list[object], criteria_by_id[str(decision)]["norms"])
            }
            if str(norm["id"]) not in criterion_norms:
                _semantic_error(
                    path,
                    locations,
                    parts + ("norms", index, "decision-criterion"),
                    f"decision criterion {decision!r} does not evaluate norm {norm['id']!r}",
                )
        if norm["modality"] in {"should", "should-not"}:
            norm_id = str(norm["id"])
            if decision is None and norm_id not in exception_coverage:
                _semantic_error(
                    path,
                    locations,
                    parts + ("norms", index),
                    f"recommended norm {norm_id!r} requires an exception or decision criterion",
                )

    for index, criterion in enumerate(criteria):
        unknown = sorted(
            {str(item) for item in cast(list[object], criterion["norms"])} - norm_ids
        )
        if unknown:
            _semantic_error(
                path,
                locations,
                parts + ("criteria", index, "norms"),
                f"criterion {criterion['id']!r} references unknown norms {unknown!r}",
            )


def _validate_predicate_roles(
    document: Mapping[str, object], *, path: Path, locations: SourceMap
) -> None:
    """Require each procedure predicate to occupy its declared role."""
    _validate_predicate_list(
        cast(list[object], document["preconditions"]),
        allowed={"guard", "authorization", "assumption", "dependency"},
        parts=("preconditions",),
        path=path,
        locations=locations,
    )
    _validate_predicate_list(
        cast(list[object], document["invariants"]),
        allowed={"invariant"},
        parts=("invariants",),
        path=path,
        locations=locations,
    )
    _validate_predicate_list(
        cast(list[object], document["postconditions"]),
        allowed={"postcondition"},
        parts=("postconditions",),
        path=path,
        locations=locations,
    )


def _validate_predicate_list(
    predicates: list[object],
    *,
    allowed: set[str],
    parts: DocumentPath,
    path: Path,
    locations: SourceMap,
) -> None:
    """Reject predicates whose class conflicts with their container."""
    for index, value in enumerate(predicates):
        predicate = _mapping(value)
        if predicate["class"] not in allowed:
            _semantic_error(
                path,
                locations,
                parts + (index, "class"),
                f"predicate class {predicate['class']!r} is not admitted in {parts[-1]!r}",
            )


def _validate_closed_object_schema(
    value: object,
    parts: DocumentPath,
    *,
    path: Path,
    locations: SourceMap,
) -> None:
    """Require every required member to have a declared property schema."""
    schema = _mapping(value)
    properties = _mapping(schema["properties"])
    for index, name in enumerate(cast(list[object], schema.get("required", []))):
        if str(name) not in properties:
            _semantic_error(
                path,
                locations,
                parts + ("required", index),
                f"required property {name!r} has no declared schema",
            )


def _validate_procedure_bindings(
    document: Mapping[str, object], *, path: Path, locations: SourceMap
) -> None:
    """Require parameter bindings to reference declared procedure parameters."""
    parameters = _mapping(_mapping(document["parameters"])["properties"])
    for action_index, action_value in enumerate(
        cast(list[object], document["actions"])
    ):
        action = _mapping(action_value)
        for input_name, binding_value in _mapping(action.get("with", {})).items():
            binding = _mapping(binding_value)
            parameter = binding.get("parameter")
            if parameter is not None and str(parameter) not in parameters:
                _semantic_error(
                    path,
                    locations,
                    ("actions", action_index, "with", input_name, "parameter"),
                    f"binding references unknown procedure parameter {parameter!r}",
                )


def _validate_procedure_graph(
    document: Mapping[str, object], *, path: Path, locations: SourceMap
) -> None:
    """Require a finite, total, acyclic, and reachable procedure graph."""
    actions = {
        str(node["id"]): node
        for node in map(_mapping, cast(list[object], document["actions"]))
    }
    entry = str(document["entry"])
    if entry not in actions:
        _semantic_error(
            path, locations, ("entry",), f"entry {entry!r} is not an action"
        )
    success = {
        str(_mapping(item)["id"])
        for item in cast(list[object], document["postconditions"])
    }
    failures = {str(item) for item in cast(list[object], document["failures"])}
    terminals = success | failures
    allowed = set(actions) | terminals
    for index, (node_id, node) in enumerate(actions.items()):
        success_target = str(node["on-success"])
        failure_targets = {
            str(target) for target in _mapping(node["on-failure"]).values()
        }
        targets = {success_target, *failure_targets}
        unknown = sorted(targets - allowed)
        if unknown:
            _semantic_error(
                path,
                locations,
                ("actions", index),
                f"action {node_id!r} targets unknown states {unknown!r}",
            )
        if success_target in failures:
            _semantic_error(
                path,
                locations,
                ("actions", index, "on-success"),
                f"action {node_id!r} routes success directly to a failure state",
            )
        misrouted_failures = sorted(failure_targets & success)
        if misrouted_failures:
            _semantic_error(
                path,
                locations,
                ("actions", index, "on-failure"),
                f"action {node_id!r} routes failure directly to postconditions {misrouted_failures!r}",
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def walk(node_id: str) -> None:
        if node_id in terminals:
            return
        if node_id in visiting:
            _semantic_error(
                path,
                locations,
                ("actions",),
                f"procedure contains a cycle at {node_id!r}",
            )
        if node_id in visited:
            return
        visiting.add(node_id)
        node = actions[node_id]
        walk(str(node["on-success"]))
        for target in _mapping(node["on-failure"]).values():
            walk(str(target))
        visiting.remove(node_id)
        visited.add(node_id)

    walk(entry)
    unreachable = sorted(set(actions) - visited)
    if unreachable:
        _semantic_error(
            path,
            locations,
            ("actions",),
            f"unreachable actions {unreachable!r}",
        )


def _validate_resolution_policy(
    document: Mapping[str, object], *, path: Path, locations: SourceMap
) -> None:
    """Require policy strategies to act on their declared conflict."""
    conflicts = {str(item) for item in cast(list[object], document["conflicts"])}
    strategy = _mapping(document["strategy"])
    kind = strategy["kind"]
    if kind == "retain" and str(strategy["retain"]) not in conflicts:
        _semantic_error(
            path,
            locations,
            ("strategy", "retain"),
            "retained identifier is not a member of the declared conflict",
        )
    if kind == "substitute" and str(strategy["replace"]) not in conflicts:
        _semantic_error(
            path,
            locations,
            ("strategy", "replace"),
            "replaced identifier is not a member of the declared conflict",
        )
    if kind == "substitute" and strategy["replace"] == strategy["with"]:
        _semantic_error(
            path,
            locations,
            ("strategy", "with"),
            "substitute identifier must differ from the replaced identifier",
        )
    if kind == "combine" and str(strategy["result"]) in conflicts:
        _semantic_error(
            path,
            locations,
            ("strategy", "result"),
            "combine result must differ from both conflicting identifiers",
        )


def _semantic_error(
    path: Path,
    locations: SourceMap,
    parts: DocumentPath,
    message: str,
) -> NoReturn:
    """Raise one semantic error at the closest source position."""
    source = nearest_location(locations, parts)
    raise DeclarationSemanticError(
        path,
        format_document_path(parts),
        message,
        line=source.line if source else None,
        column=source.column if source else None,
    )
