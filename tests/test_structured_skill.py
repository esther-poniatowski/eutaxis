"""Exercise authenticated structured procedure Skill planning."""

from __future__ import annotations

import copy
import pickle
from pathlib import Path

import pytest
import yaml

from eutaxis.declarations import (
    AcquisitionContractError,
    AcquiredResource,
    CompositionError,
    DeclarationSemanticError,
    StructuredSkillPlan,
    acquire_external_declarations_from_path,
    plan_structured_skill,
    resolve_external_compilation_unit,
)
from eutaxis.declarations.structured_skill import (
    _STRUCTURED_SKILL_PLAN_AUTHORITIES,
    _issued_structured_skill_plan_state,
)
from tests.test_external_acquisition import _write_contract

MEDIA_TYPE = "text/x-python; charset=utf-8"
RESOURCE_PATH = "declarations/resources/publish-index.py"


def _yaml(document: dict[str, object]) -> bytes:
    return yaml.safe_dump(document, sort_keys=False).encode()


def _base(identifier: str, kind: str) -> dict[str, object]:
    return {
        "_schema": "eutaxis:declaration@1",
        "id": identifier,
        "kind": kind,
        "owner": "oikos",
        "status": "active",
        "source-revision": "fixture-1",
        "applicability": {
            "facet": "oikos.enabled",
            "operator": "equals",
            "value": True,
        },
        "relations": [],
    }


def _operation(
    *,
    identifier: str = "oikos/publish-index",
    method: str | None = "Publish only the guarded Git-index paths.",
    support_resources: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    document = {
        **_base(identifier, "operation"),
        "version": 1,
        "inputs": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "outputs": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "preconditions": [],
        "support-resources": (
            support_resources
            if support_resources is not None
            else [
                {
                    "resource": "oikos/publish-index",
                    "destination": "scripts/publish-index.py",
                }
            ]
        ),
        "effects": ["git/index"],
        "failure-outcomes": ["publish-failed"],
        "recovery": "Leave the guarded paths unchanged.",
    }
    if method is not None:
        document["method"] = method
    return document


def _procedure(identifier: str = "oikos/complete-module") -> dict[str, object]:
    return {
        **_base(identifier, "procedure"),
        "purpose": "Complete one module through guarded index publication",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "preconditions": [],
        "actions": [
            {
                "id": "publish",
                "operation": {"id": "oikos/publish-index", "version": 1},
                "with": {},
                "on-success": "published",
                "on-failure": {"publish-failed": "publish-failed"},
            }
        ],
        "entry": "publish",
        "invariants": [],
        "effects": ["git/index"],
        "postconditions": [
            {
                "id": "published",
                "class": "postcondition",
                "expression": {
                    "facet": "artifact.created",
                    "operator": "equals",
                    "value": True,
                },
            }
        ],
        "failures": ["publish-failed"],
    }


def _manifest(
    *,
    mechanism: str = "separate-directory",
    target: str = "complete-module",
    selected: list[str] | None = None,
) -> dict[str, object]:
    document = {
        **_base("oikos/complete-module-skill", "composition-manifest"),
        "mechanism": mechanism,
        "scope": "project",
        "target": target,
        "sections": [
            {
                "id": "procedure",
                "declarations": selected or ["oikos/complete-module"],
            }
        ],
        "policies": [],
    }
    if mechanism == "separate-directory":
        document["invocation"] = ["model", "user"]
    return document


def _pipeline(
    tmp_path: Path,
    *,
    operation: dict[str, object] | None = None,
    procedure: dict[str, object] | None = None,
    manifest: dict[str, object] | None = None,
    resources: tuple[tuple[str, str, str, bytes], ...] | None = None,
    extra_declarations: tuple[tuple[str, bytes], ...] = (),
):
    declaration_files = (
        ("declarations/operation.yaml", _yaml(operation or _operation())),
        ("declarations/procedure.yaml", _yaml(procedure or _procedure())),
        ("declarations/manifest.yaml", _yaml(manifest or _manifest())),
        *extra_declarations,
    )
    resource_files = resources or (
        (
            "oikos/publish-index",
            RESOURCE_PATH,
            MEDIA_TYPE,
            b"print('publish')\n",
        ),
    )
    manifest_path, lock_path = _write_contract(
        tmp_path,
        declaration_files=declaration_files,
        resource_files=resource_files,
    )
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )
    resolution = resolve_external_compilation_unit(
        acquisition,
        "oikos/complete-module-skill",
        {"oikos.enabled": True, "artifact.created": True},
    )
    return acquisition, resolution


