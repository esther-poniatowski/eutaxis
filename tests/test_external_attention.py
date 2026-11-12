"""Exercise enforcement planning across the authenticated external boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

import eutaxis.declarations.external_attention as external_attention_module
from eutaxis.declarations import (
    AcquisitionContractError,
    ExternalAttentionRequirements,
    derive_external_attention_requirements,
    resolve_external_compilation_unit,
)
from eutaxis.declarations.external_result import _retire_external_result_tree
from tests.test_external_resolution import _acquire, _context


def _derive(tmp_path: Path):
    acquisition = _acquire(tmp_path)
    resolution = resolve_external_compilation_unit(
        acquisition,
        "resolution/manifest",
        _context(),
    )
    return acquisition, resolution, derive_external_attention_requirements(resolution)


def test_derives_external_requirements_without_exposing_the_registry(
    tmp_path: Path,
) -> None:
    _acquisition, _resolution, requirements = _derive(tmp_path)

    assert len(requirements.completion) == 1
    assert len(requirements.deliberative) == 1
    assert requirements.assisted == ()
    assert requirements.mechanical == ()
    assert not hasattr(requirements, "resolution")
    assert not hasattr(requirements, "registry")
    assert not hasattr(requirements, "requirements")


def test_external_requirements_remain_bound_to_acquisition_authority(
    tmp_path: Path,
) -> None:
    acquisition, _resolution, requirements = _derive(tmp_path)

    _retire_external_result_tree(acquisition)

    with pytest.raises(AcquisitionContractError, match="not issued"):
        _ = requirements.completion


def test_external_requirements_reject_internal_state_change(tmp_path: Path) -> None:
    _acquisition, _resolution, requirements = _derive(tmp_path)
    state = external_attention_module._EXTERNAL_ATTENTION_AUTHORITIES.lookup(
        requirements
    )
    assert state is not None
    internal = state[1].requirements
    object.__setattr__(internal, "completion", ())

    with pytest.raises(AcquisitionContractError, match="state changed"):
        _ = requirements.completion


def test_rejects_nonissued_external_resolution() -> None:
    with pytest.raises(AcquisitionContractError, match="not issued"):
        derive_external_attention_requirements(object())  # type: ignore[arg-type]


def test_derivation_race_preserves_external_authority_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquisition = _acquire(tmp_path)
    resolution = resolve_external_compilation_unit(
        acquisition,
        "resolution/manifest",
        _context(),
    )
    original = external_attention_module.derive_attention_requirements

    def retire_after_derivation(*args, **kwargs):
        requirements = original(*args, **kwargs)
        _retire_external_result_tree(acquisition)
        return requirements

    monkeypatch.setattr(
        external_attention_module,
        "derive_attention_requirements",
        retire_after_derivation,
    )

    with pytest.raises(AcquisitionContractError, match="not issued"):
        derive_external_attention_requirements(resolution)


def test_external_requirement_store_interruption_retires_wrapper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquisition = _acquire(tmp_path)
    resolution = resolve_external_compilation_unit(
        acquisition,
        "resolution/manifest",
        _context(),
    )
    store = external_attention_module._EXTERNAL_ATTENTION_AUTHORITIES
    original = store.issue
    captured = []

    def interrupt(aggregate, state):
        captured.append(aggregate)
        original(aggregate, state)
        raise KeyboardInterrupt

    monkeypatch.setattr(store, "issue", interrupt)

    with pytest.raises(KeyboardInterrupt):
        derive_external_attention_requirements(resolution)

    assert len(captured) == 1
    assert store.lookup(captured[0]) is None


def test_external_requirement_capability_requires_issuance() -> None:
    with pytest.raises(TypeError, match="must be issued"):
        ExternalAttentionRequirements()
