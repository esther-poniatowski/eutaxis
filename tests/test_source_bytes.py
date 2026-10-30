"""Exercise YAML parsing from already-retained byte evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from eutaxis.declarations.exceptions import DeclarationSchemaError
from eutaxis.declarations.source import load_yaml_bytes, load_yaml_document


def test_byte_and_path_entry_points_return_identical_evidence(tmp_path: Path) -> None:
    path = tmp_path / "declaration.yaml"
    source = b"schema-version: 1\nkind: rule\n"
    path.write_bytes(source)

    from_path = load_yaml_document(path)
    from_bytes = load_yaml_bytes(source, path=path)

    assert from_bytes == from_path
    assert from_bytes[2] == hashlib.sha256(source).hexdigest()
    assert from_bytes[1][("schema-version",)].line == 1
    assert from_bytes[1][("kind",)].line == 2


def test_byte_entry_point_never_reads_its_diagnostic_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "absent.yaml"

    def fail_read(_path: Path) -> bytes:
        raise AssertionError("diagnostic path was read")

    monkeypatch.setattr(Path, "read_bytes", fail_read)

    document, _locations, _digest = load_yaml_bytes(b"value: retained\n", path=path)
    assert document == {"value": "retained"}


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (b"value: \xff\n", "decode"),
        (b"value: first\nvalue: second\n", "duplicate key"),
        (b"", "source is empty"),
    ],
)
def test_byte_entry_point_preserves_public_parse_errors(
    tmp_path: Path, source: bytes, message: str
) -> None:
    path = tmp_path / "declaration.yaml"

    with pytest.raises(DeclarationSchemaError, match=message) as raised:
        load_yaml_bytes(source, path=path)

    assert raised.value.path == path


def test_byte_entry_point_rejects_bytes_subclasses_and_other_values(
    tmp_path: Path,
) -> None:
    class DerivedBytes(bytes):
        pass

    path = tmp_path / "declaration.yaml"
    for source in (DerivedBytes(b"value: derived\n"), "value: text\n"):
        with pytest.raises(DeclarationSchemaError, match="exact bytes"):
            load_yaml_bytes(source, path=path)  # type: ignore[arg-type]
