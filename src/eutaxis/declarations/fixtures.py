"""Load immutable evaluator fixtures through a confined resource boundary."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import (
    Iterable,
    Literal,
    Mapping,
    NoReturn,
    SupportsIndex,
    TypeAlias,
    cast,
)

from .embedded_schema import validate_json_instance
from .exceptions import (
    EvaluatorFixtureSchemaError,
    EvaluatorFixtureSemanticError,
)
from .fixture_schema import validate_evaluator_fixture_document
from .models import JsonValue, VersionedReference, freeze_json
from .source import (
    DocumentPath,
    SourceMap,
    format_document_path,
    load_yaml_document,
    nearest_location,
)

EvaluatorInputContracts: TypeAlias = Mapping[VersionedReference, Mapping[str, object]]
_PATH_RESOLUTION_ERRORS = (OSError, RuntimeError, ValueError)
_FIXTURE_INDEX_ISSUER = object()


@dataclass(frozen=True)
class EvaluatorFixtureDigest:
    """One fixture-owned file occurrence and its loaded SHA-256 digest."""

    path: Path
    sha256: str
    fixture_id: str
    role: Literal["descriptor", "source", "facet-registry"]
    document_path: DocumentPath


@dataclass(frozen=True)
class EvaluatorFixture:
    """One validated known-failure input and its confined resources."""

    path: Path
    schema_version: int
    id: str
    evaluator: VersionedReference
    input_revision: str
    input: Mapping[str, JsonValue]
    expected_state: str
    sources: tuple[Path, ...]
    facet_registry: Path
    digests: tuple[EvaluatorFixtureDigest, ...]
    locations: SourceMap


@dataclass(frozen=True, init=False, eq=False)
class EvaluatorFixtureIndex:
    """A deterministic fixture index issued only by the validated loader."""

    root: Path
    paths: tuple[Path, ...]
    fixtures: Mapping[str, EvaluatorFixture]
    _issuer: object

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        """Reject construction outside validated fixture loading."""
        raise TypeError(
            "EvaluatorFixtureIndex instances must be issued by fixture loading"
        )

    def __copy__(self) -> NoReturn:
        """Reject reconstruction by shallow copying."""
        raise TypeError("EvaluatorFixtureIndex instances cannot be copied")

    def __deepcopy__(self, _memo: object) -> NoReturn:
        """Reject reconstruction by deep copying."""
        raise TypeError("EvaluatorFixtureIndex instances cannot be copied")

    def __reduce__(self) -> NoReturn:
        """Reject serialization and reconstruction."""
        raise TypeError("EvaluatorFixtureIndex instances cannot be serialized")

    def __reduce_ex__(self, _protocol: SupportsIndex) -> NoReturn:
        """Reject protocol-specific serialization and reconstruction."""
        raise TypeError("EvaluatorFixtureIndex instances cannot be serialized")


def load_evaluator_fixture_index(
    paths: Iterable[Path],
    *,
    root: Path,
    input_contracts: EvaluatorInputContracts,
) -> EvaluatorFixtureIndex:
    """Load fixture descriptors in lexical path order under one root.

    ``input_contracts`` maps each exact evaluator reference to the operation
    input schema that types its fixture payload.
    """
    canonical_root = _canonical_root(root)
    supplied_paths = tuple(sorted(paths, key=lambda path: path.as_posix()))
    canonical_paths = tuple(
        sorted(
            (
                _confined_existing_file(
                    path,
                    root=canonical_root,
                    error_path=path,
                    location="$",
                    role="fixture descriptor",
                )
                for path in supplied_paths
            ),
            key=lambda path: path.as_posix(),
        )
    )
    fixtures: dict[str, EvaluatorFixture] = {}
    for descriptor_path in canonical_paths:
        fixture, locations = _load_evaluator_fixture(
            descriptor_path,
            root=canonical_root,
            input_contracts=input_contracts,
        )
        if fixture.id in fixtures:
            _raise_fixture_semantic(
                descriptor_path,
                locations,
                ("id",),
                f"duplicate fixture id {fixture.id!r}",
            )
        fixtures[fixture.id] = fixture
    return _issue_fixture_index(canonical_root, canonical_paths, fixtures)


def _issue_fixture_index(
    root: Path,
    paths: tuple[Path, ...],
    fixtures: Mapping[str, EvaluatorFixture],
) -> EvaluatorFixtureIndex:
    """Issue one aggregate after every descriptor passes validated loading."""
    index = object.__new__(EvaluatorFixtureIndex)
    object.__setattr__(index, "root", root)
    object.__setattr__(index, "paths", paths)
    object.__setattr__(index, "fixtures", MappingProxyType(dict(fixtures)))
    object.__setattr__(index, "_issuer", _FIXTURE_INDEX_ISSUER)
    return index


def _is_loader_issued_fixture_index(index: object) -> bool:
    """Return whether ``index`` carries this process's loader authority."""
    return (
        isinstance(index, EvaluatorFixtureIndex)
        and getattr(index, "_issuer", None) is _FIXTURE_INDEX_ISSUER
    )


