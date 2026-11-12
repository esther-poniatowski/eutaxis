"""Resolution tests for authenticated external declaration results."""

from __future__ import annotations

import copy
import pickle
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

import eutaxis.declarations.external_composition as external_composition_module
import eutaxis.declarations.external_resolution as external_resolution_module
from eutaxis.declarations import (
    CumulativeMarkdownProfile,
    AcquisitionContractError,
    ExternalCumulativeArtifact,
    ExternalCumulativeCompositionPlan,
    ExternalResolutionResult,
    acquire_external_declarations_from_path,
    assemble_external_cumulative_artifact,
    plan_external_cumulative_composition,
    render_external_cumulative_markdown,
    resolve_external_compilation_unit,
)
from eutaxis.declarations.external_result import _retire_external_result_tree
from eutaxis.declarations.resolution import _is_issued_resolution_result
from tests.test_external_acquisition import _write_contract

RULE = b"""\
_schema: eutaxis:declaration@1
id: resolution/purpose
kind: rule
owner: resolution
status: active
source-revision: fixture-1
applicability: {facet: resolution.enabled, operator: equals, value: true}
relations: []
axis: reasoning-target
failure-mode: visible
norms:
  - id: state-purpose
    modality: must
    subject: agent
    action: {verb: state, object: the reader-facing purpose}
criteria:
  - id: purpose-is-explicit
    norms: [state-purpose]
    evaluator: {id: eutaxis/manual-judgment, version: 1}
    statement: The artifact states a reader-facing purpose
"""

MANIFEST = b"""\
_schema: eutaxis:declaration@1
id: resolution/manifest
kind: composition-manifest
owner: resolution
status: active
source-revision: fixture-1
applicability: {facet: resolution.enabled, operator: equals, value: true}
relations: []
mechanism: cumulative
scope: project
target: AGENTS.md
sections:
  - id: core
    declarations: [resolution/purpose]
policies: []
"""


def _acquire(tmp_path: Path):
    declaration_files = (
        ("declarations/rule.yaml", RULE),
        ("declarations/manifest.yaml", MANIFEST),
    )
    manifest_path, lock_path = _write_contract(
        tmp_path,
        namespace="resolution",
        declaration_files=declaration_files,
    )
    return acquire_external_declarations_from_path(
        str(tmp_path), manifest_path, lock_path
    )


def _context() -> dict[str, object]:
    return {
        "context.available": True,
        "resolution.enabled": True,
    }


def _pipeline(tmp_path: Path):
    acquisition = _acquire(tmp_path)
    resolution = resolve_external_compilation_unit(
        acquisition, "resolution/manifest", _context()
    )
    plan = plan_external_cumulative_composition(resolution)
    artifact = assemble_external_cumulative_artifact(
        plan,
        {"resolution/purpose": "State the reader-facing purpose."},
    )
    return acquisition, resolution, plan, artifact


class _RetiringMapping(Mapping[str, object]):
    def __init__(self, values, retire) -> None:
        self._values = values
        self._retire = retire
        self._retired = False

    def __iter__(self) -> Iterator[str]:
        if not self._retired:
            self._retired = True
            self._retire()
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __getitem__(self, key: str) -> object:
        return self._values[key]


def test_resolves_an_authenticated_external_corpus(tmp_path: Path) -> None:
    result = _acquire(tmp_path)

    resolved = resolve_external_compilation_unit(
        result, "resolution/manifest", _context()
    )

    assert tuple(component.declaration for component in resolved.unit.components) == (
        "resolution/purpose",
    )
    assert not hasattr(resolved, "registry")
    assert not hasattr(resolved, "_external_result_state")


def test_resolution_remains_bound_to_acquisition_authority(tmp_path: Path) -> None:
    result = _acquire(tmp_path)
    resolved = resolve_external_compilation_unit(
        result, "resolution/manifest", _context()
    )

    _retire_external_result_tree(result)

    with pytest.raises(AcquisitionContractError, match="not issued"):
        _ = resolved.unit


def test_rejects_nonissued_acquisition_result() -> None:
    with pytest.raises(AcquisitionContractError, match="not issued"):
        resolve_external_compilation_unit(object(), "resolution/manifest", _context())


