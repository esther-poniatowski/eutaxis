"""Render resolved declaration records as cumulative Markdown fragments."""

from __future__ import annotations

import json
from collections.abc import Mapping

from .catalog import DeclarationCatalog
from .composition import (
    CumulativeArtifact,
    CumulativeCompositionPlan,
    assemble_cumulative_artifact,
)
from .exceptions import CompositionError
from .models import (
    Binding,
    Criterion,
    DeclarationKind,
    LiteralBinding,
    Norm,
    OperationDeclaration,
    ParameterBinding,
    Predicate,
    ProcedureDeclaration,
    RuleDeclaration,
    VersionedReference,
)
from .resolution import ResolvedCompilationUnit, ResolvedRuleProjection

_MODALITY = {
    "must": ("✓", "MUST"),
    "must-not": ("✗", "MUST NOT"),
    "should": ("✓", "SHOULD"),
    "should-not": ("✗", "SHOULD NOT"),
    "may": ("✓", "MAY"),
}


def _render_cumulative_markdown(
    catalog: DeclarationCatalog,
    unit: ResolvedCompilationUnit,
    plan: CumulativeCompositionPlan,
) -> CumulativeArtifact:
    """Render one authenticated catalog and resolved cumulative plan."""
    projections = {
        projection.declaration: projection for projection in unit.rule_projections
    }
    fragments: dict[str, str] = {}
    for component in plan.components:
        identifier = component.declaration
        record = catalog.get(identifier)
        if record is None:
            raise CompositionError(
                _component_location(identifier),
                f"catalog has no declaration {identifier!r}",
            )
        declaration = record.declaration
        if isinstance(declaration, RuleDeclaration):
            projection = projections.get(identifier)
            if projection is None:
                raise CompositionError(
                    _component_location(identifier),
                    f"resolved unit has no rule projection for {identifier!r}",
                )
            fragments[identifier] = _render_rule(declaration, projection)
        elif isinstance(declaration, ProcedureDeclaration):
            fragments[identifier] = _render_procedure(catalog, declaration)
        else:
            raise CompositionError(
                _component_location(identifier),
                f"declaration {identifier!r} is not renderable instruction content",
            )
    return assemble_cumulative_artifact(plan, fragments)


def _render_rule(
    rule: RuleDeclaration,
    projection: ResolvedRuleProjection,
) -> str:
    """Render the effective local projection of one rule."""
    norms = {norm.id: norm for norm in rule.norms}
    criteria = {criterion.id: criterion for criterion in rule.criteria}
    blocks = [f"**{rule.id}**:"]
    for identifier in projection.norms:
        norm = norms[identifier]
        blocks.append(_render_norm(norm))
        if norm.guidance is not None:
            blocks.append(f"*How to apply.* {norm.guidance}")
        if norm.rationale is not None:
            blocks.append(f"*Why.* {norm.rationale}")
        if norm.decision_criterion is not None:
            blocks.append(f"*Decision criterion.* {norm.decision_criterion}")
    if rule.rationale is not None:
        blocks.append(f"*Why.* {rule.rationale}")
    if projection.criteria:
        lines = ["*Success criteria.*"]
        lines.extend(
            _render_criterion(criteria[identifier])
            for identifier in projection.criteria
        )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _render_norm(norm: Norm) -> str:
    """Render one BCP 14 norm as one labelled instruction line."""
    marker, keyword = _MODALITY[norm.modality]
    subject = norm.subject[0].upper() + norm.subject[1:]
    statement = f"{subject} {keyword} {norm.action.verb} {norm.action.object}"
    if norm.action.timing is not None:
        statement += f" {norm.action.timing}"
    return f"{marker} `{norm.id}`: {statement}."


def _render_criterion(criterion: Criterion) -> str:
    """Render one effective criterion and its exact evaluator reference."""
    evaluator = f"{criterion.evaluator.id}@{criterion.evaluator.version}"
    return f"- `{criterion.id}` [{evaluator}]: {criterion.statement}"


