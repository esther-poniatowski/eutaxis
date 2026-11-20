"""Exercise SARIF output from the manifest-defined declaration corpus check."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from elenchos.profile import violations  # type: ignore[import-untyped]
from typer.testing import CliRunner

import eutaxis.declarations._cli as check_cli_module
from eutaxis.cli import app
from eutaxis.declarations.exceptions import DeclarationSchemaError


def _write_workspace(root: Path) -> str:
    """Write a valid corpus that uses one consumer-owned context facet."""
    declarations = root / "declarations"
    declarations.mkdir(parents=True)
    (declarations / "context-facets.yaml").write_text(
        "\n".join(
            (
                "_schema: eutaxis:context-facets@1",
                "id: geonexus/context-facets",
                "owner: geonexus",
                "source-revision: v1",
                "facets:",
                "  - id: geonexus.repository",
                "    value-schema: {type: boolean}",
                "",
            )
        ),
        encoding="utf-8",
    )
    (declarations / "repository-rule.yaml").write_text(
        "\n".join(
            (
                "_schema: eutaxis:declaration@1",
                "id: geonexus/repository-rule",
                "kind: rule",
                "owner: geonexus",
                "status: active",
                "source-revision: fixture-1",
                "applicability:",
                "  all:",
                "    - {facet: context.available, operator: exists}",
                "    - {facet: geonexus.repository, operator: equals, value: true}",
                "relations: []",
                "axis: reasoning-target",
                "failure-mode: visible",
                "norms:",
                "  - id: preserve-model",
                "    modality: must",
                "    subject: agent",
                "    action: {verb: preserve, object: the repository model}",
                "criteria:",
                "  - id: model-is-preserved",
                "    norms: [preserve-model]",
                "    evaluator: {id: eutaxis/manual-judgment, version: 1}",
                "    statement: The repository model remains intact",
                "",
            )
        ),
        encoding="utf-8",
    )
    manifest = "declarations/acquisition.yaml"
    (root / manifest).write_text(
        "\n".join(
            (
                "schema-version: 1",
                "facet-extensions:",
                "  - namespace: geonexus",
                "    kind: workspace",
                "    root: .",
                "    path: declarations/context-facets.yaml",
                "internal-source:",
                "  namespace: eutaxis",
                "  kind: packaged",
                "sources:",
                "  - namespace: geonexus",
                "    kind: workspace",
                "    root: .",
                "    files: [declarations/repository-rule.yaml]",
                "",
            )
        ),
        encoding="utf-8",
    )
    return manifest


def _add_rule_skill(
    root: Path,
    *,
    failure_mode: str,
    required_visibility: str | None,
    invocation: list[str],
) -> None:
    """Add one rule-set Skill candidate to the checked corpus."""
    rule: dict[str, object] = {
        "_schema": "eutaxis:declaration@1",
        "id": "geonexus/skill-rule",
        "kind": "rule",
        "owner": "geonexus",
        "status": "active",
        "source-revision": "fixture-1",
        "applicability": {
            "facet": "geonexus.repository",
            "operator": "equals",
            "value": True,
        },
        "relations": [],
        "axis": "reasoning-target",
        "failure-mode": failure_mode,
        "norms": [
            {
                "id": "preserve-skill",
                "modality": "must",
                "subject": "agent",
                "action": {"verb": "preserve", "object": "the Skill boundary"},
            }
        ],
        "criteria": [
            {
                "id": "skill-is-preserved",
                "norms": ["preserve-skill"],
                "evaluator": {"id": "eutaxis/manual-judgment", "version": 1},
                "statement": "The Skill boundary remains intact",
            }
        ],
    }
    if required_visibility is not None:
        rule["required-visibility"] = required_visibility
    rule_set = {
        "_schema": "eutaxis:declaration@1",
        "id": "geonexus/skill-rules",
        "kind": "rule-set",
        "owner": "geonexus",
        "status": "active",
        "source-revision": "fixture-1",
        "applicability": {
            "facet": "geonexus.repository",
            "operator": "equals",
            "value": True,
        },
        "relations": [],
        "purpose": "Preserve the tested Skill boundary",
        "rules": [rule],
    }
    composition = {
        "_schema": "eutaxis:declaration@1",
        "id": "geonexus/skill-manifest",
        "kind": "composition-manifest",
        "owner": "geonexus",
        "status": "active",
        "source-revision": "fixture-1",
        "applicability": {
            "facet": "geonexus.repository",
            "operator": "equals",
            "value": True,
        },
        "relations": [],
        "mechanism": "separate-directory",
        "scope": "project",
        "target": "testing",
        "invocation": invocation,
        "sections": [{"id": "rules", "declarations": ["geonexus/skill-rules"]}],
        "policies": [],
    }
    declarations = root / "declarations"
    (declarations / "skill-rules.yaml").write_text(
        yaml.safe_dump(rule_set, sort_keys=False),
        encoding="utf-8",
    )
    (declarations / "skill-manifest.yaml").write_text(
        yaml.safe_dump(composition, sort_keys=False),
        encoding="utf-8",
    )
    acquisition_path = declarations / "acquisition.yaml"
    acquisition = yaml.safe_load(acquisition_path.read_text(encoding="utf-8"))
    acquisition["sources"][0]["files"].extend(
        ["declarations/skill-rules.yaml", "declarations/skill-manifest.yaml"]
    )
    acquisition_path.write_text(
        yaml.safe_dump(acquisition, sort_keys=False),
        encoding="utf-8",
    )


def _invoke(root: Path, manifest: str):
    """Run the public corpus checker against one workspace manifest."""
    return CliRunner().invoke(
        app,
        [
            "declarations",
            "check",
            "--workspace",
            str(root),
            "--manifest",
            manifest,
        ],
    )


def _sarif(result) -> dict[str, object]:
    """Parse the command's sole standard-output artifact."""
    assert result.stderr == ""
    return json.loads(result.stdout)


