"""
Registry validation module.

Validates machine-readable project state (reasoning graphs, open questions,
terminology registries, dependencies) against JSON schemas shipped with
the eutaxis governance data.

This module is a stub. Implementation will follow once the JSON schemas
in ``data/governance/schemas/`` are stabilized.
"""

from __future__ import annotations

from pathlib import Path


def validate_registry(registry_path: Path, schema_path: Path | None = None) -> list[str]:
    """Validate a registry file against its schema.

    Parameters
    ----------
    registry_path : Path
        Path to the YAML registry file to validate.
    schema_path : Path or None
        Path to the JSON schema. If None, the schema is inferred
        from the registry filename using the default schemas in
        ``data/governance/schemas/``.

    Returns
    -------
    list of str
        List of validation error messages. Empty if valid.
    """
    _ = schema_path  # placeholder
    if not registry_path.exists():
        return [f"Registry file not found: {registry_path}"]
    return []
