"""Test identity-indexed weak authority storage independently of aggregates."""

from __future__ import annotations

import gc
from dataclasses import dataclass
from threading import Barrier, Thread
from weakref import ref

from eutaxis.declarations._authority import IdentityAuthorityStore


@dataclass(frozen=True)
class _SemanticValue:
    payload: object


def test_identity_store_never_requires_value_hashing_or_equality() -> None:
    store: IdentityAuthorityStore[_SemanticValue] = IdentityAuthorityStore()
    first = _SemanticValue({"nested": [1, 2]})
    second = _SemanticValue({"nested": [1, 2]})

    first_token = store.issue(first, ("first",))
    second_token = store.issue(second, ("second",))

    assert first == second
    assert store.lookup(first) == (first_token, ("first",))
    assert store.lookup(second) == (second_token, ("second",))


def test_identity_store_releases_without_retaining_the_aggregate() -> None:
    store: IdentityAuthorityStore[_SemanticValue] = IdentityAuthorityStore()
    value = _SemanticValue("value")
    key = id(value)
    reference = ref(value)
    store.issue(value, ("state",))

    del value
    gc.collect()

    assert reference() is None
    assert key not in store._entries


def test_delayed_release_cannot_remove_a_replacement_entry() -> None:
    store: IdentityAuthorityStore[_SemanticValue] = IdentityAuthorityStore()
    old = _SemanticValue("old")
    replacement = _SemanticValue("replacement")
    key = id(old)
    store.issue(old, ("old",))
    old_reference = store._entries[key][0]
    replacement_reference = ref(replacement)
    replacement_token = object()
    store._entries[key] = (replacement_reference, replacement_token, ("replacement",))

    store._release(key, old_reference)

    assert store._entries[key] == (
        replacement_reference,
        replacement_token,
        ("replacement",),
    )


def test_state_returns_the_issued_state_object_without_a_wrapper() -> None:
    store: IdentityAuthorityStore[_SemanticValue] = IdentityAuthorityStore()
    value = _SemanticValue("value")
    state = (object(), "state")
    store.issue(value, state)

    assert store.state(value) is state


def test_retire_returns_and_removes_the_issued_state() -> None:
    store: IdentityAuthorityStore[_SemanticValue] = IdentityAuthorityStore()
    value = _SemanticValue("value")
    state = (object(), "state")
    store.issue(value, state)

    assert store.retire(value) is state
    assert store.state(value) is None
    assert store.lookup(value) is None
    assert store.retire(value) is None


def test_only_one_concurrent_retirement_can_own_the_state() -> None:
    store: IdentityAuthorityStore[_SemanticValue] = IdentityAuthorityStore()
    value = _SemanticValue("value")
    state = (object(), "state")
    store.issue(value, state)
    ready = Barrier(3)
    results: list[object] = []

    def retire() -> None:
        ready.wait()
        results.append(store.retire(value))

    workers = [Thread(target=retire), Thread(target=retire)]
    for worker in workers:
        worker.start()
    ready.wait()
    for worker in workers:
        worker.join(5)

    assert all(not worker.is_alive() for worker in workers)
    assert sum(result is state for result in results) == 1
    assert sum(result is None for result in results) == 1
