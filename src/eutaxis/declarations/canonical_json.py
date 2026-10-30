"""Encode and parse JSON Canonicalization Scheme values."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from decimal import Decimal
from typing import NoReturn, cast

_SAFE_INTEGER = 2**53 - 1


class CanonicalJsonError(ValueError):
    """Report a value or byte sequence outside the admitted JCS boundary."""


def require_unicode_scalar_text(value: str) -> None:
    """Reject text containing a lone UTF-16 surrogate code point."""
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise CanonicalJsonError("lone surrogate is not interoperable")


def jcs_bytes(value: object) -> bytes:
    """Return canonical UTF-8 bytes for one I-JSON value."""
    try:
        return _jcs(value).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise CanonicalJsonError(str(exc)) from exc


def parse_canonical_json_bytes(source: bytes) -> object:
    """Parse exact I-JSON bytes and require their JCS representation."""
    if type(source) is not bytes:
        raise CanonicalJsonError("source must be exact bytes")
    try:
        text = source.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise CanonicalJsonError(str(exc)) from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_int=_parse_integer,
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise CanonicalJsonError(str(exc)) from exc
    if source != jcs_bytes(value):
        raise CanonicalJsonError(
            "source bytes are not their exact JSON Canonicalization Scheme form"
        )
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalJsonError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    raise CanonicalJsonError(f"non-finite JSON number {value!r} is invalid")


def _parse_integer(value: str) -> int:
    result = int(value)
    if abs(result) > _SAFE_INTEGER:
        raise CanonicalJsonError("integer is outside the interoperable range")
    return result


def _jcs(value: object) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        integer = cast(int, value)
        if abs(integer) > _SAFE_INTEGER:
            raise ValueError("integer is outside the interoperable range")
        return str(integer)
    if type(value) is float:
        return _jcs_float(cast(float, value))
    if type(value) is str:
        text = cast(str, value)
        _utf16_key(text)
        return json.dumps(text, ensure_ascii=False, allow_nan=False)
    if type(value) is dict:
        mapping = cast(dict[object, object], value)
        keys = list(mapping)
        if any(type(key) is not str for key in keys):
            raise TypeError("JSON object key is not text")
        pairs = [
            f"{_jcs(key)}:{_jcs(mapping[key])}"
            for key in sorted(cast(list[str], keys), key=_utf16_key)
        ]
        return "{" + ",".join(pairs) + "}"
    if type(value) is list:
        return "[" + ",".join(_jcs(item) for item in cast(list[object], value)) + "]"
    if isinstance(value, Mapping):
        raise TypeError("JSON objects must use exact built-in dictionaries")
    raise TypeError(f"value of type {type(value).__name__} is not JSON")


def _utf16_key(value: str) -> bytes:
    require_unicode_scalar_text(value)
    return value.encode("utf-16-be")


def _jcs_float(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("number is not finite")
    if value == 0:
        return "0"
    decimal = Decimal(repr(value))
    absolute = abs(value)
    if 1e-6 <= absolute < 1e21:
        result = format(decimal, "f")
        if "." in result:
            result = result.rstrip("0").rstrip(".")
        return result
    sign = "-" if decimal.is_signed() else ""
    digits = "".join(str(digit) for digit in decimal.copy_abs().as_tuple().digits)
    digits = digits.rstrip("0") or "0"
    decimal_exponent = cast(int, decimal.copy_abs().as_tuple().exponent)
    exponent = len(digits) + decimal_exponent - 1
    coefficient = digits[0] + (("." + digits[1:]) if len(digits) > 1 else "")
    exponent_text = f"+{exponent}" if exponent >= 0 else str(exponent)
    return f"{sign}{coefficient}e{exponent_text}"
