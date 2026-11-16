"""Tests for the dependency-neutral Skill placement matrix."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from eutaxis.skill_placement import (
    SkillPlacementCandidate,
    SkillPlacementError,
    validate_skill_placement,
)


def _candidate(
    identifier: str,
    *,
    failure_mode: str,
    required_visibility: str | None = None,
) -> SkillPlacementCandidate:
    return SkillPlacementCandidate(
        identifier=identifier,
        source=f"declarations/{identifier}.yaml",
        failure_mode=failure_mode,
        required_visibility=required_visibility,
    )


@pytest.mark.parametrize(
    "invocation",
    [("user",), ("model",), ("model", "user")],
)
def test_visible_content_admits_every_invocation_route(
    invocation: tuple[str, ...],
) -> None:
    validate_skill_placement(
        (_candidate("visible", failure_mode="visible"),),
        invocation,
    )


def test_silent_pre_action_content_admits_user_only() -> None:
    validate_skill_placement(
        (
            _candidate(
                "silent-pre-action",
                failure_mode="silent",
                required_visibility="pre-action",
            ),
        ),
        ("user",),
    )


@pytest.mark.parametrize("invocation", [("model",), ("model", "user")])
def test_silent_content_rejects_model_invocation(
    invocation: tuple[str, ...],
) -> None:
    candidate = _candidate(
        "silent-model",
        failure_mode="silent",
        required_visibility="pre-action",
    )
    with pytest.raises(SkillPlacementError) as exc_info:
        validate_skill_placement((candidate,), invocation)
    message = str(exc_info.value)
    assert "model invocation" in message
    assert "'silent-model'" in message
    assert "declarations/silent-model.yaml" in message


@pytest.mark.parametrize("invocation", [("user",), ("model",), ("model", "user")])
def test_pre_invocation_content_rejects_every_skill_route(
    invocation: tuple[str, ...],
) -> None:
    candidate = _candidate(
        "pre-invocation",
        failure_mode="silent",
        required_visibility="pre-invocation",
    )
    with pytest.raises(SkillPlacementError) as exc_info:
        validate_skill_placement((candidate,), invocation)
    message = str(exc_info.value)
    assert "pre-invocation" in message
    assert "'pre-invocation'" in message
    assert "declarations/pre-invocation.yaml" in message


def test_one_forbidden_member_rejects_a_mixed_set() -> None:
    candidates = (
        _candidate("visible", failure_mode="visible"),
        _candidate(
            "forbidden",
            failure_mode="silent",
            required_visibility="pre-action",
        ),
        _candidate("unreached", failure_mode="visible"),
    )
    with pytest.raises(
        SkillPlacementError,
        match=r"forbidden.*declarations/forbidden\.yaml",
    ):
        validate_skill_placement(candidates, ("model", "user"))


def test_candidate_generator_is_consumed_once() -> None:
    expected = (
        _candidate("first", failure_mode="visible"),
        _candidate("second", failure_mode="visible"),
    )

    class SinglePassCandidates:
        def __init__(self) -> None:
            self.iterations = 0

        def __iter__(self) -> Iterator[SkillPlacementCandidate]:
            self.iterations += 1
            if self.iterations > 1:
                raise AssertionError("candidate iterable was consumed twice")
            return iter(expected)

    candidates = SinglePassCandidates()
    validate_skill_placement(candidates, ("model",))
    assert candidates.iterations == 1


@pytest.mark.parametrize("failure_mode", ["", "mixed", "VISIBLE"])
def test_candidate_rejects_unknown_failure_mode(failure_mode: str) -> None:
    with pytest.raises(SkillPlacementError, match="unknown failure mode"):
        _candidate("invalid", failure_mode=failure_mode)


@pytest.mark.parametrize("required_visibility", [None, "", "eventual"])
def test_silent_candidate_requires_closed_visibility(
    required_visibility: str | None,
) -> None:
    with pytest.raises(SkillPlacementError, match="requires.*visibility"):
        _candidate(
            "invalid-silent",
            failure_mode="silent",
            required_visibility=required_visibility,
        )


@pytest.mark.parametrize("required_visibility", ["pre-action", "pre-invocation"])
def test_visible_candidate_rejects_required_visibility(
    required_visibility: str,
) -> None:
    with pytest.raises(SkillPlacementError, match="cannot declare"):
        _candidate(
            "invalid-visible",
            failure_mode="visible",
            required_visibility=required_visibility,
        )


@pytest.mark.parametrize("invocation", [(), ("automatic",), ("model", "other")])
def test_validator_rejects_invalid_invocation_routes(
    invocation: tuple[str, ...],
) -> None:
    candidate = _candidate("visible", failure_mode="visible")
    with pytest.raises(SkillPlacementError):
        validate_skill_placement((candidate,), invocation)


@pytest.mark.parametrize("invocation", [("user", "user"), ("model", "model")])
def test_validator_rejects_duplicate_invocation_routes(
    invocation: tuple[str, ...],
) -> None:
    candidate = _candidate("visible", failure_mode="visible")
    with pytest.raises(SkillPlacementError, match="must be unique"):
        validate_skill_placement((candidate,), invocation)