def _load_evaluator_fixture(
    path: Path,
    *,
    root: Path,
    input_contracts: EvaluatorInputContracts,
) -> tuple[EvaluatorFixture, SourceMap]:
    """Load one descriptor and validate its resources and typed input."""
    document, locations, source_sha256 = load_yaml_document(
        path, error_type=EvaluatorFixtureSchemaError
    )
    validated = validate_evaluator_fixture_document(
        document, path=path, locations=locations
    )
    evaluator_data = _mapping(validated["evaluator"])
    evaluator = VersionedReference(
        id=str(evaluator_data["id"]), version=cast(int, evaluator_data["version"])
    )
    input_data = _mapping(validated["input"])
    input_schema = input_contracts.get(evaluator)
    if input_schema is None:
        _raise_fixture_semantic(
            path,
            locations,
            ("evaluator",),
            f"no input contract is registered for evaluator {evaluator.id!r} version {evaluator.version}",
        )
    error = validate_json_instance(input_schema, input_data)
    if error is not None:
        _raise_fixture_semantic(
            path,
            locations,
            ("input",) + tuple(error.absolute_path),
            f"input violates the registered operation contract: {error.message}",
        )
    sources = tuple(
        _resolve_resource(
            str(resource),
            descriptor=path,
            root=root,
            parts=("input", "sources", index),
            locations=locations,
        )
        for index, resource in enumerate(cast(list[object], input_data["sources"]))
    )
    facet_registry = _resolve_resource(
        str(input_data["facet-registry"]),
        descriptor=path,
        root=root,
        parts=("input", "facet-registry"),
        locations=locations,
    )
    fixture_id = str(validated["id"])
    digests = (
        EvaluatorFixtureDigest(
            path=path,
            sha256=source_sha256,
            fixture_id=fixture_id,
            role="descriptor",
            document_path=(),
        ),
        *(
            _resource_digest(
                resource,
                fixture_id=fixture_id,
                role="source",
                document_path=("input", "sources", index),
                descriptor=path,
                locations=locations,
            )
            for index, resource in enumerate(sources)
        ),
        _resource_digest(
            facet_registry,
            fixture_id=fixture_id,
            role="facet-registry",
            document_path=("input", "facet-registry"),
            descriptor=path,
            locations=locations,
        ),
    )
    return (
        EvaluatorFixture(
            path=path,
            schema_version=cast(int, validated["schema-version"]),
            id=fixture_id,
            evaluator=evaluator,
            input_revision=str(validated["input-revision"]),
            input=cast(Mapping[str, JsonValue], freeze_json(input_data)),
            expected_state=str(validated["expected-state"]),
            sources=sources,
            facet_registry=facet_registry,
            digests=digests,
            locations=MappingProxyType(dict(locations)),
        ),
        MappingProxyType(dict(locations)),
    )


