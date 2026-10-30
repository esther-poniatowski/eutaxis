"""Define the one normalized relative POSIX path grammar for acquisition."""

from __future__ import annotations

from .canonical_json import CanonicalJsonError, require_unicode_scalar_text


class AcquisitionPathError(ValueError):
    """Report a value outside the acquisition path grammar."""


def normalized_relative_path(value: object, *, allow_dot: bool) -> str:
    """Return exact text after validating the acquisition path grammar."""
    if type(value) is not str:
        raise AcquisitionPathError("path must be exact text")
    try:
        require_unicode_scalar_text(value)
    except CanonicalJsonError as exc:
        raise AcquisitionPathError(str(exc)) from exc
    if value == ".":
        if allow_dot:
            return value
        raise AcquisitionPathError("'.' is admitted only for a source root")
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or "\x00" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise AcquisitionPathError("path is not a normalized relative POSIX path")
    return value


def normalized_path_components(value: object, *, allow_dot: bool) -> tuple[str, ...]:
    """Return the validated path components used for descriptor traversal."""
    path = normalized_relative_path(value, allow_dot=allow_dot)
    return () if path == "." else tuple(path.split("/"))
