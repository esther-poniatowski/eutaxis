"""Retain process-local issuance state by object identity without hashing it."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Generic, TypeVar
from weakref import ReferenceType, ref

AuthorityState = tuple[object, ...]

_T = TypeVar("_T")


class IdentityAuthorityStore(Generic[_T]):
    """Associate weak aggregate identities with opaque issuance snapshots."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._entries: dict[int, tuple[ReferenceType[_T], object, AuthorityState]] = {}

    def issue(self, aggregate: _T, state: AuthorityState) -> object:
        """Retain ``state`` for one exact aggregate and return its opaque token."""
        key = id(aggregate)
        token = object()

        def release(reference: ReferenceType[_T]) -> None:
            self._release(key, reference)

        reference = ref(aggregate, release)
        with self._lock:
            self._entries[key] = (reference, token, state)
        return token

    def lookup(self, aggregate: _T) -> tuple[object, AuthorityState] | None:
        """Return issuance data only when the stored reference is ``aggregate``."""
        with self._lock:
            entry = self._entries.get(id(aggregate))
            if entry is None or entry[0]() is not aggregate:
                return None
            return entry[1], entry[2]

    def state(self, aggregate: _T) -> AuthorityState | None:
        """Return the existing authority state without constructing a wrapper."""
        with self._lock:
            entry = self._entries.get(id(aggregate))
            if entry is None or entry[0]() is not aggregate:
                return None
            return entry[2]

    def retire(self, aggregate: _T) -> AuthorityState | None:
        """Atomically remove and return authority owned by ``aggregate``."""
        with self._lock:
            entry = self._entries.get(id(aggregate))
            if entry is None or entry[0]() is not aggregate:
                return None
            del self._entries[id(aggregate)]
            return entry[2]

    def _release(self, key: int, reference: ReferenceType[_T]) -> None:
        """Remove only the entry owned by the weak reference being collected."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry[0] is reference:
                del self._entries[key]


def identity_value_state(value: object) -> object:
    """Capture immutable semantics and carrier identities without callables."""
    if isinstance(value, Enum):
        return (type(value), value.value)
    if value is None or type(value) in {str, int, float, bool}:
        return value
    if isinstance(value, Path):
        return (type(value), id(value), str(value))
    if isinstance(value, Mapping):
        return (
            type(value),
            id(value),
            tuple(
                (identity_value_state(key), identity_value_state(item))
                for key, item in value.items()
            ),
        )
    if type(value) is tuple:
        return (
            tuple,
            id(value),
            tuple(identity_value_state(item) for item in value),
        )
    if type(value) is frozenset:
        return (
            frozenset,
            id(value),
            tuple(sorted((identity_value_state(item) for item in value), key=repr)),
        )
    if is_dataclass(value):
        return (
            type(value),
            id(value),
            tuple(
                (field.name, identity_value_state(getattr(value, field.name)))
                for field in fields(value)
            ),
        )
    return (type(value), id(value))
