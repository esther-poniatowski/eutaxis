"""Parse canonical YAML while retaining source locations and JSON boundaries."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, TypeAlias

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, Node, SequenceNode

from .exceptions import (
    DeclarationSchemaError,
    EvaluatorFixtureSchemaError,
    FacetRegistrySchemaError,
    MigrationBaselineError,
)

PathPart: TypeAlias = str | int
DocumentPath: TypeAlias = tuple[PathPart, ...]


@dataclass(frozen=True)
class SourceLocation:
    """A one-based source position."""

    line: int
    column: int


SourceMap: TypeAlias = Mapping[DocumentPath, SourceLocation]
SchemaErrorType: TypeAlias = (
    type[DeclarationSchemaError]
    | type[EvaluatorFixtureSchemaError]
    | type[FacetRegistrySchemaError]
    | type[MigrationBaselineError]
)


class _CanonicalLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicates and leaves timestamps as text."""

    yaml_implicit_resolvers = {
        key: [
            (tag, expression)
            for tag, expression in resolvers
            if tag != "tag:yaml.org,2002:timestamp"
        ]
        for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }

    def construct_mapping(
        self, node: MappingNode, deep: bool = False
    ) -> dict[object, object]:
        """Construct a mapping after rejecting every duplicate source key."""
        seen: dict[object, Node] = {}
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                first = seen.get(key)
            except TypeError as exc:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "mapping keys must be scalar JSON values",
                    key_node.start_mark,
                ) from exc
            if first is not None:
                raise ConstructorError(
                    "while constructing a mapping",
                    first.start_mark,
                    f"duplicate key {key!r}",
                    key_node.start_mark,
                )
            seen[key] = key_node
        return super().construct_mapping(node, deep=deep)


def load_yaml_document(
    path: Path,
    *,
    error_type: SchemaErrorType = DeclarationSchemaError,
) -> tuple[object, dict[DocumentPath, SourceLocation], str]:
    """Load one YAML document and return its value, source map, and byte hash.

    Raises
    ------
    DeclarationSchemaError or FacetRegistrySchemaError
        If the file cannot be read or the YAML source is invalid.
    """
    try:
        source_bytes = path.read_bytes()
    except OSError as exc:
        raise error_type(path, "$", str(exc)) from exc
    return load_yaml_bytes(source_bytes, path=path, error_type=error_type)


def load_yaml_bytes(
    source_bytes: bytes,
    *,
    path: Path,
    error_type: SchemaErrorType = DeclarationSchemaError,
) -> tuple[object, dict[DocumentPath, SourceLocation], str]:
    """Parse retained YAML bytes with one diagnostic path and byte hash."""
    if type(source_bytes) is not bytes:
        raise error_type(path, "$", "source must be exact bytes")
    try:
        text = source_bytes.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise error_type(path, "$", str(exc)) from exc
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()

    loader = _CanonicalLoader(text)
    try:
        node = loader.get_single_node()
        if node is None:
            raise error_type(path, "$", "source is empty")
        document = loader.construct_document(node)
        locations: dict[DocumentPath, SourceLocation] = {}
        _collect_locations(node, document, (), locations)
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark
        message = str(exc) if isinstance(exc, ConstructorError) else exc.problem
        raise error_type(
            path,
            "$",
            message or str(exc),
            line=mark.line + 1 if mark is not None else None,
            column=mark.column + 1 if mark is not None else None,
        ) from exc
    finally:
        loader.dispose()

    _validate_json_domain(
        document,
        path=path,
        locations=locations,
        error_type=error_type,
    )
    return document, locations, source_sha256


def format_document_path(parts: DocumentPath) -> str:
    """Format a structured document path for diagnostics."""
    result = "$"
    for part in parts:
        result += f"[{part}]" if isinstance(part, int) else f".{part}"
    return result


def nearest_location(
    locations: SourceMap, parts: DocumentPath
) -> SourceLocation | None:
    """Return the closest recorded source location for ``parts``."""
    current = parts
    while current:
        if current in locations:
            return locations[current]
        current = current[:-1]
    return locations.get(())


