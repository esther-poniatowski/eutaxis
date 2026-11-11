"""Golden and authority tests for cumulative Markdown projection."""

from __future__ import annotations

from pathlib import Path

import pytest

import eutaxis.declarations.external_composition as external_composition_module
from eutaxis.declarations import (
    CompositionError,
    DeclarationCatalogError,
    acquire_external_declarations_from_path,
    plan_external_cumulative_composition,
    render_external_cumulative_markdown,
    resolve_external_compilation_unit,
)
from eutaxis.declarations.catalog import _CATALOG_AUTHORITIES
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

    def hostile_render(catalog, unit, internal_plan):
        artifact = original(catalog, unit, internal_plan)
        _CATALOG_AUTHORITIES.retire(catalog)
        return artifact

    monkeypatch.setattr(
        external_composition_module,
        "_render_cumulative_markdown",
        hostile_render,
    )

    with pytest.raises(DeclarationCatalogError, match="not issued"):
        render_external_cumulative_markdown(plan)