# The writer does not yet conform to the findings profile of Elenchos (see TODO.md).
# Each test therefore freezes the nodes of its log that break the profile. A new break
# fails the test, and a repair fails it too, until the frozen list shrinks to the empty
# list of a conforming log.
_LOG_BREAKS = ("/$schema", "/runs/0/tool/driver", "/runs/0/tool/driver/name")
"""Nodes of every log that break the profile: schema URI, driver version and name."""

_LOCATED_BREAKS = (
    "/runs/0",
    "/runs/0/results/0/locations/0/logicalLocations/0/name",
    "/runs/0/results/0/locations/0/physicalLocation/artifactLocation",
    "/runs/0/tool/driver/rules/0",
)
"""Further nodes of a log holding one located result: `columnKind`, the resource of the
logical name, the URI base, and the default level of the rule."""


def _profile_breaks(report: object) -> list[str]:
    """Return the sorted pointers of the log nodes reported by `elenchos.profile`."""
    return sorted(violation.pointer for violation in violations(report))


def _breaks(*pointers: str) -> list[str]:
    """Return the sorted pointers of the frozen breaks of one log."""
    return sorted((*_LOG_BREAKS, *pointers))


def test_check_accepts_consumer_facets_and_emits_clean_sarif(tmp_path: Path) -> None:
    manifest = _write_workspace(tmp_path)

    first = _invoke(tmp_path, manifest)
    second = _invoke(tmp_path, manifest)

    assert first.exit_code == 0
    assert first.stdout_bytes == second.stdout_bytes
    report = _sarif(first)
    assert report["version"] == "2.1.0"
    run = report["runs"][0]  # type: ignore[index]
    assert run["results"] == []
    assert run["invocations"] == [{"executionSuccessful": True}]
    assert _profile_breaks(report) == _breaks()


