"""Render resolved declaration records as cumulative Markdown fragments."""

from __future__ import annotations

import json
from collections.abc import Mapping

from ..names import SAFE_SLUG_PATTERN
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
    CumulativeMarkdownProfile,
    DeclarationKind,
    LiteralBinding,
    Norm,
    OperationDeclaration,
    ParameterBinding,
    Predicate,
    ProcedureDeclaration,
    RuleDeclaration,
    RuleSetDeclaration,
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
    profile: CumulativeMarkdownProfile,
) -> CumulativeArtifact:
    """Render one authenticated catalog and resolved cumulative plan."""
    if type(profile) is not CumulativeMarkdownProfile:
        raise CompositionError(
            "$.profile",
            "cumulative Markdown profile must be a CumulativeMarkdownProfile",
        )
    projections = {
        projection.declaration: projection for projection in unit.rule_projections
    }
    fragments: dict[str, str] = {}
    projected_labels: dict[str, str] = {}
    rendered_rule_sets: set[str] = set()
    for component in plan.components:
        identifier = component.declaration
        record = catalog.get(identifier)
        if record is None:
            raise CompositionError(
                _component_location(identifier),
                f"catalog has no declaration {identifier!r}",
            )
        declaration = record.declaration
        label = _projection_label(identifier, profile)
        _claim_projected_label(projected_labels, label, identifier)
        if isinstance(declaration, RuleDeclaration):
            projection = projections.get(identifier)
            if projection is None:
                raise CompositionError(
                    _component_location(identifier),
                    f"resolved unit has no rule projection for {identifier!r}",
                )
            blocks: list[str] = []
            rule_set = record.containing_rule_set
            if (
                profile is CumulativeMarkdownProfile.AGENT_INSTRUCTIONS
                and rule_set is not None
                and rule_set not in rendered_rule_sets
            ):
                blocks.append(_render_rule_set(catalog, rule_set))
                rendered_rule_sets.add(rule_set)
            blocks.append(
                _render_rule(
                    declaration,
                    projection,
                    profile=profile,
                    label=label,
                )
            )
            fragments[identifier] = "\n\n".join(blocks)
        elif isinstance(declaration, ProcedureDeclaration):
            fragments[identifier] = _render_procedure(
                catalog,
                declaration,
                label=label,
            )
        else:
            raise CompositionError(
                _component_location(identifier),
                f"declaration {identifier!r} is not renderable instruction content",
            )
    return assemble_cumulative_artifact(plan, fragments)


def _render_rule(
    rule: RuleDeclaration,
    projection: ResolvedRuleProjection,
    *,
    profile: CumulativeMarkdownProfile,
    label: str,
) -> str:
    """Render the effective local projection of one rule."""
    norms = {norm.id: norm for norm in rule.norms}
    criteria = {criterion.id: criterion for criterion in rule.criteria}
    blocks = [f"**{label}**:"]
    for identifier in projection.norms:
        norm = norms[identifier]
        blocks.append(_render_norm(norm, profile))
        if norm.guidance is not None:
            blocks.append(f"*How to apply.* {norm.guidance}")
        if norm.rationale is not None:
            blocks.append(f"*Why.* {norm.rationale}")
        if norm.decision_criterion is not None:
            blocks.append(f"*Decision criterion.* {norm.decision_criterion}")
    if rule.rationale is not None:
        blocks.append(f"*Why.* {rule.rationale}")
    if profile is CumulativeMarkdownProfile.AUDITABLE and projection.criteria:
        lines = ["*Success criteria.*"]
        lines.extend(
            _render_criterion(criteria[identifier])
            for identifier in projection.criteria
        )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _render_rule_set(
    catalog: DeclarationCatalog,
    identifier: str,
) -> str:
    """Render one selected rule-set frame before its first effective rule."""
    record = catalog.get(identifier)
    if record is None or not isinstance(record.declaration, RuleSetDeclaration):
        raise CompositionError(
            _component_location(identifier),
            f"catalog has no containing rule set {identifier!r}",
        )
    rule_set = record.declaration
    label = _projection_label(
        rule_set.id,
        CumulativeMarkdownProfile.AGENT_INSTRUCTIONS,
    )
    heading = f"# {label.replace('-', ' ').capitalize()}"
    blocks = [heading, rule_set.purpose]
    if rule_set.rationale is not None:
        blocks.append(f"*Why.* {rule_set.rationale}")
    return "\n\n".join(blocks)


def _render_norm(norm: Norm, profile: CumulativeMarkdownProfile) -> str:
    """Render one BCP 14 norm as one labelled instruction line."""
    marker, keyword = _MODALITY[norm.modality]
    subject = norm.subject[0].upper() + norm.subject[1:]
    statement = f"{subject} {keyword} {norm.action.verb} {norm.action.object}"
    if norm.action.timing is not None:
        statement += f" {norm.action.timing}"
    if profile is CumulativeMarkdownProfile.AGENT_INSTRUCTIONS:
        return f"{marker} {statement}."
    return f"{marker} `{norm.id}`: {statement}."


def _projection_label(
    identifier: str,
    profile: CumulativeMarkdownProfile,
) -> str:
    """Return one profile-specific label without changing canonical identity."""
    if profile is CumulativeMarkdownProfile.AUDITABLE:
        return identifier
    label = identifier.rsplit("/", 1)[-1]
    if SAFE_SLUG_PATTERN.fullmatch(label) is None:
        raise CompositionError(
            "$.profile",
            f"declaration {identifier!r} has no valid agent label",
        )
    return label


def _claim_projected_label(
    labels: dict[str, str],
    label: str,
    identifier: str,
) -> None:
    """Claim one consumer label and reject cross-namespace collisions."""
    previous = labels.get(label)
    if previous is not None:
        raise CompositionError(
            "$.profile",
            f"projected label {label!r} is shared by {previous!r} and "
            f"{identifier!r}",
        )
    labels[label] = identifier


def _render_criterion(criterion: Criterion) -> str:
    """Render one effective criterion and its exact evaluator reference."""
    evaluator = f"{criterion.evaluator.id}@{criterion.evaluator.version}"
    return f"- `{criterion.id}` [{evaluator}]: {criterion.statement}"


def _render_procedure(
    catalog: DeclarationCatalog,
    procedure: ProcedureDeclaration,
    *,
    label: str | None = None,
    allow_support_resources: bool = False,
) -> str:
    """Render one finite procedure and its exact operation contracts."""
    blocks = [
        f"**{label or procedure.id}**:",
        "*Kind.* Procedure.",
        procedure.purpose,
    ]
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
        _render_operation(
            catalog,
            reference,
            allow_support_resources=allow_support_resources,
        )
        for reference in operation_references
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
    *,
    allow_support_resources: bool = False,
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
    if operation.support_resources and not allow_support_resources:
        raise CompositionError(
            "$.operation-contracts",
            (
                f"operation {reference.id!r}@{reference.version} requires "
                "support resources that cumulative Markdown cannot carry"
            ),
        )
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
    if operation.support_resources:
        blocks.append(
            "\n".join(
                (
                    "*Support resources.*",
                    *(
                        f"- `{support.resource}` → `{support.destination}`"
                        for support in operation.support_resources
                    ),
                )
            )
        )
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
