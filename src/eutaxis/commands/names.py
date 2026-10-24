"""Name invariants for Skill sources and artifact directories."""

from __future__ import annotations

import re


SKILL_NAME_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")


def is_skill_name(value: object) -> bool:
    """Return whether ``value`` is one safe lowercase Skill slug."""
    return isinstance(value, str) and SKILL_NAME_PATTERN.fullmatch(value) is not None
