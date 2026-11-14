"""Golden and authority tests for cumulative Markdown projection."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import eutaxis.declarations.external_composition as external_composition_module
from eutaxis.cli import app
from eutaxis.declarations import (
    CumulativeMarkdownProfile,
    CompositionError,
    DeclarationCatalogError,
    acquire_external_declarations_from_path,
    plan_external_cumulative_composition,
    render_external_cumulative_markdown,
    resolve_external_compilation_unit,
)
from eutaxis.declarations.catalog import _CATALOG_AUTHORITIES
from eutaxis.instructions.rules import parse_module
from tests.test_external_acquisition import _write_contract

GOLDEN = Path(__file__).parent / "fixtures" / "projection" / "cumulative-markdown.md"

FACETS = b"""\
_schema: eutaxis:context-facets@1
id: projection/context-facets
owner: projection
source-revision: fixture-1
facets:
  - id: projection.enabled
    value-schema: {type: boolean}
  - id: projection.optional
    value-schema: {type: boolean}
  - id: projection.stable
    value-schema: {type: boolean}
  - id: projection.done
    value-schema: {type: boolean}
"""

RULE = b"""\
_schema: eutaxis:declaration@1
id: projection/all-modalities
kind: rule
owner: projection
status: active
source-revision: fixture-1
applicability: {facet: projection.enabled, operator: equals, value: true}
relations: []
axis: reasoning-target
failure-mode: visible
rationale: The projection must preserve the complete effective rule
norms:
  - id: required
    modality: must
    subject: agent
    action: {verb: retain, object: every required field, timing: before rendering}
    guidance: |-
      Keep `authored Markdown` intact.

      Preserve its paragraph boundary.
    rationale: Required content defines the lower bound
  - id: prohibited
    modality: must-not
    subject: agent
    action: {verb: restore, object: excluded content}
  - id: recommended
    modality: should
    subject: agent
    action: {verb: retain, object: the recommended form}
    decision-criterion: recommended-check
  - id: discouraged
    modality: should-not
    subject: agent
    action: {verb: select, object: the discouraged form}
    decision-criterion: discouraged-check
  - id: permitted
    modality: may
    subject: agent
    action: {verb: choose, object: either equivalent form}
  - id: context-excluded
    modality: must
    subject: agent
    action: {verb: emit, object: content excluded by context}
    applies-when: {facet: projection.optional, operator: equals, value: true}
criteria:
  - id: required-check
    norms: [required]
    evaluator: {id: eutaxis/manual-judgment, version: 1}
    statement: Required fields remain visible
  - id: prohibited-check
    norms: [prohibited]
    evaluator: {id: eutaxis/manual-judgment, version: 1}
    statement: Excluded content is not restored
  - id: recommended-check
    norms: [recommended]
    evaluator: {id: eutaxis/manual-judgment, version: 1}
    statement: The recommendation is retained when its criterion wins
  - id: discouraged-check
    norms: [discouraged]
    evaluator: {id: eutaxis/manual-judgment, version: 1}
    statement: The discouraged form is absent when its criterion wins
  - id: permitted-check
    norms: [permitted]
    evaluator: {id: eutaxis/manual-judgment, version: 1}
    statement: The discretionary choice remains explicit
  - id: excluded-check
    norms: [context-excluded]
    evaluator: {id: eutaxis/manual-judgment, version: 1}
    statement: This criterion must not appear
"""

RULE_SET = b"""\
_schema: eutaxis:declaration@1
id: projection/strategic-rules
kind: rule-set
owner: projection
status: active
source-revision: fixture-1
applicability: {facet: projection.enabled, operator: equals, value: true}
relations: []
purpose: These rules govern every projected artifact
rationale: The frame states why the selected rules belong together
rules:
  - _schema: eutaxis:declaration@1
    id: projection/framed-rule
    kind: rule
    owner: projection
    status: active
    source-revision: fixture-1
    applicability: {facet: projection.enabled, operator: equals, value: true}
    relations: []
    axis: reasoning-target
    failure-mode: visible
    norms:
      - id: preserve-frame
        modality: must
        subject: agent
        action: {verb: preserve, object: the rule-set frame}
    criteria:
      - id: frame-visible
        norms: [preserve-frame]
        evaluator: {id: eutaxis/manual-judgment, version: 1}
        statement: The rule-set frame appears once