def _render_procedure(
    catalog: DeclarationCatalog,
    procedure: ProcedureDeclaration,
) -> str:
    """Render one finite procedure and its exact operation contracts."""
    blocks = [f"**{procedure.id}** (procedure):", procedure.purpose]
    if procedure.rationale is not None:
        blocks.append(f"*Why.* {procedure.rationale}")
    blocks.extend(
        (
            "*Parameters.*\n\n" + _json_fence(procedure.parameters),
            f"*Entry.* `{procedure.entry}`",
        )
    )
    blocks.append(_render_predicates("Preconditions", procedure.preconditions))

    action_lines = ["*Actions.*"]
    operation_references: list[VersionedReference] = []
    seen_operations: set[tuple[str, int]] = set()
    for action in procedure.actions:
        action_lines.extend(
            (
                f"\n**`{action.id}`.**",
                f"- Operation: `{action.operation.id}@{action.operation.version}`",
            )
        )
        action_lines.append("- Bindings:")
        if action.bindings:
            action_lines.extend(
                f"  - `{name}`: {_render_binding(binding)}"
                for name, binding in sorted(action.bindings.items())
            )
        else:
            action_lines.append("  - None")
        action_lines.append(f"- On success: `{action.on_success}`")
        action_lines.append("- On failure:")
        if action.on_failure:
            action_lines.extend(
                f"  - `{outcome}` → `{target}`"
                for outcome, target in sorted(action.on_failure.items())
            )
        else:
            action_lines.append("  - None")
        operation_key = (action.operation.id, action.operation.version)
        if operation_key not in seen_operations:
            seen_operations.add(operation_key)
            operation_references.append(action.operation)
    blocks.append("\n".join(action_lines))

    if procedure.invariants:
        blocks.append(_render_predicates("Invariants", procedure.invariants))
    if procedure.effects:
        blocks.append(_render_values("Effects", procedure.effects))
    if procedure.postconditions:
        blocks.append(_render_predicates("Postconditions", procedure.postconditions))
    if procedure.failures:
        blocks.append(_render_values("Failure outcomes", procedure.failures))
    operation_blocks = ["*Operation contracts.*"]
    operation_blocks.extend(
        _render_operation(catalog, reference) for reference in operation_references
    )
    blocks.append("\n\n".join(operation_blocks))
    return "\n\n".join(blocks)


def _render_predicates(title: str, predicates: tuple[Predicate, ...]) -> str:
    """Render one ordered predicate group with canonical JSON expressions."""
    lines = [f"*{title}.*"]
    if not predicates:
        lines.append("- None")
    else:
        for predicate in predicates:
            evaluator = (
                "None"
                if predicate.evaluator is None
                else f"`{predicate.evaluator.id}@{predicate.evaluator.version}`"
            )
            observes = (
                "None"
                if not predicate.observes
                else ", ".join(f"`{value}`" for value in predicate.observes)
            )
            lines.extend(
                (
                    f"\n**`{predicate.id}` ({predicate.predicate_class}).**",
                    f"- Evaluator: {evaluator}",
                    f"- Observes: {observes}",
                    "- Expression:",
                    "",
                    _json_fence(predicate.expression),
                )
            )
    return "\n".join(lines)


def _render_values(title: str, values: tuple[str, ...]) -> str:
    """Render one ordered string-value group."""
    return "\n".join((f"*{title}.*", *(f"- `{value}`" for value in values)))


def _render_binding(binding: Binding) -> str:
    """Render one typed operation binding."""
    if isinstance(binding, ParameterBinding):
        return f"parameter `{binding.parameter}`"
    if isinstance(binding, LiteralBinding):
        return f"literal {_code_span(_canonical_json(binding.value))}"
    raise AssertionError("declaration loader admitted an unknown binding")


def _canonical_json(value: object) -> str:
    """Return compact deterministic JSON for an immutable JSON value."""
    return json.dumps(
        _thaw_json(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_fence(value: object) -> str:
    """Fence canonical JSON with a delimiter absent from its payload."""
    payload = _canonical_json(value)
    fence = "`" * max(3, _longest_backtick_run(payload) + 1)
    return f"{fence}json\n{payload}\n{fence}"


def _code_span(value: str) -> str:
    """Wrap one single-line value in a collision-free Markdown code span."""
    delimiter = "`" * max(1, _longest_backtick_run(value) + 1)
    return f"{delimiter}{value}{delimiter}"


def _longest_backtick_run(value: str) -> int:
    """Return the longest consecutive backtick run in ``value``."""
    longest = current = 0
    for character in value:
        if character == "`":
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _render_operation(
    catalog: DeclarationCatalog,
    reference: VersionedReference,
) -> str:
    """Render the complete exact contract for one referenced operation."""
    record = catalog.get_contract(
        DeclarationKind.OPERATION,
        reference.id,
        reference.version,
    )
    if record is None or not isinstance(record.declaration, OperationDeclaration):
        raise CompositionError(
            "$.operation-contracts",
            f"catalog has no operation {reference.id!r}@{reference.version}",
        )
    operation = record.declaration
    blocks = [f"**`{operation.id}@{operation.version}`.**"]
    if operation.rationale is not None:
        blocks.append(f"*Why.* {operation.rationale}")
    blocks.extend(
        (
            "*Inputs.*\n\n" + _json_fence(operation.inputs),
            "*Outputs.*\n\n" + _json_fence(operation.outputs),
            _render_predicates("Preconditions", operation.preconditions),
        )
    )
    if operation.method is not None:
        blocks.append("*Method.*\n\n" + operation.method)
    blocks.extend(
        (
            _render_values("Effects", operation.effects),
            _render_values("Failure outcomes", operation.failure_outcomes),
            f"*Recovery.* {operation.recovery}",
        )
    )
    return "\n\n".join(blocks)


def _thaw_json(value: object) -> object:
    """Convert immutable declaration JSON containers for serialization."""
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _component_location(identifier: str) -> str:
    """Return one stable diagnostic path for a planned component."""
    return f"$.components[{json.dumps(identifier, ensure_ascii=False)}]"
