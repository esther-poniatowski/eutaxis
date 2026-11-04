"""Shared name invariants for generated and installed artifacts."""

from __future__ import annotations

import re

SAFE_SLUG_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")


def is_safe_slug(value: object) -> bool:
    """Return whether ``value`` is one safe lowercase path segment."""
    return isinstance(value, str) and SAFE_SLUG_PATTERN.fullmatch(value) is not None