"""

OPERATION = b"""\
_schema: eutaxis:declaration@1
id: projection/transform
kind: operation
owner: projection
status: active
source-revision: fixture-1
applicability: {facet: projection.enabled, operator: equals, value: true}
relations: []
version: 1
rationale: One exact operation serves every graph node in this fixture
inputs:
  type: object
  properties:
    source: {type: string}
    marker: {type: string}
  required: [source, marker]
  additionalProperties: false
outputs:
  type: object
  properties:
    changed: {type: boolean}
  required: [changed]
  additionalProperties: false
preconditions:
  - id: source-ready
    class: guard
    expression: {facet: projection.enabled, operator: equals, value: true}
    evaluator: {id: eutaxis/manual-judgment, version: 1}
method: |-
  Transform each source in declared order.

  Inspect the `result` before publication.
effects: [projection/artifact]
failure-outcomes: [choose-failed, finalize-failed, recover-failed]
recovery: Preserve the input and report the failed graph node
"""

PROCEDURE = b"""\
_schema: eutaxis:declaration@1
id: projection/branching-procedure
kind: procedure
owner: projection
status: active
source-revision: fixture-1
applicability: {facet: projection.enabled, operator: equals, value: true}
relations: []
purpose: Exercises a graph whose entry is not its first authored node
rationale: A rendered numbered list would misstate this graph
parameters:
  type: object
  properties:
    source: {type: string}
  required: [source]
  additionalProperties: false
preconditions:
  - id: source-ready
    class: guard
    expression: {facet: projection.enabled, operator: equals, value: true}
    evaluator: {id: eutaxis/manual-judgment, version: 1}
actions:
  - id: finalize
    operation: {id: projection/transform, version: 1}
    with:
      source: {parameter: source}
      marker: {literal: final}
    on-success: complete
    on-failure:
      choose-failed: failed
      finalize-failed: failed
      recover-failed: failed
  - id: recover
    operation: {id: projection/transform, version: 1}
    with:
      source: {parameter: source}
      marker: {literal: "value ``` with backticks"}
    on-success: complete
    on-failure:
      choose-failed: failed
      finalize-failed: failed
      recover-failed: failed
  - id: choose
    operation: {id: projection/transform, version: 1}
    with:
      source: {parameter: source}
      marker: {literal: choose}
    on-success: finalize
    on-failure:
      choose-failed: recover
      finalize-failed: recover
      recover-failed: recover
entry: choose
invariants:
  - id: source-remains-stable
    class: invariant
    expression: {facet: projection.stable, operator: equals, value: true}
    evaluator: {id: eutaxis/manual-judgment, version: 1}
    observes: [projection/source]
effects: [projection/artifact]
postconditions:
  - id: complete
    class: postcondition
    expression: {facet: projection.done, operator: equals, value: true}
    evaluator: {id: eutaxis/manual-judgment, version: 1}
failures: [failed]
"""

MANIFEST = b"""\
_schema: eutaxis:declaration@1
id: projection/manifest
kind: composition-manifest
owner: projection
status: active
source-revision: fixture-1
applicability: {facet: projection.enabled, operator: equals, value: true}
relations: []
mechanism: cumulative
scope: project
target: AGENTS.md
sections:
  - id: rules
    declarations: [projection/all-modalities]
  - id: procedures
    declarations: [projection/branching-procedure]
policies: []
"""

RULE_SET_MANIFEST = b"""\
_schema: eutaxis:declaration@1
id: projection/rule-set-manifest
kind: composition-manifest
owner: projection
status: active
source-revision: fixture-1
applicability: {facet: projection.enabled, operator: equals, value: true}
relations: []
mechanism: cumulative
scope: project
target: AGENTS.md
sections:
  - id: rules
    declarations: [projection/strategic-rules]
