"""Shared name invariants for generated and installed artifacts."""

from __future__ import annotations

import re

SAFE_SLUG_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
_PORTABLE_DEVICE_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
)


def is_safe_slug(value: object) -> bool:
    """Return whether ``value`` is one safe lowercase path segment."""
    return isinstance(value, str) and SAFE_SLUG_PATTERN.fullmatch(value) is not None


def is_portable_skill_name(value: object) -> bool:
    """Return whether ``value`` is a portable shared-host Skill name."""
    return (
        is_safe_slug(value)
        and isinstance(value, str)
        and len(value.encode("utf-8")) <= 64
        and value.casefold() not in _PORTABLE_DEVICE_NAMES
    )