def test_post_resolution_authority_failure_retires_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _acquire(tmp_path)
    captured = []
    original = external_resolution_module.resolve_compilation_unit

    def hostile_resolve(registry, manifest_id, context):
        resolved = original(registry, manifest_id, context)
        captured.append(resolved)
        _retire_external_result_tree(result)
        return resolved

    monkeypatch.setattr(
        external_resolution_module,
        "resolve_compilation_unit",
        hostile_resolve,
    )

    with pytest.raises(AcquisitionContractError, match="not issued"):
        resolve_external_compilation_unit(result, "resolution/manifest", _context())

    assert len(captured) == 1
    assert not _is_issued_resolution_result(captured[0])


def test_external_composition_stays_bound_through_artifact(
    tmp_path: Path,
) -> None:
    acquisition = _acquire(tmp_path)
    resolution = resolve_external_compilation_unit(
        acquisition, "resolution/manifest", _context()
    )
    plan = plan_external_cumulative_composition(resolution)
    artifact = assemble_external_cumulative_artifact(
        plan,
        {"resolution/purpose": "State the reader-facing purpose."},
    )

    assert tuple(component.declaration for component in plan.components) == (
        "resolution/purpose",
    )
    assert artifact.text == "State the reader-facing purpose.\n"
    assert not hasattr(plan, "registry")
    assert not hasattr(plan, "plan")

    _retire_external_result_tree(acquisition)

    for operation in (
        lambda: resolution.unit,
        lambda: plan.components,
        lambda: artifact.content,
    ):
        with pytest.raises(AcquisitionContractError, match="not issued"):
            operation()


def test_renders_external_cumulative_markdown_from_catalog(tmp_path: Path) -> None:
    acquisition = _acquire(tmp_path)
    resolution = resolve_external_compilation_unit(
        acquisition, "resolution/manifest", _context()
    )
    plan = plan_external_cumulative_composition(resolution)

    artifact = render_external_cumulative_markdown(plan)

    assert artifact.text == (
        "**resolution/purpose**:\n\n"
        "✓ `state-purpose`: Agent MUST state the reader-facing purpose.\n\n"
        "*Success criteria.*\n"
        "- `purpose-is-explicit` [eutaxis/manual-judgment@1]: "
        "The artifact states a reader-facing purpose\n"
    )


def test_renders_bounded_agent_instruction_markdown(tmp_path: Path) -> None:
    acquisition = _acquire(tmp_path)
    resolution = resolve_external_compilation_unit(
        acquisition, "resolution/manifest", _context()
    )
    plan = plan_external_cumulative_composition(resolution)

    artifact = render_external_cumulative_markdown(
        plan,
        profile=CumulativeMarkdownProfile.AGENT_INSTRUCTIONS,
    )

    assert artifact.text == (
        "**purpose**:\n\n" "✓ Agent MUST state the reader-facing purpose.\n"
    )


def test_rendered_markdown_remains_bound_to_acquisition(tmp_path: Path) -> None:
    acquisition = _acquire(tmp_path)
    resolution = resolve_external_compilation_unit(
        acquisition, "resolution/manifest", _context()
    )
    plan = plan_external_cumulative_composition(resolution)
    artifact = render_external_cumulative_markdown(plan)

    _retire_external_result_tree(acquisition)

    with pytest.raises(AcquisitionContractError, match="not issued"):
        _ = artifact.text


def test_external_capabilities_reject_copy_and_serialization(tmp_path: Path) -> None:
    _acquisition, resolution, plan, artifact = _pipeline(tmp_path)

    for capability in (resolution, plan, artifact):
        for operation in (
            lambda value=capability: copy.copy(value),
            lambda value=capability: copy.deepcopy(value),
            lambda value=capability: pickle.dumps(value),
        ):
            with pytest.raises(TypeError, match="cannot be (copied|serialized)"):
                operation()


def test_external_capabilities_reject_subclassing() -> None:
    for capability_type in (
        ExternalResolutionResult,
        ExternalCumulativeCompositionPlan,
        ExternalCumulativeArtifact,
    ):
        with pytest.raises(TypeError, match="cannot be subclassed"):
            type("Derived", (capability_type,), {})


def test_equal_state_reissue_cannot_self_attest(tmp_path: Path) -> None:
    pipelines = [_pipeline(tmp_path / str(index)) for index in range(3)]
    cases = (
        (
            pipelines[0][1],
            external_resolution_module._EXTERNAL_RESOLUTION_AUTHORITIES,
            lambda value: value.unit,
        ),
        (
            pipelines[1][2],
            external_composition_module._EXTERNAL_PLAN_AUTHORITIES,
            lambda value: value.components,
        ),
        (
            pipelines[2][3],
            external_composition_module._EXTERNAL_ARTIFACT_AUTHORITIES,
            lambda value: value.content,
        ),
    )
    for capability, store, read in cases:
        state = store.retire(capability)
        assert state is not None
        equal_state = type(state)(*state)
        store.issue(capability, equal_state)
        with pytest.raises(AcquisitionContractError, match="not issued"):
            read(capability)


