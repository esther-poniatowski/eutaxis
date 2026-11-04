"""Name invariants for Skill sources and artifact directories."""

from __future__ import annotations

from ..names import is_safe_slug


def is_skill_name(value: object) -> bool:
    """Return whether ``value`` is one safe lowercase Skill slug."""
    return is_safe_slug(value)