policies: []
"""


def _plan(tmp_path: Path):
    manifest_path, lock_path = _write_contract(
        tmp_path,
        namespace="projection",
        declaration_files=(
            ("declarations/rule.yaml", RULE),
            ("declarations/operation.yaml", OPERATION),
            ("declarations/procedure.yaml", PROCEDURE),
            ("declarations/manifest.yaml", MANIFEST),
        ),
        facet_bytes=FACETS,
    )
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )
    resolution = resolve_external_compilation_unit(
        acquisition,
        "projection/manifest",
        {
            "context.available": True,
            "projection.enabled": True,
            "projection.optional": False,
            "projection.stable": True,
            "projection.done": False,
        },
    )
    return acquisition, plan_external_cumulative_composition(resolution)


def _plan_with_operation(tmp_path: Path, operation: bytes):
    manifest_path, lock_path = _write_contract(
        tmp_path,
        namespace="projection",
        declaration_files=(
            ("declarations/rule.yaml", RULE),
            ("declarations/operation.yaml", operation),
            ("declarations/procedure.yaml", PROCEDURE),
            ("declarations/manifest.yaml", MANIFEST),
        ),
        facet_bytes=FACETS,
    )
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )
    resolution = resolve_external_compilation_unit(
        acquisition,
        "projection/manifest",
        {
            "context.available": True,
            "projection.enabled": True,
            "projection.optional": False,
            "projection.stable": True,
            "projection.done": False,
        },
    )
    return plan_external_cumulative_composition(resolution)


def _rule_set_plan(tmp_path: Path):
    manifest_path, lock_path = _write_contract(
        tmp_path,
        namespace="projection",
        declaration_files=(
            ("declarations/rule-set.yaml", RULE_SET),
            ("declarations/manifest.yaml", RULE_SET_MANIFEST),
        ),
        facet_bytes=FACETS,
    )
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )
    resolution = resolve_external_compilation_unit(
        acquisition,
        "projection/rule-set-manifest",
        {
            "context.available": True,
            "projection.enabled": True,
            "projection.optional": False,
            "projection.stable": True,
            "projection.done": False,
        },
    )
    return plan_external_cumulative_composition(resolution)


def _plan_with_rule_identifier(tmp_path: Path, identifier: str):
    rule = RULE.replace(b"projection/all-modalities", identifier.encode())
    manifest = MANIFEST.replace(b"projection/all-modalities", identifier.encode())
    manifest_path, lock_path = _write_contract(
        tmp_path,
        namespace="projection",
        declaration_files=(
            ("declarations/rule.yaml", rule),
            ("declarations/operation.yaml", OPERATION),
            ("declarations/procedure.yaml", PROCEDURE),
            ("declarations/manifest.yaml", manifest),
        ),
        facet_bytes=FACETS,
    )
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )
    resolution = resolve_external_compilation_unit(
        acquisition,
        "projection/manifest",
        {
            "context.available": True,
            "projection.enabled": True,
            "projection.optional": False,
            "projection.stable": True,
            "projection.done": False,
        },
    )
    return plan_external_cumulative_composition(resolution)


def _collision_plan(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    (first / "declarations").mkdir(parents=True)
    (second / "declarations").mkdir(parents=True)
    shared_rule = RULE.replace(b"projection.enabled", b"context.available").replace(
        b"projection.optional", b"context.available"
    )
    (first / "declarations" / "rule.yaml").write_bytes(
        shared_rule.replace(b"projection/", b"first/").replace(
            b"owner: projection", b"owner: first"
        )
    )
    (second / "declarations" / "rule.yaml").write_bytes(
        shared_rule.replace(b"projection/", b"second/").replace(
            b"owner: projection", b"owner: second"
        )
    )
    (first / "declarations" / "manifest.yaml").write_bytes(b"""\
_schema: eutaxis:declaration@1
id: first/collision-manifest
kind: composition-manifest
owner: first
status: active
source-revision: fixture-1
applicability: {facet: context.available, operator: equals, value: true}
relations: []
mechanism: cumulative
scope: project
target: AGENTS.md
sections:
  - id: rules
    declarations: [first/all-modalities, second/all-modalities]
policies: []
""")
    acquisition_manifest = "acquisition.yaml"
    (tmp_path / acquisition_manifest).write_text(
        """\
schema-version: 1
facet-extensions: []
internal-source: {namespace: eutaxis, kind: packaged}
sources:
  - namespace: first
    kind: workspace
    root: first
    files: [declarations/rule.yaml, declarations/manifest.yaml]
  - namespace: second
    kind: workspace
    root: second
    files: [declarations/rule.yaml]