def test_plan_closes_exact_operations_and_resources_without_reopening(
    tmp_path: Path,
) -> None:
    acquisition, resolution = _pipeline(tmp_path)
    (tmp_path / RESOURCE_PATH).write_bytes(b"print('changed later')\n")

    plan = plan_structured_skill(resolution)
    state = _issued_structured_skill_plan_state(plan)

    assert plan.manifest.id == "oikos/complete-module-skill"
    assert plan.name == "complete-module"
    assert plan.scope == "project"
    assert plan.invocation == ("model", "user")
    assert plan.procedure.id == "oikos/complete-module"
    assert tuple(operation.id for operation in plan.operations) == (
        "oikos/publish-index",
    )
    assert plan.support_resources[0].operation.id == "oikos/publish-index"
    assert plan.support_resources[0].destination == "scripts/publish-index.py"
    assert plan.support_resources[0].resource == AcquiredResource(
        "oikos",
        "oikos/publish-index",
        RESOURCE_PATH,
        MEDIA_TYPE,
        acquisition.lock.sources[0].resources[0].sha256,
        b"print('publish')\n",
    )
    assert state.resource_evidence[0].authoritative.data == b"print('publish')\n"


def test_plan_rejects_operation_without_authored_method(tmp_path: Path) -> None:
    _acquisition, resolution = _pipeline(tmp_path, operation=_operation(method=None))

    with pytest.raises(CompositionError, match="non-empty authored method") as raised:
        plan_structured_skill(resolution)

    assert raised.value.location.endswith(".method")


@pytest.mark.parametrize(
    "purpose",
    (
        "   ",
        "Two\rlines",
        "Two\u2028lines",
        "Two\x85lines",
        "Two\vlines",
        "Two\flines",
    ),
)
def test_plan_rejects_invalid_skill_description(tmp_path: Path, purpose: str) -> None:
    procedure = _procedure()
    procedure["purpose"] = purpose
    _acquisition, resolution = _pipeline(tmp_path, procedure=procedure)

    with pytest.raises(CompositionError, match="one-line Skill description"):
        plan_structured_skill(resolution)


def test_plan_rejects_unknown_acquired_resource(tmp_path: Path) -> None:
    operation = _operation(
        support_resources=[
            {
                "resource": "oikos/not-acquired",
                "destination": "scripts/publish-index.py",
            }
        ]
    )
    _acquisition, resolution = _pipeline(tmp_path, operation=operation)

    with pytest.raises(CompositionError, match="unknown acquired resource") as raised:
        plan_structured_skill(resolution)

    assert raised.value.location.endswith(".support-resources[0].resource")


