"""Boundary tests for versioned evaluator-fixture descriptors."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml

from eutaxis.declarations import (
    EvaluatorFixtureSchemaError,
    EvaluatorFixtureSemanticError,
    VersionedReference,
    evaluator_fixture_schema,
    evaluator_fixture_schema_path,
    load_evaluator_fixture_index,
)

EVALUATOR = VersionedReference("eutaxis/declaration-registry", 1)
INPUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["sources", "facet-registry"],
    "properties": {
        "sources": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "pattern": "[.]yaml$"},
        },
        "facet-registry": {"type": "string", "pattern": "[.]yaml$"},
    },
    "additionalProperties": False,
}


def _descriptor(identifier: str = "fixture/known-failure") -> dict[str, object]:
    """Return one complete descriptor document."""
    return {
        "schema-version": 1,
        "id": identifier,
        "evaluator": {"id": EVALUATOR.id, "version": EVALUATOR.version},
        "input-revision": "declaration-v1",
        "input": {
            "sources": ["resources/declaration.yaml"],
            "facet-registry": "resources/facets.yaml",
        },
        "expected-state": "violated",
    }


def _fixture_root(tmp_path: Path) -> Path:
    """Create the resources shared by descriptor tests."""
    resources = tmp_path / "resources"
    resources.mkdir(parents=True)
    (resources / "declaration.yaml").write_text("kind: rule\n", encoding="utf-8")
    (resources / "facets.yaml").write_text("facets: []\n", encoding="utf-8")
    return tmp_path


def _write_descriptor(
    root: Path,
    name: str = "fixture.yaml",
    *,
    identifier: str = "fixture/known-failure",
    mutate: Callable[[dict[str, object]], None] | None = None,
) -> Path:
    """Write one descriptor while preserving its insertion order."""
    document = _descriptor(identifier)
    if mutate is not None:
        mutate(document)
    path = root / name
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _load(paths: list[Path], root: Path):
    """Load descriptors against the one test input contract."""
    return load_evaluator_fixture_index(
        paths,
        root=root,
        input_contracts={EVALUATOR: INPUT_SCHEMA},
    )


def _line_containing(path: Path, text: str) -> int:
    """Return the one-based source line containing ``text``."""
    return next(
        index
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if text in line
    )


def test_fixture_schema_is_packaged_meta_validated_and_isolated() -> None:
    assert evaluator_fixture_schema_path().is_file()
    schema = evaluator_fixture_schema()
    assert schema["title"] == "Eutaxis evaluator fixture version 1"
    schema["title"] = "mutated"
    assert evaluator_fixture_schema()["title"] == "Eutaxis evaluator fixture version 1"


def test_fixture_index_is_lexical_resolved_typed_and_immutable(
    tmp_path: Path,
) -> None:
    root = _fixture_root(tmp_path)
    later = _write_descriptor(root, "z.yaml", identifier="fixture/z")
    earlier = _write_descriptor(root, "a.yaml", identifier="fixture/a")

    index = _load([later, earlier], root)

    assert index.root == root.resolve()
    assert index.paths == (earlier.resolve(), later.resolve())
    assert tuple(index.fixtures) == ("fixture/a", "fixture/z")
    fixture = index.fixtures["fixture/a"]
    assert fixture.evaluator == EVALUATOR
    assert fixture.input_revision == "declaration-v1"
    assert fixture.sources == ((root / "resources/declaration.yaml").resolve(),)
    assert fixture.facet_registry == (root / "resources/facets.yaml").resolve()
    with pytest.raises(TypeError):
        index.fixtures["new"] = fixture  # type: ignore[index]
    with pytest.raises(TypeError):
        fixture.input["facet-registry"] = "other.yaml"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        fixture.id = "other"  # type: ignore[misc]


def test_schema_error_owns_unknown_field_and_source_line(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)

    def add_unknown(document: dict[str, object]) -> None:
        document["unexpected"] = True

    path = _write_descriptor(root, mutate=add_unknown)
    with pytest.raises(EvaluatorFixtureSchemaError) as captured:
        _load([path], root)
    assert captured.value.location == "$.unexpected"
    assert captured.value.line == _line_containing(path, "unexpected:")


def test_duplicate_descriptor_key_fails_at_yaml_boundary(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    path = root / "fixture.yaml"
    path.write_text(
        "schema-version: 1\nschema-version: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(EvaluatorFixtureSchemaError, match="duplicate key"):
        _load([path], root)


def test_duplicate_id_fails_at_the_later_lexical_descriptor(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    _write_descriptor(root, "a.yaml")
    later = _write_descriptor(root, "z.yaml")
    with pytest.raises(EvaluatorFixtureSemanticError) as captured:
        _load([later, root / "a.yaml"], root)
    assert captured.value.path == later.resolve()
    assert captured.value.location == "$.id"
    assert captured.value.line == 2


def test_duplicate_id_order_uses_canonical_descriptor_paths(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    canonical_later = _write_descriptor(root, "z.yaml")
    canonical_earlier = _write_descriptor(root, "b.yaml")
    alias = root / "a.yaml"
    try:
        os.symlink(canonical_later, alias)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(EvaluatorFixtureSemanticError) as captured:
        _load([alias, canonical_earlier], root)
    assert captured.value.path == canonical_later.resolve()
    assert captured.value.location == "$.id"


@pytest.mark.parametrize(
    "resource",
    ["../outside.yaml", "/absolute.yaml", "resources\\facets.yaml", "bad\x00path"],
)
def test_nonportable_resource_paths_fail_at_the_value(
    tmp_path: Path, resource: str
) -> None:
    root = _fixture_root(tmp_path)

    def change_path(document: dict[str, object]) -> None:
        input_data = document["input"]
        assert isinstance(input_data, dict)
        input_data["facet-registry"] = resource

    path = _write_descriptor(root, mutate=change_path)
    with pytest.raises(EvaluatorFixtureSemanticError) as captured:
        _load([path], root)
    assert captured.value.location == "$.input.facet-registry"
    assert captured.value.line == _line_containing(path, "facet-registry:")


def test_dot_and_repeated_separator_resource_spellings_are_admitted(
    tmp_path: Path,
) -> None:
    root = _fixture_root(tmp_path)

    def use_equivalent_paths(document: dict[str, object]) -> None:
        input_data = document["input"]
        assert isinstance(input_data, dict)
        input_data["sources"] = [
            "./resources//declaration.yaml",
            "resources/declaration.yaml",
        ]
        input_data["facet-registry"] = "./resources//facets.yaml"

    path = _write_descriptor(root, mutate=use_equivalent_paths)
    fixture = _load([path], root).fixtures["fixture/known-failure"]
    declaration = (root / "resources/declaration.yaml").resolve()
    assert fixture.sources == (declaration, declaration)
    assert fixture.facet_registry == (root / "resources/facets.yaml").resolve()


def test_unresolved_resource_fails_at_the_resource_value(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)

    def remove_target(document: dict[str, object]) -> None:
        input_data = document["input"]
        assert isinstance(input_data, dict)
        input_data["facet-registry"] = "resources/missing.yaml"

    path = _write_descriptor(root, mutate=remove_target)
    with pytest.raises(EvaluatorFixtureSemanticError) as captured:
        _load([path], root)
    assert captured.value.location == "$.input.facet-registry"
    assert captured.value.line == _line_containing(path, "facet-registry:")
    assert "does not resolve" in str(captured.value)


def test_symlinked_resource_cannot_escape_fixture_root(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path / "root")
    outside = tmp_path / "outside.yaml"
    outside.write_text("external: true\n", encoding="utf-8")
    link = root / "resources" / "outside.yaml"
    try:
        os.symlink(outside, link)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    def use_link(document: dict[str, object]) -> None:
        input_data = document["input"]
        assert isinstance(input_data, dict)
        input_data["facet-registry"] = "resources/outside.yaml"

    path = _write_descriptor(root, mutate=use_link)
    with pytest.raises(EvaluatorFixtureSemanticError, match="outside fixture root"):
        _load([path], root)


def test_symlink_loop_is_a_located_resource_error(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    loop = root / "resources" / "loop.yaml"
    try:
        os.symlink("loop.yaml", loop)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    def use_loop(document: dict[str, object]) -> None:
        input_data = document["input"]
        assert isinstance(input_data, dict)
        input_data["facet-registry"] = "resources/loop.yaml"

    path = _write_descriptor(root, mutate=use_loop)
    with pytest.raises(EvaluatorFixtureSemanticError) as captured:
        _load([path], root)
    assert captured.value.location == "$.input.facet-registry"
    assert captured.value.line == _line_containing(path, "facet-registry:")
    assert "does not resolve" in str(captured.value)


def test_descriptor_itself_must_remain_inside_fixture_root(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path / "root")
    outside_root = _fixture_root(tmp_path / "outside")
    path = _write_descriptor(outside_root)
    with pytest.raises(EvaluatorFixtureSemanticError) as captured:
        _load([path], root)
    assert captured.value.location == "$"
    assert "outside fixture root" in str(captured.value)


def test_missing_exact_input_contract_fails_at_evaluator(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)

    def add_missing_resource(document: dict[str, object]) -> None:
        input_data = document["input"]
        assert isinstance(input_data, dict)
        input_data["facet-registry"] = "resources/missing.yaml"

    path = _write_descriptor(root, mutate=add_missing_resource)
    with pytest.raises(EvaluatorFixtureSemanticError) as captured:
        load_evaluator_fixture_index([path], root=root, input_contracts={})
    assert captured.value.location == "$.evaluator"
    assert captured.value.line == _line_containing(path, "evaluator:")


def test_input_contract_failure_owns_deepest_input_path(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)

    def mistype_source(document: dict[str, object]) -> None:
        input_data = document["input"]
        assert isinstance(input_data, dict)
        input_data["sources"] = ["resources/missing.txt"]

    path = _write_descriptor(root, mutate=mistype_source)
    with pytest.raises(EvaluatorFixtureSemanticError) as captured:
        _load([path], root)
    assert captured.value.location == "$.input.sources[0]"
    assert captured.value.line == _line_containing(path, "missing.txt")
    assert "operation contract" in str(captured.value)
