"""Load, select, and fingerprint explicit migration baselines."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import NoReturn, SupportsIndex, cast

from ._authority import IdentityAuthorityStore, identity_value_state
from .attention import CompletionRequirement, RuleCriterionKey, RuleObligationSnapshot
from .exceptions import MigrationBaselineError
from .migration_baseline_schema import validate_migration_baseline_document
from .models import VersionedReference
from .rule_evidence import (
    RuleAssistedEvidence,
    RuleManualEvidence,
    RuleMechanicalEvidence,
)
from .source import format_document_path, load_yaml_document

_REGISTRY_ISSUER = object()
_SELECTION_ISSUER = object()
_REGISTRY_AUTHORITIES: IdentityAuthorityStore[MigrationBaselineRegistry] = (
    IdentityAuthorityStore()
)
_SELECTION_AUTHORITIES: IdentityAuthorityStore[MigrationBaselineSelection] = (
    IdentityAuthorityStore()
)
_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$"
)
_SAFE_INTEGER = 2**53 - 1
_EXACT_PATH_TYPE = type(Path())


@dataclass(frozen=True)
class MigrationBaselineFinding:
    """Identify one exact eligible rule-criterion finding."""

    key: RuleCriterionKey
    state: str
    digest: str


@dataclass(frozen=True)
class MigrationBaseline:
    """Retain one validated baseline and its exact source provenance."""

    schema_version: int
    id: str
    owner: str
    manifest: str
    migration: str
    expires_at: str
    finding: MigrationBaselineFinding
    source_path: str
    source_sha256: str


@dataclass(frozen=True, init=False, eq=False)
class MigrationBaselineRegistry:
    """Retain validated baseline sources behind process-local authority."""

    root: Path
    paths: tuple[Path, ...]
    entries: Mapping[str, MigrationBaseline]
    _token: object
    _state: tuple[object, ...]
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("MigrationBaselineRegistry instances must be issued by loading")

    def __copy__(self) -> NoReturn:
        raise TypeError("MigrationBaselineRegistry instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("MigrationBaselineRegistry instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("MigrationBaselineRegistry instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("MigrationBaselineRegistry instances cannot be serialized")


@dataclass(frozen=True, init=False, eq=False)
class MigrationBaselineSelection:
    """Retain one explicit ordered selection from an exact registry."""

    registry: MigrationBaselineRegistry
    identifiers: tuple[str, ...]
    baselines: tuple[MigrationBaseline, ...]
    _token: object
    _state: tuple[object, ...]
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        raise TypeError("MigrationBaselineSelection instances must be issued")

    def __copy__(self) -> NoReturn:
        raise TypeError("MigrationBaselineSelection instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        raise TypeError("MigrationBaselineSelection instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("MigrationBaselineSelection instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        raise TypeError("MigrationBaselineSelection instances cannot be serialized")


@dataclass(frozen=True)
class AppliedMigrationBaseline:
    """Retain the exact reviewed registry entry applied to one record."""

    baseline: MigrationBaseline
    source_path: str
    source_sha256: str


def load_migration_baseline_registry(
    paths: Iterable[Path], *, root: Path
) -> MigrationBaselineRegistry:
    """Load closed baseline sources under one confined root."""
    canonical_root = _canonical_root(root)
    supplied = tuple(paths)
    canonical: list[Path] = []
    for index, path in enumerate(supplied):
        if type(path) is not _EXACT_PATH_TYPE:
            _fail(Path("<paths>"), ("paths", index), "path must be an exact Path")
        try:
            resolved = path.resolve(strict=True)
            if type(resolved) is not _EXACT_PATH_TYPE:
                _fail(path, ("paths", index), "resolved path must be an exact Path")
            resolved.relative_to(canonical_root)
        except (OSError, RuntimeError, ValueError) as exc:
            _fail(path, ("paths", index), "path is not a file under the root", exc)
        if not resolved.is_file():
            _fail(path, ("paths", index), "path is not a file")
        canonical.append(resolved)
    ordered = tuple(sorted(canonical, key=lambda item: item.as_posix()))
    if len(set(ordered)) != len(ordered):
        _fail(canonical_root, ("paths",), "source path occurs more than once")
    entries: dict[str, MigrationBaseline] = {}
    for path in ordered:
        document, locations, source_sha256 = load_yaml_document(
            path, error_type=MigrationBaselineError
        )
        source = validate_migration_baseline_document(
            document, path=path, locations=locations
        )
        baseline = _baseline_from_source(
            source,
            source_path=path.relative_to(canonical_root).as_posix(),
            source_sha256=source_sha256,
            path=path,
        )
        if baseline.id in entries:
            _fail(path, ("id",), f"duplicate baseline id {baseline.id!r}")
        entries[baseline.id] = baseline
    registry = object.__new__(MigrationBaselineRegistry)
    object.__setattr__(registry, "root", canonical_root)
    object.__setattr__(registry, "paths", ordered)
    object.__setattr__(registry, "entries", MappingProxyType(entries))
    object.__setattr__(registry, "_issuer", _REGISTRY_ISSUER)
    state = _capture_registry_state(registry)
    token = _REGISTRY_AUTHORITIES.issue(registry, state)
    object.__setattr__(registry, "_token", token)
    object.__setattr__(registry, "_state", state)
    return registry


def select_migration_baselines(
    registry: MigrationBaselineRegistry, identifiers: tuple[str, ...]
) -> MigrationBaselineSelection:
    """Issue one explicit exact selection without scanning at ledger time."""
    if not _is_issued_migration_baseline_registry(registry):
        _fail(Path("<registry>"), ("registry",), "registry is not authoritative")
    if type(identifiers) is not tuple:
        _fail(Path("<selection>"), ("identifiers",), "identifiers must be a tuple")
    seen: set[str] = set()
    selected: list[MigrationBaseline] = []
    for index, identifier in enumerate(identifiers):
        if (
            type(identifier) is not str
            or not identifier
            or any(character.isspace() for character in identifier)
        ):
            _fail(
                Path("<selection>"),
                ("identifiers", index),
                "identifier must be non-empty text without whitespace",
            )
        if identifier in seen:
            _fail(
                Path("<selection>"),
                ("identifiers", index),
                "identifier occurs more than once",
            )
        baseline = registry.entries.get(identifier)
        if baseline is None:
            _fail(
                Path("<selection>"),
                ("identifiers", index),
                "identifier is not present in the registry",
            )
        seen.add(identifier)
        selected.append(baseline)
    selection = object.__new__(MigrationBaselineSelection)
    object.__setattr__(selection, "registry", registry)
    object.__setattr__(selection, "identifiers", identifiers)
    object.__setattr__(selection, "baselines", tuple(selected))
    object.__setattr__(selection, "_issuer", _SELECTION_ISSUER)
    state = _capture_selection_state(selection)
    token = _SELECTION_AUTHORITIES.issue(selection, state)
    object.__setattr__(selection, "_token", token)
    object.__setattr__(selection, "_state", state)
    return selection


def eligible_finding_digest(
    requirement: CompletionRequirement,
    state: str,
    sources: tuple[object, ...],
    diagnostics: tuple[str, ...],
) -> str | None:
    """Return the exact version 1 digest, or ``None`` when ineligible."""
    canonical = _eligible_finding_canonical_bytes(
        requirement, state, sources, diagnostics
    )
    if canonical is None:
        return None
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _eligible_finding_canonical_bytes(
    requirement: CompletionRequirement,
    state: str,
    sources: tuple[object, ...],
    diagnostics: tuple[str, ...],
) -> bytes | None:
    """Return the complete version 1 JCS payload for an eligible finding."""
    if type(requirement.key) is not RuleCriterionKey:
        return None
    if state == "unchecked":
        if sources or diagnostics:
            return None
        source: object = None
    elif state == "violated":
        if len(sources) != 1 or diagnostics:
            return None
        source = _rule_source_payload(sources[0])
        if source is None:
            return None
    else:
        return None
    obligation = requirement.obligation
    if type(obligation) is not RuleObligationSnapshot:
        return None
    payload = {
        "schema-version": 1,
        "key": _key_payload(requirement.key),
        "obligation": _obligation_payload(obligation),
        "evaluator": _reference_payload(
            None
            if requirement.evaluator is None
            else VersionedReference(
                requirement.evaluator.id, requirement.evaluator.version
            )
        ),
        "enforcement": (
            None if requirement.enforcement is None else requirement.enforcement.value
        ),
        "state": state,
        "source": source,
    }
    try:
        return _jcs_bytes(payload)
    except (TypeError, ValueError, UnicodeError):
        return None


def baseline_expiry(value: str) -> datetime:
    """Parse the one admitted UTC timestamp grammar."""
    if type(value) is not str or _TIMESTAMP.fullmatch(value) is None:
        raise ValueError("timestamp does not use canonical UTC grammar")
    observed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    return observed.replace(tzinfo=timezone.utc)


def _baseline_from_source(
    source: Mapping[str, object],
    *,
    source_path: str,
    source_sha256: str,
    path: Path,
) -> MigrationBaseline:
    schema_version = source.get("schema-version")
    if type(schema_version) is not int or schema_version != 1:
        _fail(
            path,
            ("schema-version",),
            "schema-version must be the exact integer 1",
        )
    try:
        expires_at = cast(str, source["expires-at"])
        baseline_expiry(expires_at)
        finding = cast(Mapping[str, object], source["finding"])
        key = cast(Mapping[str, object], finding["key"])
        return MigrationBaseline(
            schema_version,
            cast(str, source["id"]),
            cast(str, source["owner"]),
            cast(str, source["manifest"]),
            cast(str, source["migration"]),
            expires_at,
            MigrationBaselineFinding(
                RuleCriterionKey(
                    cast(str, key["declaration"]), cast(str, key["criterion"])
                ),
                cast(str, finding["state"]),
                cast(str, finding["digest"]),
            ),
            source_path,
            source_sha256,
        )
    except (KeyError, TypeError, ValueError) as exc:
        _fail(path, (), "validated source could not be normalized", exc)


def _canonical_root(root: Path) -> Path:
    if type(root) is not _EXACT_PATH_TYPE:
        _fail(Path("<root>"), ("root",), "root must be an exact Path")
    try:
        canonical = root.resolve(strict=True)
        if type(canonical) is not _EXACT_PATH_TYPE:
            _fail(root, ("root",), "resolved root must be an exact Path")
    except (OSError, RuntimeError, ValueError) as exc:
        _fail(root, ("root",), "root cannot be resolved", exc)
    if not canonical.is_dir():
        _fail(root, ("root",), "root is not a directory")
    return canonical


def _key_payload(key: RuleCriterionKey) -> dict[str, object]:
    return {
        "kind": "rule-criterion",
        "declaration": key.declaration,
        "criterion": key.criterion,
    }


def _reference_payload(reference: VersionedReference | None) -> object:
    if reference is None:
        return None
    return {"id": reference.id, "version": reference.version}


def _obligation_payload(obligation: RuleObligationSnapshot) -> dict[str, object]:
    criterion = obligation.criterion
    return {
        "key": _key_payload(obligation.key),
        "axis": obligation.axis.value,
        "failure-mode": obligation.failure_mode,
        "required-visibility": obligation.required_visibility,
        "title": obligation.title,
        "rationale": obligation.rationale,
        "criterion": {
            "id": criterion.id,
            "norms": list(criterion.norms),
            "evaluator": _reference_payload(criterion.evaluator),
            "statement": criterion.statement,
        },
        "norms": [
            {
                "id": norm.id,
                "modality": norm.modality,
                "subject": norm.subject,
                "action": {
                    "verb": norm.action.verb,
                    "object": norm.action.object,
                    "timing": norm.action.timing,
                },
                "applicability": norm.applicability,
                "guidance": norm.guidance,
                "rationale": norm.rationale,
                "decision-criterion": norm.decision_criterion,
            }
            for norm in obligation.norms
        ],
    }


def _rule_source_payload(source: object) -> dict[str, object] | None:
    if type(source) is RuleManualEvidence:
        manual = cast(RuleManualEvidence, source)
        return {
            "kind": "manual",
            "evaluator": _reference_payload(manual.submission.evaluator),
            "input-revision": manual.submission.input_revision,
            "evidence": manual.submission.evidence,
            "state": manual.state.value,
        }
    if type(source) is RuleAssistedEvidence:
        assisted = cast(RuleAssistedEvidence, source)
        if assisted.execution is None or assisted.judgment is None:
            return None
        execution = assisted.execution
        judgment = assisted.judgment
        return {
            "kind": "assisted",
            "evaluator": _reference_payload(execution.evaluator),
            "input-revision": execution.input_revision,
            "input": execution.input_data,
            "evidence": execution.evidence,
            "residual": {
                "schema-version": judgment.schema_version,
                "question": judgment.request.residual_question,
                "state": judgment.state.value,
                "rationale": judgment.rationale,
            },
            "state": assisted.state.value,
        }
    if type(source) is RuleMechanicalEvidence:
        mechanical = cast(RuleMechanicalEvidence, source)
        if mechanical.result is None:
            return None
        return {
            "kind": "mechanical",
            "evaluator": _reference_payload(mechanical.result.evaluator),
            "input-revision": mechanical.result.input_revision,
            "evidence": mechanical.result.evidence,
            "state": mechanical.state.value,
        }
    return None


def _jcs_bytes(value: object) -> bytes:
    return _jcs(value).encode("utf-8", errors="strict")


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
    if isinstance(value, Mapping):
        pairs: list[str] = []
        keys = list(value.keys())
        if any(type(key) is not str for key in keys):
            raise TypeError("JSON object key is not text")
        for key in sorted(cast(list[str], keys), key=_utf16_key):
            pairs.append(f"{_jcs(key)}:{_jcs(value[key])}")
        return "{" + ",".join(pairs) + "}"
    if type(value) in {list, tuple}:
        return (
            "[" + ",".join(_jcs(item) for item in cast(Iterable[object], value)) + "]"
        )
    raise TypeError(f"value of type {type(value).__name__} is not JSON")


def _utf16_key(value: str) -> bytes:
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise UnicodeError("lone surrogate is not interoperable")
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


def _capture_registry_state(
    registry: MigrationBaselineRegistry,
) -> tuple[object, ...]:
    return (
        id(registry.root),
        str(registry.root),
        id(registry.paths),
        tuple((id(path), str(path)) for path in registry.paths),
        id(registry.entries),
        tuple(
            (identifier, id(entry), identity_value_state(entry))
            for identifier, entry in registry.entries.items()
        ),
        id(registry._issuer),
    )


def _is_issued_migration_baseline_registry(value: object) -> bool:
    try:
        if (
            type(value) is not MigrationBaselineRegistry
            or getattr(value, "_issuer", None) is not _REGISTRY_ISSUER
            or type(getattr(value, "_state", None)) is not tuple
        ):
            return False
        registry = cast(MigrationBaselineRegistry, value)
        issued = _REGISTRY_AUTHORITIES.lookup(registry)
        return (
            issued is not None
            and registry._token is issued[0]
            and registry._state == issued[1]
            and registry._state == _capture_registry_state(registry)
        )
    except Exception:
        return False


def _capture_selection_state(
    selection: MigrationBaselineSelection,
) -> tuple[object, ...]:
    return (
        id(selection.registry),
        id(selection.identifiers),
        selection.identifiers,
        id(selection.baselines),
        tuple(id(item) for item in selection.baselines),
        id(selection._issuer),
    )


def _is_issued_migration_baseline_selection(value: object) -> bool:
    try:
        if (
            type(value) is not MigrationBaselineSelection
            or getattr(value, "_issuer", None) is not _SELECTION_ISSUER
            or type(getattr(value, "_state", None)) is not tuple
        ):
            return False
        selection = cast(MigrationBaselineSelection, value)
        issued = _SELECTION_AUTHORITIES.lookup(selection)
        return (
            issued is not None
            and selection._token is issued[0]
            and selection._state == issued[1]
            and selection._state == _capture_selection_state(selection)
            and _is_issued_migration_baseline_registry(selection.registry)
            and len(selection.identifiers) == len(selection.baselines)
            and all(
                selection.registry.entries.get(identifier) is baseline
                for identifier, baseline in zip(
                    selection.identifiers, selection.baselines
                )
            )
        )
    except Exception:
        return False


def _fail(
    path: Path,
    parts: tuple[str | int, ...],
    message: str,
    cause: BaseException | None = None,
) -> NoReturn:
    error = MigrationBaselineError(path, format_document_path(parts), message)
    if cause is None:
        raise error
    raise error from cause