@pytest.mark.parametrize(
    ("supports", "resources", "message"),
    (
        (
            [
                {
                    "resource": "oikos/publish-index",
                    "destination": "scripts/shared.py",
                },
                {
                    "resource": "oikos/check-index",
                    "destination": "scripts/shared.py",
                },
            ],
            (
                ("oikos/publish-index", RESOURCE_PATH, MEDIA_TYPE, b"one\n"),
                (
                    "oikos/check-index",
                    "declarations/resources/check-index.py",
                    MEDIA_TYPE,
                    b"two\n",
                ),
            ),
            "names multiple resources",
        ),
        (
            [
                {
                    "resource": "oikos/publish-index",
                    "destination": "scripts/first.py",
                },
                {
                    "resource": "oikos/publish-index",
                    "destination": "scripts/second.py",
                },
            ],
            (("oikos/publish-index", RESOURCE_PATH, MEDIA_TYPE, b"one\n"),),
            "multiple destinations",
        ),
        (
            [
                {
                    "resource": "oikos/publish-index",
                    "destination": "scripts/tool.py",
                },
                {
                    "resource": "oikos/check-index",
                    "destination": "scripts/tool.py/data",
                },
            ],
            (
                ("oikos/publish-index", RESOURCE_PATH, MEDIA_TYPE, b"one\n"),
                (
                    "oikos/check-index",
                    "declarations/resources/check-index.py",
                    MEDIA_TYPE,
                    b"two\n",
                ),
            ),
            "collides with artifact path",
        ),
        (
            [
                {
                    "resource": "oikos/publish-index",
                    "destination": "scripts/tool.py/data",
                },
                {
                    "resource": "oikos/check-index",
                    "destination": "scripts/tool.py",
                },
            ],
            (
                ("oikos/publish-index", RESOURCE_PATH, MEDIA_TYPE, b"one\n"),
                (
                    "oikos/check-index",
                    "declarations/resources/check-index.py",
                    MEDIA_TYPE,
                    b"two\n",
                ),
            ),
            "collides with artifact path",
        ),
    ),
)
def test_plan_rejects_ambiguous_resource_placement(
    tmp_path: Path,
    supports: list[dict[str, str]],
    resources: tuple[tuple[str, str, str, bytes], ...],
    message: str,
) -> None:
    _acquisition, resolution = _pipeline(
        tmp_path,
        operation=_operation(support_resources=supports),
        resources=resources,
    )

    with pytest.raises(CompositionError, match=message):
        plan_structured_skill(resolution)


@pytest.mark.parametrize(
    "destination",
    (
        "references/contract.md",
        "references",
        "references/contract.md/payload.py",
        "agents",
        "agents/openai.yaml/payload",
    ),
)
def test_plan_rejects_reserved_resource_destination(
    tmp_path: Path, destination: str
) -> None:
    operation = _operation(
        support_resources=[
            {
                "resource": "oikos/publish-index",
                "destination": destination,
            }
        ]
    )
    _acquisition, resolution = _pipeline(tmp_path, operation=operation)

    with pytest.raises(CompositionError, match="is reserved"):
        plan_structured_skill(resolution)


def test_declaration_rejects_reserved_device_destination(tmp_path: Path) -> None:
    operation = _operation(
        support_resources=[
            {
                "resource": "oikos/publish-index",
                "destination": "scripts/com1.py",
            }
        ]
    )

    with pytest.raises(DeclarationSemanticError, match="reserved device stem"):
        _pipeline(tmp_path, operation=operation)


@pytest.mark.parametrize("target", ("con", "a" * 65))
def test_plan_rejects_nonportable_skill_name(tmp_path: Path, target: str) -> None:
    _acquisition, resolution = _pipeline(tmp_path, manifest=_manifest(target=target))

    with pytest.raises(CompositionError, match="portable segment"):
        plan_structured_skill(resolution)


def test_plan_rejects_non_procedure_root(tmp_path: Path) -> None:
    selected = {
        **_base("oikos/not-a-procedure", "rule"),
        "axis": "reasoning-target",
        "failure-mode": "visible",
        "norms": [
            {
                "id": "state-purpose",
                "modality": "must",
                "subject": "agent",
                "action": {"verb": "state", "object": "the purpose"},
            }
        ],
        "criteria": [
            {
                "id": "purpose-stated",
                "norms": ["state-purpose"],
                "evaluator": {"id": "eutaxis/manual-judgment", "version": 1},
                "statement": "The purpose is stated",
            }
        ],
    }
    manifest = _manifest(selected=["oikos/not-a-procedure"])
    _acquisition, resolution = _pipeline(
        tmp_path,
        manifest=manifest,
        extra_declarations=(("declarations/not-procedure.yaml", _yaml(selected)),),
    )

    with pytest.raises(CompositionError, match="is not a procedure"):
        plan_structured_skill(resolution)


