"""Validate whether rule-bearing content may compile into an Agent Skill."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from typing import Literal, cast

FailureMode = Literal["silent", "visible"]
RequiredVisibility = Literal["pre-invocation", "pre-action"] | None
InvocationRoute = Literal["model", "user"]

_FAILURE_MODES = frozenset({"silent", "visible"})
_REQUIRED_VISIBILITIES = frozenset({"pre-invocation", "pre-action"})
_INVOCATION_ROUTES = frozenset({"model", "user"})


class SkillPlacementError(Exception):
    """Report content that cannot use the requested Skill invocation routes."""

    exit_code = 1


@dataclass(frozen=True, init=False)
class SkillPlacementCandidate:
    """Describe one classified content unit and its authored source."""

    identifier: str
    source: str
    failure_mode: FailureMode
    required_visibility: RequiredVisibility

    def __init__(
        self,
        *,
        identifier: str,
        source: str,
        failure_mode: str,
        required_visibility: str | None,
    ) -> None:
        """Validate and retain one authored placement classification."""
        _validate_candidate_fields(
            identifier,
            source,
            failure_mode,
            required_visibility,
        )
        object.__setattr__(self, "identifier", identifier)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "failure_mode", cast(FailureMode, failure_mode))
        object.__setattr__(
            self,
            "required_visibility",
            cast(RequiredVisibility, required_visibility),
        )


def validate_skill_placement(
    candidates: Iterable[SkillPlacementCandidate],
    invocation: Collection[str],
) -> None:
    """Require every candidate to satisfy the Skill placement matrix.

    Parameters
    ----------
    candidates
        Classified content units considered for one Skill.
    invocation
        Invocation routes admitted by that Skill.

    Raises
    ------
    SkillPlacementError
        If one candidate must remain always loaded or cannot admit model
        invocation.
    """
    invocation_routes = _validate_invocation(invocation)
    for candidate in candidates:
        _validate_candidate_fields(
            candidate.identifier,
            candidate.source,
            candidate.failure_mode,
            candidate.required_visibility,
        )
        if candidate.failure_mode != "silent":
            continue
        location = _candidate_location(candidate)
        if candidate.required_visibility == "pre-invocation":
            raise SkillPlacementError(
                "Refusing to emit any skill from silent-failure content whose "
                f"required-visibility is 'pre-invocation': {location}. The "
                "content must remain always loaded. See ADR "
                "failure-mode-as-source-field."
            )
        if "model" in invocation_routes:
            raise SkillPlacementError(
                "Refusing to emit a skill that admits model invocation from "
                f"silent-failure content {location}. Remove 'model' from "
                "`invocation`, keep the content always loaded, or classify it "
                "as visible-failure. See ADR failure-mode-as-source-field."
            )


def _validate_invocation(invocation: Collection[str]) -> frozenset[InvocationRoute]:
    """Return the closed, non-empty set of admitted invocation routes."""
    routes = frozenset(invocation)
    if not routes:
        raise SkillPlacementError("Skill invocation must contain at least one route")
    if len(invocation) != len(routes):
        raise SkillPlacementError("Skill invocation routes must be unique")
    unknown = routes - _INVOCATION_ROUTES
    if unknown:
        raise SkillPlacementError(
            f"unknown Skill invocation route {min(unknown)!r}; expected 'model' or 'user'"
        )
    return cast(frozenset[InvocationRoute], routes)


def _validate_candidate_fields(
    identifier: str,
    source: str,
    failure_mode: str,
    required_visibility: str | None,
) -> None:
    """Require one candidate to use the closed classification vocabulary."""
    location = f"{identifier!r} at {source}"
    if failure_mode not in _FAILURE_MODES:
        raise SkillPlacementError(
            f"Skill placement candidate {location} has unknown failure mode "
            f"{failure_mode!r}"
        )
    if failure_mode == "silent" and required_visibility not in _REQUIRED_VISIBILITIES:
        raise SkillPlacementError(
            f"silent-failure content {location} requires 'pre-invocation' or "
            "'pre-action' visibility"
        )
    if failure_mode == "visible" and required_visibility is not None:
        raise SkillPlacementError(
            f"visible-failure content {location} cannot declare required visibility"
        )


def _candidate_location(candidate: SkillPlacementCandidate) -> str:
    """Return one diagnostic label containing identity and source."""
    return f"{candidate.identifier!r} at {candidate.source}"