def _resource_digest(
    path: Path,
    *,
    fixture_id: str,
    role: Literal["source", "facet-registry"],
    document_path: DocumentPath,
    descriptor: Path,
    locations: SourceMap,
) -> EvaluatorFixtureDigest:
    """Hash one resolved resource and retain its descriptor occurrence."""
    try:
        sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        _raise_fixture_semantic(
            descriptor,
            locations,
            document_path,
            f"fixture resource cannot be read: {exc}",
        )
    return EvaluatorFixtureDigest(
        path=path,
        sha256=sha256,
        fixture_id=fixture_id,
        role=role,
        document_path=document_path,
    )


def _canonical_root(root: Path) -> Path:
    """Resolve an existing fixture root before any containment checks."""
    try:
        canonical = root.resolve(strict=True)
    except _PATH_RESOLUTION_ERRORS as exc:
        raise EvaluatorFixtureSemanticError(root, "$", str(exc)) from exc
    if not canonical.is_dir():
        raise EvaluatorFixtureSemanticError(
            root, "$", "fixture root is not a directory"
        )
    return canonical


def _resolve_resource(
    value: str,
    *,
    descriptor: Path,
    root: Path,
    parts: DocumentPath,
    locations: SourceMap,
) -> Path:
    """Resolve one portable descriptor-relative resource within ``root``."""
    relative = PurePosixPath(value)
    raw_parts = value.split("/")
    if "\x00" in value or "\\" in value or relative.is_absolute() or ".." in raw_parts:
        _raise_fixture_semantic(
            descriptor,
            locations,
            parts,
            "resource path must be a relative POSIX path without NUL, backslashes, or '..' segments",
        )
    candidate = descriptor.parent.joinpath(*relative.parts)
    try:
        canonical = candidate.resolve(strict=True)
    except _PATH_RESOLUTION_ERRORS as exc:
        _raise_fixture_semantic(
            descriptor,
            locations,
            parts,
            f"fixture resource does not resolve: {exc}",
        )
    try:
        canonical.relative_to(root)
    except ValueError:
        _raise_fixture_semantic(
            descriptor,
            locations,
            parts,
            "fixture resource resolves outside fixture root",
        )
    if not canonical.is_file():
        _raise_fixture_semantic(
            descriptor,
            locations,
            parts,
            "fixture resource is not a regular file",
        )
    return canonical


def _confined_existing_file(
    path: Path,
    *,
    root: Path,
    error_path: Path,
    location: str,
    role: str,
) -> Path:
    """Resolve one existing regular file and reject root escapes."""
    try:
        canonical = path.resolve(strict=True)
    except _PATH_RESOLUTION_ERRORS as exc:
        raise EvaluatorFixtureSemanticError(
            error_path, location, f"{role} does not resolve: {exc}"
        ) from exc
    try:
        canonical.relative_to(root)
    except ValueError as exc:
        raise EvaluatorFixtureSemanticError(
            error_path, location, f"{role} resolves outside fixture root"
        ) from exc
    if not canonical.is_file():
        raise EvaluatorFixtureSemanticError(
            error_path, location, f"{role} is not a regular file"
        )
    return canonical


def _mapping(value: object) -> Mapping[str, object]:
    """Narrow a mapping already guaranteed by schema validation."""
    return cast(Mapping[str, object], value)


def _raise_fixture_semantic(
    path: Path,
    locations: SourceMap,
    parts: DocumentPath,
    message: str,
) -> NoReturn:
    """Raise one fixture semantic error at its closest source position."""
    source = nearest_location(locations, parts)
    raise EvaluatorFixtureSemanticError(
        path,
        format_document_path(parts),
        message,
        line=source.line if source else None,
        column=source.column if source else None,
    )