def test_plan_rejects_multiple_root_procedures(tmp_path: Path) -> None:
    manifest = _manifest(selected=["oikos/complete-module", "oikos/other-module"])
    other = _procedure("oikos/other-module")
    _acquisition, resolution = _pipeline(
        tmp_path,
        manifest=manifest,
        extra_declarations=(("declarations/other-procedure.yaml", _yaml(other)),),
    )

    with pytest.raises(CompositionError, match="exactly one root procedure"):
        plan_structured_skill(resolution)


def test_plan_rejects_non_skill_manifest(tmp_path: Path) -> None:
    _acquisition, resolution = _pipeline(
        tmp_path,
        manifest=_manifest(mechanism="cumulative", target="AGENTS.md"),
    )

    with pytest.raises(CompositionError, match="is not separate-directory"):
        plan_structured_skill(resolution)


def test_plan_reauthenticates_public_resource_projection(tmp_path: Path) -> None:
    _acquisition, resolution = _pipeline(tmp_path)
    plan = plan_structured_skill(resolution)
    object.__setattr__(plan.support_resources[0], "destination", "scripts/forged.py")

    with pytest.raises(CompositionError, match="plan state changed"):
        _issued_structured_skill_plan_state(plan)


def test_plan_preserves_first_use_operation_order_and_support_ownership(
    tmp_path: Path,
) -> None:
    second = _operation(identifier="oikos/check-index")
    procedure = _procedure()
    procedure["actions"] = [
        {
            "id": "check-first",
            "operation": {"id": "oikos/check-index", "version": 1},
            "with": {},
            "on-success": "publish",
            "on-failure": {"publish-failed": "publish-failed"},
        },
        {
            "id": "publish",
            "operation": {"id": "oikos/publish-index", "version": 1},
            "with": {},
            "on-success": "check-again",
            "on-failure": {"publish-failed": "publish-failed"},
        },
        {
            "id": "check-again",
            "operation": {"id": "oikos/check-index", "version": 1},
            "with": {},
            "on-success": "published",
            "on-failure": {"publish-failed": "publish-failed"},
        },
    ]
    procedure["entry"] = "check-first"
    _acquisition, resolution = _pipeline(
        tmp_path,
        procedure=procedure,
        extra_declarations=(("declarations/check-operation.yaml", _yaml(second)),),
    )

    plan = plan_structured_skill(resolution)

    assert tuple(operation.id for operation in plan.operations) == (
        "oikos/check-index",
        "oikos/publish-index",
    )
    assert tuple(resource.operation.id for resource in plan.support_resources) == (
        "oikos/check-index",
        "oikos/publish-index",
    )
    assert {resource.destination for resource in plan.support_resources} == {
        "scripts/publish-index.py"
    }


def test_failed_upstream_reauthentication_retires_plan(tmp_path: Path) -> None:
    _acquisition, resolution = _pipeline(tmp_path)
    plan = plan_structured_skill(resolution)
    object.__setattr__(plan.procedure, "purpose", "changed")

    with pytest.raises(AcquisitionContractError, match="state changed"):
        _issued_structured_skill_plan_state(plan)
    with pytest.raises(CompositionError, match="not issued"):
        _issued_structured_skill_plan_state(plan)


def test_plan_rejects_construction_copy_serialization_and_foreign_state(
    tmp_path: Path,
) -> None:
    with pytest.raises(TypeError, match="must be issued"):
        StructuredSkillPlan()
    forged = object.__new__(StructuredSkillPlan)
    with pytest.raises(CompositionError, match="not issued"):
        _issued_structured_skill_plan_state(forged)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(forged)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(forged)

    _first_acquisition, first_resolution = _pipeline(tmp_path / "first")
    first = plan_structured_skill(first_resolution)
    first_state = _issued_structured_skill_plan_state(first)
    _second_acquisition, second_resolution = _pipeline(tmp_path / "second")
    second = plan_structured_skill(second_resolution)
    second_state = _issued_structured_skill_plan_state(second)
    token = _STRUCTURED_SKILL_PLAN_AUTHORITIES.issue(
        first,
        first_state._replace(resource_evidence=second_state.resource_evidence),
    )
    object.__setattr__(first, "_token", token)

    with pytest.raises(CompositionError, match="resource evidence changed"):
        _issued_structured_skill_plan_state(first)
