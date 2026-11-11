"""Exercise SARIF output from the manifest-defined declaration corpus check."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
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


def test_check_reports_operational_failure_as_sarif(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    result = _invoke(missing, "declarations/acquisition.yaml")

    assert result.exit_code == 2
    report = _sarif(result)
    run = report["runs"][0]  # type: ignore[index]
    assert run["invocations"] == [{"executionSuccessful": False}]
    assert run["results"][0]["ruleId"] == "eutaxis.acquisition.io"


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