@pytest.mark.parametrize(
    ("failure_mode", "required_visibility", "invocation"),
    [
        ("visible", None, ["model", "user"]),
        ("silent", "pre-action", ["user"]),
    ],
)
def test_check_accepts_permitted_rule_skill_placement(
    tmp_path: Path,
    failure_mode: str,
    required_visibility: str | None,
    invocation: list[str],
) -> None:
    manifest = _write_workspace(tmp_path)
    _add_rule_skill(
        tmp_path,
        failure_mode=failure_mode,
        required_visibility=required_visibility,
        invocation=invocation,
    )

    result = _invoke(tmp_path, manifest)

    assert result.exit_code == 0
    report = _sarif(result)
    assert report["runs"][0]["results"] == []  # type: ignore[index]
    assert _profile_breaks(report) == _breaks()


@pytest.mark.parametrize(
    ("required_visibility", "invocation", "message"),
    [
        ("pre-invocation", ["user"], "pre-invocation"),
        ("pre-action", ["model", "user"], "model invocation"),
    ],
)
def test_check_rejects_forbidden_rule_skill_placement(
    tmp_path: Path,
    required_visibility: str,
    invocation: list[str],
    message: str,
) -> None:
    manifest = _write_workspace(tmp_path)
    _add_rule_skill(
        tmp_path,
        failure_mode="silent",
        required_visibility=required_visibility,
        invocation=invocation,
    )

    result = _invoke(tmp_path, manifest)

    assert result.exit_code == 1
    report = _sarif(result)
    finding = report["runs"][0]["results"][0]  # type: ignore[index]
    assert finding["ruleId"] == "eutaxis.declarations.registry"
    assert finding["locations"][0]["logicalLocations"] == [{"name": "$.invocation"}]
    assert _profile_breaks(report) == _breaks(*_LOCATED_BREAKS)
    assert "geonexus/skill-rule" in finding["message"]["text"]
    assert message in finding["message"]["text"]


def test_check_reports_a_located_declaration_schema_finding(tmp_path: Path) -> None:
    manifest = _write_workspace(tmp_path)
    path = tmp_path / "declarations" / "repository-rule.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    del document["axis"]
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    result = _invoke(tmp_path, manifest)

    assert result.exit_code == 1
    report = _sarif(result)
    finding = report["runs"][0]["results"][0]  # type: ignore[index]
    assert finding["ruleId"] == "eutaxis.declarations.schema"
    physical = finding["locations"][0]["physicalLocation"]
    assert physical["artifactLocation"]["uri"].endswith("repository-rule.yaml")
    assert physical["region"]["startLine"] > 0
    assert _profile_breaks(report) == _breaks(*_LOCATED_BREAKS)


def test_check_reports_a_cross_record_registry_finding(tmp_path: Path) -> None:
    manifest = _write_workspace(tmp_path)
    path = tmp_path / "declarations" / "repository-rule.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["relations"] = [{"type": "requires", "target": "missing/rule"}]
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    result = _invoke(tmp_path, manifest)

    assert result.exit_code == 1
    report = _sarif(result)
    finding = report["runs"][0]["results"][0]  # type: ignore[index]
    assert finding["ruleId"] == "eutaxis.declarations.registry"
    assert finding["locations"][0]["logicalLocations"] == [
        {"name": "$.relations[0].target"}
    ]
    assert _profile_breaks(report) == _breaks(*_LOCATED_BREAKS)


def test_check_reports_an_incomplete_decision_matrix(tmp_path: Path) -> None:
    manifest = _write_workspace(tmp_path)
    path = tmp_path / "declarations" / "repository-rule.yaml"
    decision = {
        "_schema": "eutaxis:declaration@1",
        "id": "geonexus/repository-decision",
        "kind": "decision",
        "owner": "geonexus",
        "status": "active",
        "source-revision": "fixture-1",
        "applicability": {
            "facet": "geonexus.repository",
            "operator": "equals",
            "value": True,
        },
        "relations": [],
        "context": "The repository needs one declaration format.",
        "drivers": [
            {"id": "structure", "statement": "Fields must be typed."},
            {"id": "prose", "statement": "Explanations must be retained."},
        ],
        "options": [
            {
                "id": "yaml",
                "description": "Use YAML with Markdown fields.",
                "assessments": [
                    {"driver": "structure", "judgment": "Fields are typed."}
                ],
            }
        ],
        "outcome": "yaml",
        "consequences": "Declarations use YAML.",
    }
    path.write_text(yaml.safe_dump(decision, sort_keys=False), encoding="utf-8")

    result = _invoke(tmp_path, manifest)

    assert result.exit_code == 1
    report = _sarif(result)
    finding = report["runs"][0]["results"][0]  # type: ignore[index]
    assert finding["ruleId"] == "eutaxis.declarations.semantic"
    assert finding["locations"][0]["logicalLocations"] == [
        {"name": "$.options[0].assessments"}
    ]
    assert _profile_breaks(report) == _breaks(*_LOCATED_BREAKS)


