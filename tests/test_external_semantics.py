"""Exercise external namespace authority and declaration-reference syntax."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
import yaml

import eutaxis.declarations as declarations_api
from eutaxis.declarations._external_semantics import (
    _validate_external_declaration_semantics,
)
from eutaxis.declarations.exceptions import AcquisitionContractError
from eutaxis.declarations.loader import (
    LoadedDeclarationSource,
    load_declaration_source_bytes,
)

FIXTURES = Path(__file__).parent / "fixtures" / "declarations" / "valid"
LOCATION = "$.sources[2].files[3]"
NAMESPACE = "source"


def _mapping(value: object) -> dict[str, object]:
    return cast(dict[str, object], value)


def _sequence(value: object) -> list[object]:
    return cast(list[object], value)


def _document(filename: str) -> dict[str, object]:
    document = cast(
        dict[str, object],
        yaml.safe_load((FIXTURES / filename).read_text(encoding="utf-8")),
    )
    local_name = str(document["id"]).split("/", 1)[-1]
    document["id"] = f"{NAMESPACE}/{local_name}"
    document["owner"] = NAMESPACE
    if document["kind"] == "rule-set":
        for index, value in enumerate(_sequence(document["rules"])):
            rule = _mapping(value)
            rule["id"] = f"{NAMESPACE}/embedded-{index}"
            rule["owner"] = NAMESPACE
    return document


def _loaded(document: dict[str, object]) -> LoadedDeclarationSource:
    return load_declaration_source_bytes(
        yaml.safe_dump(document, sort_keys=False).encode(),
        path=Path("declaration.yaml"),
    )


def _validate(document: dict[str, object]) -> None:
    _validate_external_declaration_semantics(
        _loaded(document),
        NAMESPACE,
        LOCATION,
    )


@pytest.mark.parametrize(
    "filename",
    (
        "rule.yaml",
        "rule-set.yaml",
        "procedure.yaml",
        "resolution-policy.yaml",
        "composition-manifest.yaml",
        "evaluator.yaml",
        "operation.yaml",
    ),
)
def test_every_declaration_kind_accepts_authorized_unknown_references(
    filename: str,
) -> None:
    _validate(_document(filename))


@pytest.mark.parametrize(
    ("case", "expected_location"),
    (
        ("relation", ".relations[0].target"),
        ("rule-evaluator", ".criteria[0].evaluator.id"),
        ("embedded-rule-evaluator", ".rules[0].criteria[0].evaluator.id"),
        ("procedure-predicate", ".postconditions[0].evaluator.id"),
        ("operation-predicate", ".preconditions[0].evaluator.id"),
        ("procedure-operation", ".actions[0].operation.id"),
        ("policy-conflict", ".conflicts[0]"),
        ("policy-retain", ".strategy.retain"),
        ("policy-replace", ".strategy.replace"),
        ("policy-with", ".strategy.with"),
        ("policy-result", ".strategy.result"),
        ("manifest-declaration", ".sections[0].declarations[0]"),
        ("manifest-policy", ".policies[0]"),
    ),
)
def test_reference_matrix_rejects_every_closed_reference_class(
    case: str,
    expected_location: str,
) -> None:
    document = _invalid_reference_document(case)

    with pytest.raises(
        AcquisitionContractError,
        match="external identifier grammar",
    ) as raised:
        _validate(document)

    assert raised.value.location == LOCATION + expected_location


def _invalid_reference_document(case: str) -> dict[str, object]:
    """Build one schema-valid document with one malformed declaration reference."""
    invalid = "invalid_reference"
    if case in {"relation", "rule-evaluator"}:
        document = _document("rule.yaml")
        if case == "relation":
            document["relations"] = [{"type": "requires", "target": invalid}]
        else:
            criterion = _mapping(_sequence(document["criteria"])[0])
            _mapping(criterion["evaluator"])["id"] = invalid
        return document
    if case == "embedded-rule-evaluator":
        document = _document("rule-set.yaml")
        rule = _mapping(_sequence(document["rules"])[0])
        criterion = _mapping(_sequence(rule["criteria"])[0])
        _mapping(criterion["evaluator"])["id"] = invalid
        return document
    if case in {"procedure-predicate", "procedure-operation"}:
        document = _document("procedure.yaml")
        if case == "procedure-predicate":
            predicate = _mapping(_sequence(document["postconditions"])[0])
            predicate["evaluator"] = {"id": invalid, "version": 1}
        else:
            action = _mapping(_sequence(document["actions"])[0])
            _mapping(action["operation"])["id"] = invalid
        return document
    if case == "operation-predicate":
        document = _document("operation.yaml")
        document["preconditions"] = [
            {
                "id": "authorized",
                "class": "authorization",
                "expression": {"facet": "context.available", "operator": "exists"},
                "evaluator": {"id": invalid, "version": 1},
            }
        ]
        return document
    if case.startswith("policy-"):
        document = _document("resolution-policy.yaml")
        if case == "policy-conflict":
            _sequence(document["conflicts"])[0] = invalid
            return document
        field = case.removeprefix("policy-")
        strategy = _mapping(document["strategy"])
        if field == "retain":
            _sequence(document["conflicts"])[0] = invalid
            strategy["retain"] = invalid
        elif field in {"replace", "with"}:
            if field == "replace":
                _sequence(document["conflicts"])[0] = invalid
            strategy.clear()
            strategy.update(
                {
                    "kind": "substitute",
                    "replace": invalid if field == "replace" else "shared/format",
                    "with": invalid if field == "with" else "shared/replacement",
                }
            )
        else:
            strategy.clear()
            strategy.update({"kind": "combine", "result": invalid})
        return document
    document = _document("composition-manifest.yaml")
    if case == "manifest-declaration":
        section = _mapping(_sequence(document["sections"])[0])
        _sequence(section["declarations"])[0] = invalid
    else:
        _sequence(document["policies"])[0] = invalid
    return document


@pytest.mark.parametrize(
    ("field", "value", "expected_location", "message"),
    (
        (
            "id",
            "other/reader-purpose",
            ".id",
            "identifier namespace differs",
        ),
        ("owner", "other", ".owner", "owner differs"),
    ),
)
def test_top_level_identity_must_match_source_namespace(
    field: str,
    value: str,
    expected_location: str,
    message: str,
) -> None:
    document = _document("rule.yaml")
    document[field] = value

    with pytest.raises(AcquisitionContractError, match=message) as raised:
        _validate(document)

    assert raised.value.location == LOCATION + expected_location


@pytest.mark.parametrize(
    ("field", "value", "expected_location", "message"),
    (
        (
            "id",
            "other/embedded",
            ".rules[0].id",
            "identifier namespace differs",
        ),
        ("owner", "other", ".rules[0].owner", "owner differs"),
    ),
)
def test_embedded_identity_must_match_source_namespace(
    field: str,
    value: str,
    expected_location: str,
    message: str,
) -> None:
    document = _document("rule-set.yaml")
    _mapping(_sequence(document["rules"])[0])[field] = value

    with pytest.raises(AcquisitionContractError, match=message) as raised:
        _validate(document)

    assert raised.value.location == LOCATION + expected_location


def test_local_identifiers_remain_outside_declaration_reference_grammar() -> None:
    document = _document("rule.yaml")
    norm = _mapping(_sequence(document["norms"])[0])
    norm["id"] = "local_identifier"
    criterion = _mapping(_sequence(document["criteria"])[0])
    criterion["norms"] = ["local_identifier"]

    _validate(document)


def test_external_semantics_validator_remains_private() -> None:
    assert not hasattr(declarations_api, "validate_external_declaration_semantics")