def test_cross_result_state_substitution_fails(tmp_path: Path) -> None:
    first = _pipeline(tmp_path / "first")
    second = _pipeline(tmp_path / "second")
    cases = (
        (
            first[1],
            second[1],
            external_resolution_module._EXTERNAL_RESOLUTION_AUTHORITIES,
            lambda value: value.unit,
        ),
        (
            first[2],
            second[2],
            external_composition_module._EXTERNAL_PLAN_AUTHORITIES,
            lambda value: value.components,
        ),
        (
            first[3],
            second[3],
            external_composition_module._EXTERNAL_ARTIFACT_AUTHORITIES,
            lambda value: value.content,
        ),
    )
    for target, source, store, read in cases:
        assert store.retire(target) is not None
        foreign_state = store.state(source)
        assert foreign_state is not None
        store.issue(target, foreign_state)
        with pytest.raises(AcquisitionContractError, match="not issued"):
            read(target)
        read(source)


def test_equal_owner_state_reissue_cannot_self_attest(tmp_path: Path) -> None:
    _acquisition, resolution, _plan, _artifact = _pipeline(tmp_path)
    store = external_resolution_module._EXTERNAL_RESOLUTION_OWNERS
    state = store.retire(resolution)
    assert state is not None
    store.issue(resolution, tuple(state))

    with pytest.raises(AcquisitionContractError, match="owner changed"):
        _ = resolution.unit


def test_foreign_owner_state_rejection_preserves_source(tmp_path: Path) -> None:
    first = _pipeline(tmp_path / "first")
    second = _pipeline(tmp_path / "second")
    target = first[1]
    source = second[1]
    store = external_resolution_module._EXTERNAL_RESOLUTION_OWNERS
    assert store.retire(target) is not None
    foreign_state = store.state(source)
    assert foreign_state is not None
    store.issue(target, foreign_state)

    with pytest.raises(AcquisitionContractError, match="owner changed"):
        _ = target.unit
    _ = source.unit


def test_internal_state_mutation_invalidates_each_capability(tmp_path: Path) -> None:
    pipelines = [_pipeline(tmp_path / str(index)) for index in range(3)]

    resolution = pipelines[0][1]
    resolution_state = (
        external_resolution_module._EXTERNAL_RESOLUTION_AUTHORITIES.state(resolution)
    )
    object.__setattr__(resolution_state.resolution.unit, "manifest", "changed")
    with pytest.raises(AcquisitionContractError, match="authority changed"):
        _ = resolution.unit

    plan = pipelines[1][2]
    plan_state = external_composition_module._EXTERNAL_PLAN_AUTHORITIES.state(plan)
    object.__setattr__(plan_state.plan, "target", "changed")
    with pytest.raises(AcquisitionContractError, match="plan state changed"):
        _ = plan.target

    artifact = pipelines[2][3]
    artifact_state = external_composition_module._EXTERNAL_ARTIFACT_AUTHORITIES.state(
        artifact
    )
    object.__setattr__(artifact_state.artifact, "content", b"changed")
    with pytest.raises(AcquisitionContractError, match="artifact state changed"):
        _ = artifact.content


def test_token_mutation_cannot_self_attest(tmp_path: Path) -> None:
    pipelines = [_pipeline(tmp_path / str(index)) for index in range(3)]
    cases = (
        (pipelines[0][1], lambda value: value.unit),
        (pipelines[1][2], lambda value: value.components),
        (pipelines[2][3], lambda value: value.content),
    )
    for capability, read in cases:
        object.__setattr__(capability, "_token", object())
        with pytest.raises(AcquisitionContractError, match="not issued"):
            read(capability)


def test_context_callback_retirement_has_authority_priority(tmp_path: Path) -> None:
    acquisition = _acquire(tmp_path)
    context = _RetiringMapping(
        _context(), lambda: _retire_external_result_tree(acquisition)
    )

    with pytest.raises(AcquisitionContractError, match="not issued"):
        resolve_external_compilation_unit(acquisition, "resolution/manifest", context)