""",
        encoding="utf-8",
    )
    lock_path = "acquisition.lock.json"
    result = CliRunner().invoke(
        app,
        [
            "declarations",
            "lock",
            "--workspace",
            str(tmp_path),
            "--manifest",
            acquisition_manifest,
        ],
    )
    assert result.exit_code == 0, result.stderr
    (tmp_path / lock_path).write_bytes(result.stdout_bytes)
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), acquisition_manifest, lock_path
    )
    resolution = resolve_external_compilation_unit(
        acquisition,
        "first/collision-manifest",
        {"context.available": True},
    )
    return plan_external_cumulative_composition(resolution)


def test_complete_projection_matches_reviewed_golden(tmp_path: Path) -> None:
    _acquisition, plan = _plan(tmp_path)

    first = render_external_cumulative_markdown(plan)
    second = render_external_cumulative_markdown(plan)

    assert first.content == second.content == GOLDEN.read_bytes()
    assert "context-excluded" not in first.text
    assert "excluded-check" not in first.text
    assert "1. `finalize`" not in first.text
    assert "*Entry.* `choose`" in first.text
    assert '````"value ``` with backticks"````' in first.text


def test_agent_profile_uses_local_labels_and_omits_evaluator_metadata(
    tmp_path: Path,
) -> None:
    _acquisition, plan = _plan(tmp_path)

    artifact = render_external_cumulative_markdown(
        plan,
        profile=CumulativeMarkdownProfile.AGENT_INSTRUCTIONS,
    )

    assert "**all-modalities**:" in artifact.text
    assert "**branching-procedure**:" in artifact.text
    assert "*Kind.* Procedure." in artifact.text
    assert parse_module(artifact.text, module="projected").rule(
        "branching-procedure"
    ) is not None
    assert "projection/all-modalities" not in artifact.text
    assert "*Success criteria.*" not in artifact.text
    assert "[eutaxis/manual-judgment@1]" not in artifact.text
    assert "✓ Agent MUST retain every required field before rendering." in artifact.text


def test_agent_profile_renders_closed_rule_exceptions(tmp_path: Path) -> None:
    rule_set = RULE_SET.replace(
        b"    criteria:\n",
        b"    exceptions:\n"
        b"      - id: frame-exception\n"
        b"        when: {facet: projection.optional, operator: equals, value: false}\n"
        b"        disposition: waive\n"
        b"        affects: [preserve-frame]\n"
        b"        rationale: The optional frame is intentionally absent\n"
        b"    criteria:\n",
    )
    manifest_path, lock_path = _write_contract(
        tmp_path,
        namespace="projection",
        declaration_files=(
            ("declarations/rule-set.yaml", rule_set),
            ("declarations/manifest.yaml", RULE_SET_MANIFEST),
        ),
        facet_bytes=FACETS,
    )
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )
    resolution = resolve_external_compilation_unit(
        acquisition,
        "projection/rule-set-manifest",
        {
            "context.available": True,
            "projection.enabled": True,
            "projection.optional": False,
            "projection.stable": True,
            "projection.done": False,
        },
    )
    artifact = render_external_cumulative_markdown(
        plan_external_cumulative_composition(resolution),
        profile=CumulativeMarkdownProfile.AGENT_INSTRUCTIONS,
    )

    assert "*Exception.* `frame-exception`:" in artifact.text
    assert (
        'When `{"facet":"projection.optional","operator":"equals","value":false}`'
        in artifact.text
    )
    assert (
        "- `preserve-frame`: Agent MUST preserve the rule-set frame."
        in artifact.text
    )
    assert artifact.text.count("Agent MUST preserve the rule-set frame.") == 1
    assert "The optional frame is intentionally absent" in artifact.text


def test_agent_profile_renders_active_substitute_exception(tmp_path: Path) -> None:
    rule_set = RULE_SET.replace(
        b"    criteria:\n",
        b"      - id: preserve-substitute\n"
        b"        modality: must\n"
        b"        subject: agent\n"
        b"        action: {verb: retain, object: the substitute frame}\n"
        b"    exceptions:\n"
        b"      - id: substitute-frame\n"
        b"        when: {facet: projection.optional, operator: equals, value: false}\n"
        b"        disposition: substitute\n"
        b"        affects: [preserve-frame]\n"
        b"        substitutes: [preserve-substitute]\n"
        b"    criteria:\n",
    )
    manifest_path, lock_path = _write_contract(
        tmp_path,
        namespace="projection",
        declaration_files=(
            ("declarations/rule-set.yaml", rule_set),
            ("declarations/manifest.yaml", RULE_SET_MANIFEST),
        ),
        facet_bytes=FACETS,
    )
    acquisition = acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )
    resolution = resolve_external_compilation_unit(
        acquisition,
        "projection/rule-set-manifest",
        {
            "context.available": True,
            "projection.enabled": True,
            "projection.optional": False,
            "projection.stable": True,
            "projection.done": False,
        },
    )
    artifact = render_external_cumulative_markdown(
        plan_external_cumulative_composition(resolution),
        profile=CumulativeMarkdownProfile.AGENT_INSTRUCTIONS,
    )

    assert "*Exception.* `substitute-frame`:" in artifact.text
    assert (
        "- `preserve-frame`: Agent MUST preserve the rule-set frame."
        in artifact.text
    )
    assert (
        "With:\n- `preserve-substitute`: Agent MUST retain the substitute frame."
        in artifact.text
    )
    assert artifact.text.count("Agent MUST preserve the rule-set frame.") == 1
    assert artifact.text.count("Agent MUST retain the substitute frame.") == 2


def test_agent_profile_renders_containing_rule_set_once(tmp_path: Path) -> None:
    artifact = render_external_cumulative_markdown(
        _rule_set_plan(tmp_path),
        profile=CumulativeMarkdownProfile.AGENT_INSTRUCTIONS,
    )

    assert artifact.text.count("# Strategic rules") == 1
    assert artifact.text.count("These rules govern every projected artifact") == 1
    assert artifact.text.count("*Why.* The frame states") == 1
    assert "**framed-rule**:" in artifact.text


def test_default_profile_does_not_add_rule_set_frame(tmp_path: Path) -> None:
    artifact = render_external_cumulative_markdown(_rule_set_plan(tmp_path))

    assert "strategic-rules" not in artifact.text
    assert artifact.text.startswith("**projection/framed-rule**:")


def test_agent_profile_rejects_digit_leading_local_label(tmp_path: Path) -> None:
    plan = _plan_with_rule_identifier(tmp_path, "projection/1-rule")

    with pytest.raises(CompositionError, match="has no valid agent label"):
        render_external_cumulative_markdown(
            plan,
            profile=CumulativeMarkdownProfile.AGENT_INSTRUCTIONS,
        )


def test_profile_rejects_untyped_string(tmp_path: Path) -> None:
    _acquisition, plan = _plan(tmp_path)

    with pytest.raises(CompositionError, match="must be a CumulativeMarkdownProfile"):
        render_external_cumulative_markdown(
            plan,
            profile="agent-instructions",  # type: ignore[arg-type]
        )


def test_agent_profile_rejects_colliding_local_labels(tmp_path: Path) -> None:
    plan = _collision_plan(tmp_path)

    with pytest.raises(CompositionError, match="projected label 'all-modalities'"):
        render_external_cumulative_markdown(
            plan,
            profile=CumulativeMarkdownProfile.AGENT_INSTRUCTIONS,
        )


def test_cumulative_projection_rejects_operation_support_resources(
    tmp_path: Path,
) -> None:
    operation = OPERATION.replace(
        b"effects: [projection/artifact]",
        b"support-resources:\n"
        b"  - resource: projection/helper\n"
        b"    destination: scripts/helper.py\n"
        b"effects: [projection/artifact]",
    )
    plan = _plan_with_operation(tmp_path, operation)

    with pytest.raises(CompositionError, match="cumulative Markdown cannot carry"):
        render_external_cumulative_markdown(plan)


def test_catalog_retirement_after_projection_blocks_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _acquisition, plan = _plan(tmp_path)
    original = external_composition_module._render_cumulative_markdown

    def hostile_render(catalog, unit, internal_plan, profile):
        artifact = original(catalog, unit, internal_plan, profile)
        _CATALOG_AUTHORITIES.retire(catalog)
        return artifact

    monkeypatch.setattr(
        external_composition_module,
        "_render_cumulative_markdown",
        hostile_render,
    )

    with pytest.raises(DeclarationCatalogError, match="not issued"):
        render_external_cumulative_markdown(plan)
