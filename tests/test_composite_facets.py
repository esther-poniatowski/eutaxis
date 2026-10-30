"""Exercise the packaged composite facet authority and its diagnostics."""

from __future__ import annotations

import copy
import pickle
from collections.abc import Mapping
from types import MappingProxyType

import pytest

import eutaxis.declarations as declarations
import eutaxis.declarations.composite_facets as composite_facets
from eutaxis.declarations import (
    AcquisitionContractError,
    CompositeFacetRegistry,
    FacetContextError,
    composite_facet_content_revision,
    load_declaration_registry,
)
from eutaxis.declarations.composite_facets import (
    COMPOSITE_FACET_REGISTRY_ID,
    _is_issued_composite_facet_registry,
    _issue_composite_facet_registry,
)
from eutaxis.declarations.packaged_source import _issued_packaged_facet_state
from tests._facet_authority import issue_test_composite, packaged_lock, packaged_source


def test_composite_retains_exact_packaged_authority() -> None:
    packaged = packaged_source()
    composite = _issue_composite_facet_registry(packaged)
    base = packaged.facet_registry

    assert _is_issued_composite_facet_registry(composite)
    assert composite.schema_version == 1
    assert composite.id == COMPOSITE_FACET_REGISTRY_ID
    assert composite.constituents == (base,)
    assert composite.constituents[0] is base
    assert composite.facets["artifact.created"] is base.facets["artifact.created"]
    assert composite.authority_for("artifact.created") is base
    assert composite.content_revision == composite_facet_content_revision(
        packaged.facet_content_revision,
        (),
    )
    assert not hasattr(composite, "owner")


def test_composite_rejects_construction_copying_and_serialization() -> None:
    composite = issue_test_composite()

    with pytest.raises(TypeError, match="must be issued"):
        CompositeFacetRegistry()
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.copy(composite)
    with pytest.raises(TypeError, match="cannot be copied"):
        copy.deepcopy(composite)
    with pytest.raises(TypeError, match="cannot be serialized"):
        pickle.dumps(composite)
    assert not hasattr(declarations, "_issue_composite_facet_registry")


def test_public_packaged_acquisition_issues_the_composite() -> None:
    composite = declarations.acquire_packaged_composite_facet_registry(packaged_lock())

    assert _is_issued_composite_facet_registry(composite)
    assert composite.constituents[0].id == "eutaxis/context-facets"


def test_composite_rejects_raw_or_altered_packaged_source() -> None:
    with pytest.raises(AcquisitionContractError, match="wrong exact type"):
        _issue_composite_facet_registry(object())

    packaged = packaged_source()
    object.__setattr__(packaged.facet_registry, "facets", MappingProxyType({}))
    with pytest.raises(AcquisitionContractError, match="registry state changed"):
        _issue_composite_facet_registry(packaged)

    packaged = packaged_source()
    _evidence, lock, _registry = _issued_packaged_facet_state(packaged)
    object.__setattr__(lock, "content_revision", "sha256:" + "f" * 64)
    with pytest.raises(AcquisitionContractError, match="lock state changed"):
        _issue_composite_facet_registry(packaged)


def test_equal_composites_retain_distinct_issuance_authority() -> None:
    first = issue_test_composite()
    second = issue_test_composite()

    assert first is not second
    assert first.facets == second.facets
    assert first.content_revision == second.content_revision
    assert _is_issued_composite_facet_registry(first)
    assert _is_issued_composite_facet_registry(second)


def test_composite_rejects_forgery_and_equal_value_mapping_replacement() -> None:
    composite = issue_test_composite()
    forged = object.__new__(CompositeFacetRegistry)
    for name in (
        "schema_version",
        "id",
        "constituents",
        "facets",
        "facet_authorities",
        "content_revision",
    ):
        object.__setattr__(forged, name, getattr(composite, name))

    with pytest.raises(AcquisitionContractError, match="not issued"):
        load_declaration_registry((), forged)

    object.__setattr__(composite, "facets", MappingProxyType(dict(composite.facets)))
    assert not _is_issued_composite_facet_registry(composite)
    with pytest.raises(AcquisitionContractError, match="not issued"):
        composite.require_authority()


def test_composite_authority_binds_nested_constituent_state() -> None:
    composite = issue_test_composite()
    facet = composite.constituents[0].facets["artifact.created"]

    object.__setattr__(
        facet, "value_schema", MappingProxyType(dict(facet.value_schema))
    )

    assert not _is_issued_composite_facet_registry(composite)
    with pytest.raises(AcquisitionContractError, match="not issued"):
        composite.require_authority()


def test_nested_context_value_cannot_apply_an_aba_schema() -> None:
    composite = issue_test_composite()
    facet = composite.facets["artifact.created"]
    original_schema = facet.value_schema

    class SchemaSwitchingValue(Mapping):
        calls = 0

        def __getitem__(self, key):
            raise KeyError(key)

        def __iter__(self):
            return iter(())

        def __len__(self):
            return 0

        def items(self):
            type(self).calls += 1
            schema = (
                MappingProxyType({"type": "object"})
                if self.calls == 1
                else original_schema
            )
            object.__setattr__(facet, "value_schema", schema)
            return {}.items()

    with pytest.raises(FacetContextError, match="boolean"):
        composite.validate_context({"artifact.created": SchemaSwitchingValue()})
    composite.require_authority()


def test_context_rejects_hostile_primitive_subclasses_before_lookup() -> None:
    composite = issue_test_composite()

    class HostileKey(str):
        armed = False

        def __hash__(self):
            if self.armed:
                raise RuntimeError("hostile key was hashed")
            return super().__hash__()

    key = HostileKey("artifact.created")
    context = {key: True}
    key.armed = True

    with pytest.raises(FacetContextError, match="exact strings"):
        composite.validate_context(context)
    composite.require_authority()

    hostile_values = (
        HostileKey("true"),
        type("HostileInt", (int,), {})(1),
        type("HostileFloat", (float,), {})(1.0),
    )
    for value in hostile_values:
        with pytest.raises(FacetContextError, match="finite JSON value"):
            composite.validate_context({"artifact.created": value})


def test_composite_retires_interrupted_publication(monkeypatch) -> None:
    packaged = packaged_source()
    attempted: list[CompositeFacetRegistry] = []
    retired: list[CompositeFacetRegistry] = []
    original_retire = composite_facets._COMPOSITE_AUTHORITIES.retire

    def interrupt(value, _state):
        attempted.append(value)
        raise KeyboardInterrupt

    def retire(value):
        retired.append(value)
        return original_retire(value)

    monkeypatch.setattr(composite_facets._COMPOSITE_AUTHORITIES, "issue", interrupt)
    monkeypatch.setattr(composite_facets._COMPOSITE_AUTHORITIES, "retire", retire)

    with pytest.raises(KeyboardInterrupt):
        _issue_composite_facet_registry(packaged)

    assert retired == attempted


def test_composite_diagnostics_identify_composite_and_constituent() -> None:
    composite = issue_test_composite()

    with pytest.raises(FacetContextError, match="eutaxis/context-facets"):
        composite.validate_context({"artifact.created": "invalid"})
    with pytest.raises(FacetContextError, match=COMPOSITE_FACET_REGISTRY_ID):
        composite.validate_context({"unknown.facet": True})