def test_check_reports_operational_failure_as_sarif(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    result = _invoke(missing, "declarations/acquisition.yaml")

    assert result.exit_code == 2
    report = _sarif(result)
    run = report["runs"][0]  # type: ignore[index]
    assert run["invocations"] == [{"executionSuccessful": False}]
    assert run["results"][0]["ruleId"] == "eutaxis.acquisition.io"
    assert _profile_breaks(report) == _breaks(
        "/runs/0",
        "/runs/0/invocations/0",
        "/runs/0/results/0/locations/0",
        "/runs/0/results/0/locations/0/physicalLocation/artifactLocation",
        "/runs/0/results/0/locations/0/physicalLocation/artifactLocation/uri",
        "/runs/0/tool/driver/rules/0",
    )


def test_check_maps_unexpected_workspace_open_failure_to_exit_two(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_open(_workspace: str):
        raise RuntimeError("injected open failure")

    monkeypatch.setattr(
        check_cli_module,
        "_trusted_directory_from_workspace_path",
        fail_open,
    )

    result = _invoke(tmp_path, "declarations/acquisition.yaml")

    assert result.exit_code == 2
    report = _sarif(result)
    run = report["runs"][0]  # type: ignore[index]
    assert run["invocations"] == [{"executionSuccessful": False}]
    assert run["results"][0]["ruleId"] == "eutaxis.execution.internal"
    assert _profile_breaks(report) == _breaks(
        "/runs/0",
        "/runs/0/invocations/0",
        "/runs/0/results/0",
        "/runs/0/tool/driver/rules/0",
    )


def test_check_promotes_cleanup_failure_without_hiding_corpus_finding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingWorkspace:
        def close(self) -> None:
            raise OSError("injected close failure")

    def fail_validation(_workspace: object, _manifest: str) -> bytes:
        raise DeclarationSchemaError(
            Path("declarations/rule.yaml"),
            "$.axis",
            "'axis' is required",
            line=8,
            column=1,
        )

    monkeypatch.setattr(
        check_cli_module,
        "_trusted_directory_from_workspace_path",
        lambda _workspace: FailingWorkspace(),
    )
    monkeypatch.setattr(
        check_cli_module,
        "_validated_workspace_candidate_bytes",
        fail_validation,
    )

    result = _invoke(tmp_path, "declarations/acquisition.yaml")

    assert result.exit_code == 2
    report = _sarif(result)
    run = report["runs"][0]  # type: ignore[index]
    assert run["invocations"] == [{"executionSuccessful": False}]
    assert [item["ruleId"] for item in run["results"]] == [
        "eutaxis.execution.io",
        "eutaxis.declarations.schema",
    ]
    assert [item["ruleIndex"] for item in run["results"]] == [0, 1]
    assert _profile_breaks(report) == _breaks(
        "/runs/0",
        "/runs/0/invocations/0",
        "/runs/0/results/0",
        "/runs/0/results/1/locations/0/logicalLocations/0/name",
        "/runs/0/results/1/locations/0/physicalLocation/artifactLocation",
        "/runs/0/tool/driver/rules/0",
        "/runs/0/tool/driver/rules/1",
    )


def test_check_maps_stalled_stdout_to_exit_two(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _write_workspace(tmp_path)

    def fail_write(_content: bytes) -> None:
        raise OSError("injected stalled write")

    monkeypatch.setattr(check_cli_module, "_write_exact_stdout", fail_write)

    result = _invoke(tmp_path, manifest)

    assert result.exit_code == 2
    assert result.stdout == ""
