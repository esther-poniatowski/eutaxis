"""Prepare Skill synchronization plans from instruction configurations."""

from __future__ import annotations

from collections.abc import Collection
from pathlib import Path

from ..instructions import load_config
from .adapters import AgentAdapter
from .loader import load_from_instruction_config
from .loading_unit_publication import (
    order_published_skill_sources,
    prepare_published_loading_units,
)
from .synchronization import (
    PreparedSkillSync,
    SkillSyncManifest,
    prepare_skill_sync,
)


def prepare_configured_skill_sync(
    config_path: Path,
    adapters: list[AgentAdapter],
    *,
    scope: str,
    root: Path,
    project_root: Path,
    home: Path,
    state_dir: Path,
) -> PreparedSkillSync:
    """Prepare the complete ordered Skill plan declared by a configuration.

    This function reads configuration, source, manifest, and installed Skill
    state without modifying any of them. A caller that will apply the result
    must hold the synchronization-manifest lock across this call and the
    subsequent application.
    """
    config = load_config(config_path, root=root)
    sources = load_from_instruction_config(config_path, root=root)
    published, _ = prepare_published_loading_units(
        config,
        sources,
        adapters,
        project_root=project_root,
        home=home,
    )
    ordered = order_published_skill_sources(config, published)
    manifest = SkillSyncManifest(state_dir, config_path)
    managed_names: dict[str, Collection[str]] = {
        adapter.name: manifest.managed_names(
            adapter=adapter.name,
            scope=scope,
            project_root=project_root,
        )
        for adapter in adapters
    }
    protected_names: dict[str, Collection[str]] = {
        adapter.name: manifest.names_managed_by_other_configs(
            adapter=adapter.name,
            scope=scope,
            project_root=project_root,
        )
        for adapter in adapters
    }
    return prepare_skill_sync(
        ordered,
        adapters,
        scope=scope,
        project_root=project_root,
        home=home,
        managed_names_by_adapter=managed_names,
        protected_names_by_adapter=protected_names,
    )
