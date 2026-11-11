"""Cross-record contract tests for the structured declaration registry."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
import yaml

from eutaxis.declarations import (
    DeclarationKind,
    DeclarationRegistryError,
    load_declaration_registry,
    load_facet_registry,
)

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY_FIXTURES = FIXTURES / "registry" / "valid"
RESOLUTION_FIXTURES = FIXTURES / "resolution" / "valid"
FACET_FIXTURE = FIXTURES / "facets" / "valid" / "context-facets.yaml"


@pytest.fixture(scope="module")
def facets():
    """Load the shared facet vocabulary for registry sources."""
    return load_facet_registry(FACET_FIXTURE)


def _paths(directory: Path) -> tuple[Path, ...]:
    """Return registry YAML paths in deliberately reversed order."""
    return tuple(reversed(sorted(directory.glob("*.yaml"))))


def _copy_corpus(tmp_path: Path) -> Path:
    """Copy the coherent corpus so one test may mutate it independently."""
    target = tmp_path / "registry"
    shutil.copytree(REGISTRY_FIXTURES, target)
    return target


def _mutate(
    directory: Path,
    filename: str,
    change: Callable[[dict[str, object]], None],
) -> None:
    """Apply one source mutation without reordering fields."""
    path = directory / filename
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(document)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


def _add_decision(directory: Path, *, status: str = "active") -> None:
    """Add one governance decision that rules may cite."""
    document = {
        "_schema": "eutaxis:declaration@1",
        "id": "registry/format-decision",
        "kind": "decision",
        "owner": "registry",
        "status": status,
        "source-revision": "fixture-1",
        "applicability": {"facet": "context.available", "operator": "exists"},
        "relations": [],
        "context": "The registry needs one canonical declaration format.",
        "drivers": [
            {
                "id": "structure",
                "statement": "The format exposes fields to validation.",
            }
        ],
        "options": [
            {
                "id": "yaml",
                "description": "Use structured YAML records.",
                "assessments": [
                    {
                        "driver": "structure",
                        "judgment": "YAML fields are directly schema-addressable.",
                    }
                ],
            },
            {
                "id": "markdown",
                "description": "Use labelled Markdown records.",
                "assessments": [
                    {
                        "driver": "structure",
                        "judgment": "Markdown labels require parsing first.",
                    }
                ],
            },
        ],
        "outcome": "yaml",
        "consequences": "Rule sources use YAML as their canonical form.",
    }
    (directory / "decision.yaml").write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )


def _assert_registry_error(
    directory: Path,
    facets,
    *,
    location: str,
    filename: str | None = None,
) -> DeclarationRegistryError:
    """Load one invalid corpus and assert its located registry boundary."""
    with pytest.raises(DeclarationRegistryError) as captured:
        load_declaration_registry(_paths(directory), facets)
    assert captured.value.location == location
    assert captured.value.line is not None
    if filename is not None:
        assert captured.value.path.name == filename
    return captured.value


def test_closed_registry_indexes_nested_content_and_exact_families(facets) -> None:
    registry = load_declaration_registry(
        (*_paths(REGISTRY_FIXTURES), REGISTRY_FIXTURES / "rule-set.yaml"), facets
    )

    assert registry.paths == tuple(sorted(set(registry.paths), key=str))
    assert set(registry.records) == {
        "content/alternate",
        "content/base",
        "content/combined",
        "content/package",
        "content/refined",
        "content/write",
        "registry/manifest",
        "registry/prefer-refined",
    }
    nested = registry.records["content/base"]
    assert nested.root == ("rules", 0)
    assert nested.containing_rule_set == "content/package"
    assert "all" in nested.declaration.applicability
    assert registry.families["registry/manual"].kind is DeclarationKind.EVALUATOR
    assert registry.families["registry/write"].kind is DeclarationKind.OPERATION
    assert set(registry.families["registry/manual"].versions) == {1}
    assert registry.conflicts == {("content/alternate", "content/refined")}
    with pytest.raises(TypeError):
        registry.records["new"] = nested  # type: ignore[index]
    with pytest.raises(TypeError):
        registry.families["registry/manual"].versions[2] = nested  # type: ignore[index]


def test_future_resolution_corpus_satisfies_static_registry_contracts(
    facets,
) -> None:
    registry = load_declaration_registry(_paths(RESOLUTION_FIXTURES), facets)

    assert registry.records["resolution/base"].containing_rule_set == (
        "resolution/package"
    )
    assert registry.conflicts == {("resolution/alternate", "resolution/refined")}


def test_legacy_loader_indexes_each_source_before_loading_the_next(
    tmp_path: Path,
    facets,
) -> None:
    source = (REGISTRY_FIXTURES / "evaluator.yaml").read_bytes()
    first = tmp_path / "a-first.yaml"
    duplicate = tmp_path / "b-duplicate.yaml"
    malformed = tmp_path / "z-malformed.yaml"
    first.write_bytes(source)
    duplicate.write_bytes(source)
    malformed.write_bytes(b"not: [valid")

    with pytest.raises(
        DeclarationRegistryError,
        match="duplicate contract version",
    ) as raised:
        load_declaration_registry((malformed, duplicate, first), facets)

    assert raised.value.path == duplicate.resolve()
    assert raised.value.location == "$.version"


def test_non_content_relations_fail_at_the_first_relation_item(
    tmp_path: Path, facets
) -> None:
    directory = _copy_corpus(tmp_path)
    _mutate(
        directory,
        "operation.yaml",
        lambda document: document.update(
            {"relations": [{"type": "requires", "target": "content/base"}]}
        ),
    )
    _assert_registry_error(
        directory, facets, location="$.relations[0]", filename="operation.yaml"
    )


def test_repeated_relation_fails_at_the_later_target(tmp_path: Path, facets) -> None:
    directory = _copy_corpus(tmp_path)

    def repeat(document: dict[str, object]) -> None:
        cast(list[object], document["relations"]).append(
            {"type": "requires", "target": "content/base"}
        )

    _mutate(directory, "refined-rule.yaml", repeat)
    _assert_registry_error(
        directory,
        facets,
        location="$.relations[2].target",
        filename="refined-rule.yaml",
    )


def test_relation_target_must_be_effective_content(tmp_path: Path, facets) -> None:
    directory = _copy_corpus(tmp_path)

    def target_container(document: dict[str, object]) -> None:
        document["relations"] = [{"type": "requires", "target": "content/package"}]

    _mutate(directory, "alternate-rule.yaml", target_container)
    _assert_registry_error(
        directory,
        facets,
        location="$.relations[0].target",
        filename="alternate-rule.yaml",
    )


@pytest.mark.parametrize(
    ("filename", "status", "relations"),
    [
        (
            "refined-rule.yaml",
            "proposed",
            [{"type": "requires", "target": "content/base"}],
        ),
        (
            "alternate-rule.yaml",
            "retired",
            [{"type": "incompatible-with", "target": "content/base"}],
        ),
    ],
)
def test_inactive_content_cannot_assert_operative_relations(
    tmp_path: Path,
    facets,
    filename: str,
    status: str,
    relations: list[dict[str, str]],
) -> None:
    directory = _copy_corpus(tmp_path)
    _mutate(
        directory,
        filename,
        lambda document: document.update({"status": status, "relations": relations}),
    )

    error = _assert_registry_error(
        directory, facets, location="$.status", filename=filename
    )
    assert "operative relations must be active" in str(error)


def test_reciprocal_conflict_fails_at_the_later_canonical_source(
    tmp_path: Path, facets
) -> None:
    directory = _copy_corpus(tmp_path)
    _mutate(
        directory,
        "alternate-rule.yaml",
        lambda document: document.update(
            {"relations": [{"type": "incompatible-with", "target": "content/refined"}]}
        ),
    )
    _assert_registry_error(
        directory,
        facets,
        location="$.relations[1].target",
        filename="refined-rule.yaml",
    )


def test_dependency_cycle_fails_at_the_deterministic_closing_edge(
    tmp_path: Path, facets
) -> None:
    directory = _copy_corpus(tmp_path)

    def connect_alternate(document: dict[str, object]) -> None:
        document["relations"] = [{"type": "requires", "target": "content/refined"}]

    def connect_base(document: dict[str, object]) -> None:
        document["rules"][0]["relations"] = [  # type: ignore[index]
            {"type": "requires", "target": "content/alternate"}
        ]

    _mutate(directory, "alternate-rule.yaml", connect_alternate)
    _mutate(directory, "rule-set.yaml", connect_base)
    _assert_registry_error(
        directory,
        facets,
        location="$.rules[0].relations[0].target",
        filename="rule-set.yaml",
    )


@pytest.mark.parametrize(
    ("identifier", "version", "location"),
    [
        ("registry/missing", 1, "$.criteria[0].evaluator.id"),
        ("registry/manual", 2, "$.criteria[0].evaluator.version"),
        ("registry/write", 1, "$.criteria[0].evaluator.id"),
    ],
)
def test_exact_reference_failures_distinguish_family_version_and_kind(
    tmp_path: Path,
    facets,
    identifier: str,
    version: int,
    location: str,
) -> None:
    directory = _copy_corpus(tmp_path)

    def change_reference(document: dict[str, object]) -> None:
        document["criteria"][0]["evaluator"] = {  # type: ignore[index]
            "id": identifier,
            "version": version,
        }

    _mutate(directory, "refined-rule.yaml", change_reference)
    _assert_registry_error(
        directory, facets, location=location, filename="refined-rule.yaml"
    )


def test_rule_decision_provenance_resolves_an_active_decision(
    tmp_path: Path, facets
) -> None:
    directory = _copy_corpus(tmp_path)
    _add_decision(directory)
    _mutate(
        directory,
        "refined-rule.yaml",
        lambda document: document.update({"decided-by": ["registry/format-decision"]}),
    )

    registry = load_declaration_registry(_paths(directory), facets)

    rule = registry.records["content/refined"].declaration
    assert rule.decided_by == ("registry/format-decision",)  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        ("registry/missing", "unknown decision declaration"),
        ("content/base", "does not name decision declaration"),
    ],
)
def test_rule_decision_provenance_requires_a_resolved_decision(
    tmp_path: Path, facets, decision: str, expected: str
) -> None:
    directory = _copy_corpus(tmp_path)
    _mutate(
        directory,
        "refined-rule.yaml",
        lambda document: document.update({"decided-by": [decision]}),
    )

    error = _assert_registry_error(
        directory,
        facets,
        location="$.decided-by[0]",
        filename="refined-rule.yaml",
    )
    assert expected in str(error)


def test_rule_decision_provenance_requires_an_active_decision(
    tmp_path: Path, facets
) -> None:
    directory = _copy_corpus(tmp_path)
    _add_decision(directory, status="proposed")
    _mutate(
        directory,
        "refined-rule.yaml",
        lambda document: document.update({"decided-by": ["registry/format-decision"]}),
    )

    error = _assert_registry_error(
        directory,
        facets,
        location="$.decided-by[0]",
        filename="refined-rule.yaml",
    )
    assert "is not active" in str(error)


def test_exact_reference_requires_an_active_contract(tmp_path: Path, facets) -> None:
    directory = _copy_corpus(tmp_path)
    _mutate(
        directory,
        "evaluator.yaml",
        lambda document: document.update({"status": "proposed"}),
    )

    error = _assert_registry_error(
        directory,
        facets,
        location="$.criteria[0].evaluator",
        filename="alternate-rule.yaml",
    )
    assert "is not active" in str(error)


def test_superseded_declaration_requires_an_incoming_supersedes_relation(
    tmp_path: Path, facets
) -> None:
    directory = _copy_corpus(tmp_path)
    orphan = yaml.safe_load(
        (directory / "alternate-rule.yaml").read_text(encoding="utf-8")
    )
    orphan["id"] = "content/orphaned-alternate"
    orphan["status"] = "superseded"
    (directory / "orphaned-rule.yaml").write_text(
        yaml.safe_dump(orphan, sort_keys=False), encoding="utf-8"
    )

    error = _assert_registry_error(
        directory,
        facets,
        location="$.status",
        filename="orphaned-rule.yaml",
    )
    assert "lacks an incoming supersedes relation" in str(error)


def test_active_same_kind_declaration_may_supersede_a_superseded_record(
    tmp_path: Path, facets
) -> None:
    directory = _copy_corpus(tmp_path)
    legacy = yaml.safe_load(
        (directory / "alternate-rule.yaml").read_text(encoding="utf-8")
    )
    legacy["id"] = "content/legacy-alternate"
    legacy["status"] = "superseded"
    (directory / "legacy-rule.yaml").write_text(
        yaml.safe_dump(legacy, sort_keys=False), encoding="utf-8"
    )
    _mutate(
        directory,
        "alternate-rule.yaml",
        lambda document: document.update(
            {
                "relations": [
                    {"type": "supersedes", "target": "content/legacy-alternate"}
                ]
            }
        ),
    )

    registry = load_declaration_registry(_paths(directory), facets)

    assert "content/legacy-alternate" in registry.records


@pytest.mark.parametrize(
    ("field", "value", "location"),
    [
        ("owner", "other", "$.owner"),
        ("kind", "operation", "$.kind"),
    ],
)
def test_contract_family_cannot_change_owner_or_kind(
    tmp_path: Path, facets, field: str, value: str, location: str
) -> None:
    directory = _copy_corpus(tmp_path)
    duplicate = yaml.safe_load(
        (directory / "evaluator.yaml").read_text(encoding="utf-8")
    )
    duplicate["version"] = 2
    duplicate[field] = value
    if field == "kind":
        operation = yaml.safe_load(
            (directory / "operation.yaml").read_text(encoding="utf-8")
        )
        operation["id"] = duplicate["id"]
        operation["version"] = 2
        duplicate = operation
    (directory / "z-family.yaml").write_text(
        yaml.safe_dump(duplicate, sort_keys=False), encoding="utf-8"
    )
    _assert_registry_error(
        directory, facets, location=location, filename="z-family.yaml"
    )


def test_duplicate_exact_version_fails_at_the_later_version(
    tmp_path: Path, facets
) -> None:
    directory = _copy_corpus(tmp_path)
    shutil.copy2(directory / "evaluator.yaml", directory / "z-evaluator.yaml")
    _assert_registry_error(
        directory, facets, location="$.version", filename="z-evaluator.yaml"
    )


def test_policy_requires_one_declared_incompatibility(tmp_path: Path, facets) -> None:
    directory = _copy_corpus(tmp_path)

    def change_pair(document: dict[str, object]) -> None:
        document["conflicts"] = ["content/base", "content/alternate"]
        document["strategy"] = {"kind": "retain", "retain": "content/base"}

    _mutate(directory, "policy.yaml", change_pair)
    _assert_registry_error(
        directory, facets, location="$.conflicts", filename="policy.yaml"
    )


def test_policy_conflicts_must_name_effective_content(tmp_path: Path, facets) -> None:
    directory = _copy_corpus(tmp_path)

    def target_container(document: dict[str, object]) -> None:
        document["conflicts"] = ["content/package", "content/alternate"]
        document["strategy"] = {"kind": "retain", "retain": "content/package"}

    _mutate(directory, "policy.yaml", target_container)
    _assert_registry_error(
        directory, facets, location="$.conflicts[0]", filename="policy.yaml"
    )


def test_substitution_must_preserve_the_replaced_kind(tmp_path: Path, facets) -> None:
    directory = _copy_corpus(tmp_path)
    _mutate(
        directory,
        "policy.yaml",
        lambda document: document.update(
            {
                "strategy": {
                    "kind": "substitute",
                    "replace": "content/refined",
                    "with": "content/write",
                }
            }
        ),
    )
    _assert_registry_error(
        directory, facets, location="$.strategy.with", filename="policy.yaml"
    )


@pytest.mark.parametrize(
    ("strategy", "location"),
    [
        (
            {
                "kind": "substitute",
                "replace": "content/refined",
                "with": "content/package",
            },
            "$.strategy.with",
        ),
        (
            {"kind": "combine", "result": "content/package"},
            "$.strategy.result",
        ),
    ],
)
def test_policy_outcomes_must_name_effective_content(
    tmp_path: Path, facets, strategy: dict[str, object], location: str
) -> None:
    directory = _copy_corpus(tmp_path)
    _mutate(
        directory,
        "policy.yaml",
        lambda document: document.update({"strategy": strategy}),
    )
    _assert_registry_error(directory, facets, location=location, filename="policy.yaml")


def test_cross_kind_combine_fails_at_the_strategy_kind(tmp_path: Path, facets) -> None:
    directory = _copy_corpus(tmp_path)

    def conflict_with_procedure(document: dict[str, object]) -> None:
        document["relations"] = [
            {"type": "requires", "target": "content/base"},
            {"type": "incompatible-with", "target": "content/write"},
        ]

    def combine(document: dict[str, object]) -> None:
        document["conflicts"] = ["content/refined", "content/write"]
        document["strategy"] = {"kind": "combine", "result": "content/combined"}

    _mutate(directory, "refined-rule.yaml", conflict_with_procedure)
    _mutate(directory, "policy.yaml", combine)
    _assert_registry_error(
        directory, facets, location="$.strategy.kind", filename="policy.yaml"
    )


def test_manifest_rejects_non_content_section_members(tmp_path: Path, facets) -> None:
    directory = _copy_corpus(tmp_path)

    def select_policy(document: dict[str, object]) -> None:
        document["sections"][0]["declarations"][0] = (  # type: ignore[index]
            "registry/prefer-refined"
        )

    _mutate(directory, "manifest.yaml", select_policy)
    _assert_registry_error(
        directory,
        facets,
        location="$.sections[0].declarations[0]",
        filename="manifest.yaml",
    )


def test_manifest_rejects_duplicate_direct_selections(tmp_path: Path, facets) -> None:
    directory = _copy_corpus(tmp_path)

    def repeat_selection(document: dict[str, object]) -> None:
        cast(list[object], document["sections"]).append(
            {"id": "later", "declarations": ["content/refined"]}
        )

    _mutate(directory, "manifest.yaml", repeat_selection)
    _assert_registry_error(
        directory,
        facets,
        location="$.sections[1].declarations[0]",
        filename="manifest.yaml",
    )


def test_manifest_may_select_container_and_embedded_member(
    tmp_path: Path, facets
) -> None:
    directory = _copy_corpus(tmp_path)

    def select_member(document: dict[str, object]) -> None:
        document["sections"][0]["declarations"].append(  # type: ignore[index]
            "content/base"
        )

    _mutate(directory, "manifest.yaml", select_member)

    registry = load_declaration_registry(_paths(directory), facets)

    assert registry.records["content/base"].containing_rule_set == "content/package"


def test_manifest_policy_must_share_the_manifest_owner(tmp_path: Path, facets) -> None:
    directory = _copy_corpus(tmp_path)
    _mutate(
        directory,
        "policy.yaml",
        lambda document: document.update({"owner": "other"}),
    )
    _assert_registry_error(
        directory, facets, location="$.policies[0]", filename="manifest.yaml"
    )


def test_policy_order_ties_are_scoped_to_each_manifest(tmp_path: Path, facets) -> None:
    directory = _copy_corpus(tmp_path)
    second_policy = yaml.safe_load(
        (directory / "policy.yaml").read_text(encoding="utf-8")
    )
    second_policy["id"] = "registry/second-policy"
    (directory / "second-policy.yaml").write_text(
        yaml.safe_dump(second_policy, sort_keys=False), encoding="utf-8"
    )

    def add_policy(document: dict[str, object]) -> None:
        cast(list[object], document["policies"]).append("registry/second-policy")

    _mutate(directory, "manifest.yaml", add_policy)
    _assert_registry_error(
        directory, facets, location="$.policies[1]", filename="manifest.yaml"
    )

    second_manifest = yaml.safe_load(
        (directory / "manifest.yaml").read_text(encoding="utf-8")
    )
    second_manifest["id"] = "registry/second-manifest"
    second_manifest["policies"] = ["registry/second-policy"]
    (directory / "second-manifest.yaml").write_text(
        yaml.safe_dump(second_manifest, sort_keys=False), encoding="utf-8"
    )
    _mutate(
        directory,
        "manifest.yaml",
        lambda document: document.update({"policies": ["registry/prefer-refined"]}),
    )
    load_declaration_registry(_paths(directory), facets)


@pytest.mark.parametrize(
    ("remove_with", "location"),
    [
        (False, "$.actions[0].with"),
        (True, "$.actions[0]"),
    ],
)
def test_missing_operation_inputs_belong_to_the_available_action_container(
    tmp_path: Path, facets, remove_with: bool, location: str
) -> None:
    directory = _copy_corpus(tmp_path)

    def remove_binding(document: dict[str, object]) -> None:
        action = document["actions"][0]  # type: ignore[index]
        if remove_with:
            action.pop("with")
        else:
            action["with"].pop("content")

    _mutate(directory, "procedure.yaml", remove_binding)
    _assert_registry_error(
        directory, facets, location=location, filename="procedure.yaml"
    )


def test_unknown_operation_input_belongs_to_its_binding_key(
    tmp_path: Path, facets
) -> None:
    directory = _copy_corpus(tmp_path)

    def add_binding(document: dict[str, object]) -> None:
        document["actions"][0]["with"]["extra"] = {"literal": True}  # type: ignore[index]

    _mutate(directory, "procedure.yaml", add_binding)
    _assert_registry_error(
        directory,
        facets,
        location="$.actions[0].with.extra",
        filename="procedure.yaml",
    )


def test_invalid_literal_belongs_to_its_deepest_instance_path(
    tmp_path: Path, facets
) -> None:
    directory = _copy_corpus(tmp_path)

    def require_count(document: dict[str, object]) -> None:
        document["inputs"]["properties"]["content"] = {  # type: ignore[index]
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
            "additionalProperties": False,
        }

    def bind_invalid_count(document: dict[str, object]) -> None:
        document["actions"][0]["with"]["content"] = {  # type: ignore[index]
            "literal": {"count": "seven"}
        }

    _mutate(directory, "operation.yaml", require_count)
    _mutate(directory, "procedure.yaml", bind_invalid_count)
    _assert_registry_error(
        directory,
        facets,
        location="$.actions[0].with.content.literal.count",
        filename="procedure.yaml",
    )


def test_parameter_binding_requires_exact_input_schema(tmp_path: Path, facets) -> None:
    directory = _copy_corpus(tmp_path)

    def change_parameter_schema(document: dict[str, object]) -> None:
        document["parameters"]["properties"]["path"] = {  # type: ignore[index]
            "type": "integer"
        }

    _mutate(directory, "procedure.yaml", change_parameter_schema)
    _assert_registry_error(
        directory,
        facets,
        location="$.actions[0].with.path.parameter",
        filename="procedure.yaml",
    )


def test_parameter_schema_comparison_resolves_each_local_reference_root(
    tmp_path: Path, facets
) -> None:
    directory = _copy_corpus(tmp_path)

    def reference_integer(document: dict[str, object]) -> None:
        properties = document["parameters"]["properties"]  # type: ignore[index]
        properties["path"] = {"$ref": "#/properties/shared"}
        properties["shared"] = {"type": "integer"}

    def reference_string(document: dict[str, object]) -> None:
        properties = document["inputs"]["properties"]  # type: ignore[index]
        properties["path"] = {"$ref": "#/properties/shared"}
        properties["shared"] = {"type": "string"}

    _mutate(directory, "procedure.yaml", reference_integer)
    _mutate(directory, "operation.yaml", reference_string)
    _assert_registry_error(
        directory,
        facets,
        location="$.actions[0].with.path.parameter",
        filename="procedure.yaml",
    )


def test_equal_local_reference_closures_are_valid_parameter_schemas(
    tmp_path: Path, facets
) -> None:
    directory = _copy_corpus(tmp_path)

    def reference_integer(document: dict[str, object], field: str) -> None:
        properties = document[field]["properties"]  # type: ignore[index]
        properties["path"] = {"$ref": "#/properties/shared"}
        properties["shared"] = {"type": "integer"}

    _mutate(
        directory,
        "procedure.yaml",
        lambda document: reference_integer(document, "parameters"),
    )
    _mutate(
        directory,
        "operation.yaml",
        lambda document: reference_integer(document, "inputs"),
    )

    load_declaration_registry(_paths(directory), facets)


def test_missing_operation_failure_outcome_belongs_to_the_mapping(
    tmp_path: Path, facets
) -> None:
    directory = _copy_corpus(tmp_path)

    def add_outcome(document: dict[str, object]) -> None:
        cast(list[object], document["failure-outcomes"]).append("timeout")

    _mutate(directory, "operation.yaml", add_outcome)
    _assert_registry_error(
        directory,
        facets,
        location="$.actions[0].on-failure",
        filename="procedure.yaml",
    )


def test_additional_operation_failure_outcome_belongs_to_its_key(
    tmp_path: Path, facets
) -> None:
    directory = _copy_corpus(tmp_path)

    def add_outcome_mapping(document: dict[str, object]) -> None:
        document["actions"][0]["on-failure"]["other"] = "write-failed"  # type: ignore[index]

    _mutate(directory, "procedure.yaml", add_outcome_mapping)
    _assert_registry_error(
        directory,
        facets,
        location="$.actions[0].on-failure.other",
        filename="procedure.yaml",
    )


def test_operation_effects_must_fit_the_procedure_footprint(
    tmp_path: Path, facets
) -> None:
    directory = _copy_corpus(tmp_path)

    def add_effect(document: dict[str, object]) -> None:
        cast(list[object], document["effects"]).append("network/remote")

    _mutate(directory, "operation.yaml", add_effect)
    _assert_registry_error(
        directory,
        facets,
        location="$.actions[0].operation",
        filename="procedure.yaml",
    )


@pytest.mark.parametrize(
    ("observes", "location"),
    [
        (["filesystem/artifact"], "$.invariants[0].observes[0]"),
        (["state/safe", "filesystem/artifact"], "$.invariants[0].observes[1]"),
    ],
)
def test_operation_effect_on_each_invariant_observation_is_located(
    tmp_path: Path, facets, observes: list[str], location: str
) -> None:
    directory = _copy_corpus(tmp_path)

    def add_invariant(document: dict[str, object]) -> None:
        document["invariants"] = [
            {
                "id": "artifact-stable",
                "class": "invariant",
                "expression": {
                    "facet": "filesystem.writable",
                    "operator": "equals",
                    "value": True,
                },
                "observes": observes,
            }
        ]

    _mutate(directory, "procedure.yaml", add_invariant)
    _assert_registry_error(
        directory, facets, location=location, filename="procedure.yaml"
    )
