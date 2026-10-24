"""Immutable result values returned by checker runners."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping

from .models import JsonValue, VersionedReference


class EvaluationState(StrEnum):
    """Terminal states admitted by evaluator contracts."""

    SATISFIED = "satisfied"
    VIOLATED = "violated"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class CheckerResult:
    """One evaluator-identified, revision-identified checker result."""

    evaluator: VersionedReference
    input_revision: str
    state: EvaluationState
    evidence: Mapping[str, JsonValue]