def _collect_locations(
    node: Node,
    value: object,
    path: DocumentPath,
    locations: dict[DocumentPath, SourceLocation],
    active_nodes: set[int] | None = None,
) -> None:
    """Collect positions by following the already constructed document."""
    if active_nodes is None:
        active_nodes = set()
    node_identity = id(node)
    if node_identity in active_nodes:
        raise ConstructorError(
            "while collecting source locations",
            node.start_mark,
            "cyclic YAML aliases are outside the JSON tree domain",
            node.start_mark,
        )
    active_nodes.add(node_identity)
    locations[path] = SourceLocation(
        node.start_mark.line + 1, node.start_mark.column + 1
    )
    try:
        if isinstance(node, MappingNode) and isinstance(value, Mapping):
            for (key, child_value), (key_node, child_node) in zip(
                value.items(), node.value
            ):
                child_path = path + (str(key),)
                _collect_locations(
                    child_node,
                    child_value,
                    child_path,
                    locations,
                    active_nodes,
                )
                locations[child_path] = SourceLocation(
                    key_node.start_mark.line + 1, key_node.start_mark.column + 1
                )
        elif isinstance(node, SequenceNode) and isinstance(value, list):
            for index, (child_node, child_value) in enumerate(zip(node.value, value)):
                _collect_locations(
                    child_node,
                    child_value,
                    path + (index,),
                    locations,
                    active_nodes,
                )
    finally:
        active_nodes.remove(node_identity)


def _validate_json_domain(
    value: object,
    *,
    path: Path,
    locations: SourceMap,
    error_type: SchemaErrorType,
    parts: DocumentPath = (),
    active_containers: set[int] | None = None,
) -> None:
    """Reject YAML values that cannot be represented by JSON."""
    if active_containers is None:
        active_containers = set()
    if isinstance(value, Mapping):
        identity = _enter_container(
            value,
            path=path,
            locations=locations,
            parts=parts,
            active=active_containers,
            error_type=error_type,
        )
        try:
            for key, item in value.items():
                if not isinstance(key, str):
                    _raise_domain_error(
                        path,
                        locations,
                        parts,
                        f"JSON object key {key!r} is not a string",
                        error_type=error_type,
                    )
                _validate_json_domain(
                    item,
                    path=path,
                    locations=locations,
                    parts=parts + (key,),
                    active_containers=active_containers,
                    error_type=error_type,
                )
        finally:
            active_containers.remove(identity)
        return
    if isinstance(value, list):
        identity = _enter_container(
            value,
            path=path,
            locations=locations,
            parts=parts,
            active=active_containers,
            error_type=error_type,
        )
        try:
            for index, item in enumerate(value):
                _validate_json_domain(
                    item,
                    path=path,
                    locations=locations,
                    parts=parts + (index,),
                    active_containers=active_containers,
                    error_type=error_type,
                )
        finally:
            active_containers.remove(identity)
        return
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    _raise_domain_error(
        path,
        locations,
        parts,
        f"{type(value).__name__} is not a JSON value",
        error_type=error_type,
    )


def _enter_container(
    value: object,
    *,
    path: Path,
    locations: SourceMap,
    parts: DocumentPath,
    active: set[int],
    error_type: SchemaErrorType = DeclarationSchemaError,
) -> int:
    """Enter one JSON container and reject recursive YAML alias graphs."""
    identity = id(value)
    if identity in active:
        _raise_domain_error(
            path,
            locations,
            parts,
            "cyclic YAML aliases are outside the JSON tree domain",
            error_type=error_type,
        )
    active.add(identity)
    return identity


def _raise_domain_error(
    path: Path,
    locations: SourceMap,
    parts: DocumentPath,
    message: str,
    *,
    error_type: SchemaErrorType,
) -> None:
    """Raise one source-located JSON-domain error."""
    source = nearest_location(locations, parts)
    raise error_type(
        path,
        format_document_path(parts),
        message,
        line=source.line if source else None,
        column=source.column if source else None,
    )
