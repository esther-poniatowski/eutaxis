"""Shared immutable JSON value types."""

from __future__ import annotations

from typing import Mapping, TypeAlias

JsonValue: TypeAlias = (
    None
    | bool
    | int
    | float
    | str
    | tuple["JsonValue", ...]
    | Mapping[str, "JsonValue"]
)
