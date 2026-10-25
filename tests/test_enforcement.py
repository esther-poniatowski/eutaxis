"""Tests for declared enforcement classification and catalog filtering."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
import yaml

from eutaxis.declarations import (
    DeclarationCatalog,
    DeclarationKind,
    EnforcementClass,
    EnforcementClassificationError,
    EvaluatorDeclaration,
    OperationPredicateEnforcement,
    PredicatePhase,
    ProcedurePredicateEnforcement,
    RuleCriterionEnforcement,
    VersionedReference,
    build_declaration_catalog,
    catalog_json_bytes,
    derive_enforcement_class,
    load_declaration_registry,
    load_facet_registry,
)

FIXTURES = Path(__file__).parent / "fixtures"
REGISTRY_ROOT = FIXTURES / "registry" / "valid"
FACET_PATH = FIXTURES / "facets" / "valid" / "context-facets.yaml"


def _read(root: Path, name: str) -> dict[str, object]:
    return yaml.safe_load((root / name).read_text(encoding="utf-8"))


def _write(root: Path, name: str, document: dict[str, object]) -> None:
    (root / name).write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )


def _catalog(tmp_path: Path) -> DeclarationCatalog:
    root = tmp_path / "registry"
    shutil.copytree(REGISTRY_ROOT, root)

    manual = _read(root, "evaluator.yaml")
    checker = dict(manual)
    checker.update(
        {
            "id": "registry/checker",
            "evaluator-kind": "checker",
            "coverage": "total",
            "adjudication": "authoritative",
            "known-failure-fixtures": ["registry/checker/planted"],
        }
    )
    _write(root, "checker.yaml", checker)
    detector = dict(manual)
    detector.update(
        {
            "id": "registry/detector",
            "evaluator-kind": "detector",
            "coverage": "partial",
            "adjudication": "candidate",
            "residual-question": "Does the candidate violate the selected obligation?",
        }
    )
    _write(root, "detector.yaml", detector)

    package = _read(root, "rule-set.yaml")
    rule = package["rules"][0]  # type: ignore[index]
    rule["criteria"] = [  # type: ignore[index]
        {
            "id": "machine-check",
            "norms": ["base"],
            "evaluator": {"id": "registry/checker", "version": 1},
            "statement": "The checker accepts the base contract",
        },
        {
            "id": "candidate-check",
            "norms": ["base"],
            "evaluator": {"id": "registry/detector", "version": 1},
            "statement": "Every detector candidate is resolved",
        },
        {
            "id": "base-check",
            "norms": ["base"],
            "evaluator": {"id": "registry/manual", "version": 1},
            "statement": "The base contract is preserved",
        },
    ]
    _write(root, "rule-set.yaml", package)

    procedure = _read(root, "procedure.yaml")
    procedure["preconditions"] = [
        {
            "id": "manual-precondition",
            "class": "assumption",
            "expression": {"facet": "context.available", "operator": "exists"},
            "evaluator": {"id": "registry/manual", "version": 1},
        }
    ]
    procedure["invariants"] = [
        {
            "id": "detected-invariant",
            "class": "invariant",
            "expression": {"facet": "context.available", "operator": "exists"},
            "evaluator": {"id": "registry/detector", "version": 1},
            "observes": ["registry/stable"],
        }
    ]
    procedure["postconditions"].append(  # type: ignore[attr-defined]
        {
            "id": "checked-postcondition",
            "class": "postcondition",
            "expression": {
                "facet": "artifact.written",
                "operator": "equals",
                "value": True,
            },
            "evaluator": {"id": "registry/checker", "version": 1},
        }
    )
    _write(root, "procedure.yaml", procedure)

    operation = _read(root, "operation.yaml")
    operation["preconditions"] = [
        {
            "id": "manual-operation-precondition",
            "class": "authorization",
            "expression": {"facet": "context.available", "operator": "exists"},
            "evaluator": {"id": "registry/manual", "version": 1},
        }
    ]
    _write(root, "operation.yaml", operation)

    registry = load_declaration_registry(
        tuple(sorted(root.glob("*.yaml"))), load_facet_registry(FACET_PATH)
    )
    return build_declaration_catalog(registry, source_root=root)


def test_enforcement_class_is_derived_from_complete_evaluator_contract(
    tmp_path: Path,
) -> None:
    catalog = _catalog(tmp_path)
    expected = {
        "registry/checker": EnforcementClass.MECHANICAL,
        "registry/detector": EnforcementClass.ASSISTED,
        "registry/manual": EnforcementClass.DELIBERATIVE,
    }

    for identifier, enforcement in expected.items():
        record = catalog.get_contract(
            kind=DeclarationKind.EVALUATOR, identifier=identifier, version=1
        )
        assert record is not None
        evaluator = cast(EvaluatorDeclaration, record.declaration)
        assert derive_enforcement_class(evaluator) is enforcement


def test_catalog_filters_mixed_obligations_at_locator_granularity(
    tmp_path: Path,
) -> None:
    catalog = _catalog(tmp_path)

    assert catalog.filter_enforcement(EnforcementClass.MECHANICAL) == (
        RuleCriterionEnforcement(
            "content/base",
            "machine-check",
            VersionedReference("registry/checker", 1),
            EnforcementClass.MECHANICAL,
        ),
        ProcedurePredicateEnforcement(
            "content/write",
            PredicatePhase.POSTCONDITION,
            "checked-postcondition",
            VersionedReference("registry/checker", 1),
            EnforcementClass.MECHANICAL,
        ),
    )
    assert catalog.filter_enforcement(EnforcementClass.ASSISTED) == (
        RuleCriterionEnforcement(
            "content/base",
            "candidate-check",
            VersionedReference("registry/detector", 1),
            EnforcementClass.ASSISTED,
        ),
        ProcedurePredicateEnforcement(
            "content/write",
            PredicatePhase.INVARIANT,
            "detected-invariant",
            VersionedReference("registry/detector", 1),
            EnforcementClass.ASSISTED,
        ),
    )
    assert catalog.filter_enforcement(EnforcementClass.DELIBERATIVE) == (
        RuleCriterionEnforcement(
            "content/alternate",
            "alternate-check",
            VersionedReference("registry/manual", 1),
            EnforcementClass.DELIBERATIVE,
        ),
        RuleCriterionEnforcement(
            "content/base",
            "base-check",
            VersionedReference("registry/manual", 1),
            EnforcementClass.DELIBERATIVE,
        ),
        RuleCriterionEnforcement(
            "content/combined",
            "combined-check",
            VersionedReference("registry/manual", 1),
            EnforcementClass.DELIBERATIVE,
        ),
        RuleCriterionEnforcement(
            "content/refined",
            "refined-check",
            VersionedReference("registry/manual", 1),
            EnforcementClass.DELIBERATIVE,
        ),
        ProcedurePredicateEnforcement(
            "content/write",
            PredicatePhase.PRECONDITION,
            "manual-precondition",
            VersionedReference("registry/manual", 1),
            EnforcementClass.DELIBERATIVE,
        ),
        OperationPredicateEnforcement(
            VersionedReference("registry/write", 1),
            "manual-operation-precondition",
            VersionedReference("registry/manual", 1),
            EnforcementClass.DELIBERATIVE,
        ),
    )


def test_evaluator_less_predicates_are_not_classified(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    identifiers = {
        locator.predicate
        for enforcement in EnforcementClass
        for locator in catalog.filter_enforcement(enforcement)
        if isinstance(
            locator,
            (ProcedurePredicateEnforcement, OperationPredicateEnforcement),
        )
    }

    assert "written" not in identifiers


def test_invalid_capability_triples_are_rejected(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    record = catalog.get_contract(DeclarationKind.EVALUATOR, "registry/manual", 1)
    assert record is not None
    evaluator = cast(EvaluatorDeclaration, record.declaration)
    invalid = replace(evaluator, coverage="total")

    with pytest.raises(EnforcementClassificationError, match="no admitted"):
        derive_enforcement_class(invalid)


def test_detector_residual_question_is_preserved_in_the_catalog_index(
    tmp_path: Path,
) -> None:
    payload = json.loads(catalog_json_bytes(_catalog(tmp_path)))
    detector = next(
        item for item in payload["contracts"] if item["id"] == "registry/detector"
    )

    assert detector["query"]["residual-question"] == (
        "Does the candidate violate the selected obligation?"
    )