def test_fragment_callback_retirement_has_authority_priority(tmp_path: Path) -> None:
    acquisition, _resolution, plan, _artifact = _pipeline(tmp_path)
    fragments = _RetiringMapping(
        {"resolution/purpose": "State the reader-facing purpose."},
        lambda: _retire_external_result_tree(acquisition),
    )

    with pytest.raises(AcquisitionContractError, match="not issued"):
        assemble_external_cumulative_artifact(plan, fragments)


def test_resolution_publication_race_preserves_authority_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquisition = _acquire(tmp_path)
    original = external_resolution_module._issue_external_resolution

    def retire_then_issue(*args):
        _retire_external_result_tree(acquisition)
        return original(*args)

    monkeypatch.setattr(
        external_resolution_module,
        "_issue_external_resolution",
        retire_then_issue,
    )

    with pytest.raises(AcquisitionContractError, match="not issued"):
        resolve_external_compilation_unit(
            acquisition, "resolution/manifest", _context()
        )


def test_plan_publication_race_preserves_authority_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquisition = _acquire(tmp_path)
    resolution = resolve_external_compilation_unit(
        acquisition, "resolution/manifest", _context()
    )
    original = external_composition_module._issue_external_plan

    def retire_then_issue(*args):
        _retire_external_result_tree(acquisition)
        return original(*args)

    monkeypatch.setattr(
        external_composition_module,
        "_issue_external_plan",
        retire_then_issue,
    )

    with pytest.raises(AcquisitionContractError, match="not issued"):
        plan_external_cumulative_composition(resolution)


def test_artifact_publication_race_preserves_authority_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquisition = _acquire(tmp_path)
    resolution = resolve_external_compilation_unit(
        acquisition, "resolution/manifest", _context()
    )
    plan = plan_external_cumulative_composition(resolution)
    original = external_composition_module._issue_external_artifact

    def retire_then_issue(*args):
        _retire_external_result_tree(acquisition)
        return original(*args)

    monkeypatch.setattr(
        external_composition_module,
        "_issue_external_artifact",
        retire_then_issue,
    )

    with pytest.raises(AcquisitionContractError, match="not issued"):
        assemble_external_cumulative_artifact(
            plan,
            {"resolution/purpose": "State the reader-facing purpose."},
        )


def test_resolution_store_interruption_retires_all_issued_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquisition = _acquire(tmp_path)
    store = external_resolution_module._EXTERNAL_RESOLUTION_AUTHORITIES
    original = store.issue
    captured = []

    def interrupt(aggregate, state):
        captured.append((aggregate, state))
        original(aggregate, state)
        raise KeyboardInterrupt

    monkeypatch.setattr(store, "issue", interrupt)

    with pytest.raises(KeyboardInterrupt):
        resolve_external_compilation_unit(
            acquisition, "resolution/manifest", _context()
        )

    assert len(captured) == 1
    aggregate, state = captured[0]
    assert store.lookup(aggregate) is None
    assert not _is_issued_resolution_result(state.resolution)


def test_plan_store_interruption_retires_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _acquisition, resolution, _plan, _artifact = _pipeline(tmp_path)
    store = external_composition_module._EXTERNAL_PLAN_AUTHORITIES
    original = store.issue
    captured = []

    def interrupt(aggregate, state):
        captured.append(aggregate)
        original(aggregate, state)
        raise KeyboardInterrupt

    monkeypatch.setattr(store, "issue", interrupt)

    with pytest.raises(KeyboardInterrupt):
        plan_external_cumulative_composition(resolution)

    assert len(captured) == 1
    assert store.lookup(captured[0]) is None


def test_artifact_store_interruption_retires_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _acquisition, _resolution, plan, _artifact = _pipeline(tmp_path)
    store = external_composition_module._EXTERNAL_ARTIFACT_AUTHORITIES
    original = store.issue
    captured = []

    def interrupt(aggregate, state):
        captured.append(aggregate)
        original(aggregate, state)
        raise KeyboardInterrupt

    monkeypatch.setattr(store, "issue", interrupt)

    with pytest.raises(KeyboardInterrupt):
        assemble_external_cumulative_artifact(
            plan,
            {"resolution/purpose": "State the reader-facing purpose."},
        )

    assert len(captured) == 1
    assert store.lookup(captured[0]) is None


@pytest.mark.parametrize(
    "constructor",
    [
        ExternalResolutionResult,
        ExternalCumulativeCompositionPlan,
        ExternalCumulativeArtifact,
    ],
)
def test_external_capabilities_require_issuance(constructor) -> None:
    with pytest.raises(TypeError, match="must be issued"):
        constructor()
