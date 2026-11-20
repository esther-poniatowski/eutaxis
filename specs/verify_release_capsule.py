"""Verify the draft release records against a read-only byte store."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from eutaxis.declarations.acquisition_paths import normalized_relative_path
from eutaxis.declarations.canonical_json import jcs_bytes, parse_canonical_json_bytes

ACQUISITION_FIELDS = (
    "acquisition-manifest",
    "acquisition-lock",
    "workspace-files",
    "packaged-source-revision",
    "distribution-revision",
)


def _digest(content: bytes) -> str:
    """Address one exact byte sequence."""
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _read(blobs: Mapping[str, bytes], address: str) -> bytes:
    """Read bytes and check their address."""
    try:
        content = blobs[address]
    except KeyError as error:
        raise ValueError(f"Missing stored bytes for {address}") from error
    if type(content) is not bytes or _digest(content) != address:
        raise ValueError(f"Stored bytes differ from {address}")
    return content


def _object(content: bytes) -> dict[str, Any]:
    """Require a canonical JSON object."""
    value = parse_canonical_json_bytes(content)
    if not isinstance(value, dict):
        raise ValueError("Expected a canonical JSON object")
    return value


def _load_record(
    blobs: Mapping[str, bytes], address: str, record: str
) -> dict[str, Any]:
    """Validate a content-addressed draft record."""
    name = f"declaration-{record}-v1.draft.schema.json"
    schema = json.loads(Path(__file__).with_name(name).read_text(encoding="utf-8"))
    value = _object(_read(blobs, address))
    Draft202012Validator(schema).validate(value)
    return value


def _read_targets(
    blobs: Mapping[str, bytes], address: str, *, require_present: bool
) -> dict[str, str | None]:
    """Verify target names and each present artifact reference."""
    targets = _object(_read(blobs, address))
    for target, state in targets.items():
        normalized_relative_path(target, allow_dot=False)
        if isinstance(state, str):
            _read(blobs, state)
        elif state is not None or require_present:
            raise ValueError(f"Invalid artifact state for {target}")
    return targets


def _verify_acquisition(
    blobs: Mapping[str, bytes], capsule: dict[str, Any], address: str
) -> None:
    """Bind the reviewed acquisition record to the capsule and its bytes."""
    authorization = {field: capsule[field] for field in ACQUISITION_FIELDS}
    if _read(blobs, address) != jcs_bytes(authorization):
        raise ValueError("Review acquisition does not bind the capsule sources")
    for field in ("acquisition-manifest", "acquisition-lock"):
        entry = capsule[field]
        normalized_relative_path(entry["path"], allow_dot=False)
        _read(blobs, entry["sha256"])
    for path, digest in capsule["workspace-files"].items():
        normalized_relative_path(path, allow_dot=False)
        _read(blobs, digest)


def _verify_review_binding(
    blobs: Mapping[str, bytes], capsule: dict[str, Any]
) -> dict[str, Any]:
    """Verify the review against the capsule without its review digest."""
    review = _load_record(blobs, capsule["review-packet"], "review")
    binding = {key: value for key, value in capsule.items() if key != "review-packet"}
    if _digest(jcs_bytes(binding)) != review["candidate-binding"]:
        raise ValueError("Review does not bind the candidate capsule")
    return review


def verify_capsule(blobs: Mapping[str, bytes], address: str) -> None:
    """Check canonical records, bound bytes, and complete targets by address.

    The caller supplies the reviewed capsule address and a read-only byte store.
    """
    capsule = _load_record(blobs, address, "release")
    review = _verify_review_binding(blobs, capsule)
    semantics = review["semantics"]
    acquisition = review["acquisition"]
    artifacts = review["artifacts"]
    _verify_acquisition(blobs, capsule, acquisition["candidate"])
    _read(blobs, semantics["candidate"])
    baseline = _read_targets(blobs, artifacts["baseline"], require_present=False)
    outputs = _read_targets(blobs, artifacts["candidate"], require_present=True)
    predecessor = capsule["predecessor"]
    if predecessor is None:
        initial = capsule["initial-baseline"]
        if semantics["kind"] != "initial" or (
            semantics["accountability-ledger"] != initial["accountability-ledger"]
        ):
            raise ValueError("Review does not bind the initial accountability ledger")
        if baseline != initial["golden-targets"]:
            raise ValueError("Review does not bind the golden baseline targets")
        if semantics["accountability-ledger"] is not None:
            _read(blobs, semantics["accountability-ledger"])
    else:
        prior_capsule = _load_record(blobs, predecessor, "release")
        prior_review = _verify_review_binding(blobs, prior_capsule)
        if semantics["kind"] != "successor" or (
            semantics["baseline"] != prior_review["semantics"]["candidate"]
        ):
            raise ValueError("Review does not bind predecessor semantics")
        if acquisition["baseline"] != prior_review["acquisition"]["candidate"]:
            raise ValueError("Review does not bind predecessor acquisition")
        if baseline != prior_capsule["managed-targets"]:
            raise ValueError("Review does not bind predecessor targets")
        _read(blobs, semantics["baseline"])
        _read(blobs, semantics["differences"])
    if acquisition["baseline"] is not None:
        _read(blobs, acquisition["baseline"])
    expected_targets = dict.fromkeys(baseline) | outputs
    if capsule["managed-targets"] != expected_targets:
        raise ValueError(
            "Managed targets must include every prior and candidate target"
        )
