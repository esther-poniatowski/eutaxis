"""Exercise the exact I-JSON and JCS byte boundary."""

from __future__ import annotations

from collections import UserDict

import pytest

from eutaxis.declarations.canonical_json import (
    CanonicalJsonError,
    jcs_bytes,
    parse_canonical_json_bytes,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"b": 1, "a": 2}, b'{"a":2,"b":1}'),
        ({"n": -0.0}, b'{"n":0}'),
        ({"n": 1e-7}, b'{"n":1e-7}'),
        ({"n": 1e-6}, b'{"n":0.000001}'),
        ({"n": 1e21}, b'{"n":1e+21}'),
        ({"\ue000": 1, "😀": 2}, '{"😀":2,"\ue000":1}'.encode()),
    ],
)
def test_jcs_bytes_has_stable_canonical_form(value: object, expected: bytes) -> None:
    assert jcs_bytes(value) == expected
    assert parse_canonical_json_bytes(expected) == value


@pytest.mark.parametrize(
    "source",
    [
        b'{"a":1,"a":2}',
        b'{"a": 1}',
        b'{"b":1,"a":2}',
        b'{"a":1}\n',
        b'{"a":NaN}',
        b'{"a":9007199254740992}',
        b'"\xed\xa0\x80"',
    ],
)
def test_canonical_parser_rejects_noncanonical_or_noninteroperable_bytes(
    source: bytes,
) -> None:
    with pytest.raises(CanonicalJsonError):
        parse_canonical_json_bytes(source)


@pytest.mark.parametrize(
    "value",
    [
        UserDict({"a": 1}),
        ("tuple",),
        {1: "not a JSON object key"},
        {"n": 2**53},
        {"n": float("inf")},
        {"text": "\ud800"},
    ],
)
def test_jcs_encoder_rejects_values_outside_exact_json_boundary(value: object) -> None:
    with pytest.raises(CanonicalJsonError):
        jcs_bytes(value)


def test_canonical_parser_requires_exact_bytes() -> None:
    with pytest.raises(CanonicalJsonError, match="exact bytes"):
        parse_canonical_json_bytes(bytearray(b"null"))  # type: ignore[arg-type]
