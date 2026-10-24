"""Validate and expand the graph of declared Skill loading units."""

from __future__ import annotations

from collections.abc import Iterable

from .exceptions import ConfigurationError
from .models import SkillLoadingMember, SkillLoadingUnit


def validate_loading_units(
    loading_units: Iterable[SkillLoadingUnit],
    module_ids: Iterable[str],
) -> None:
    """Reject loading units that name unknown modules or form cycles."""
    units = tuple(loading_units)
    known_modules = set(module_ids)
    units_by_name = {unit.name: unit for unit in units}

    for unit in units:
        unknown_modules = sorted(
            member.module
            for member in unit.members
            if member.module not in known_modules
        )
        if unknown_modules:
            raise ConfigurationError(
                f"Skill loading unit '{unit.name}' references unknown "
                f"task modules: {', '.join(unknown_modules)}"
            )

        unknown_includes = sorted(set(unit.includes) - units_by_name.keys())
        if unknown_includes:
            raise ConfigurationError(
                f"Skill loading unit '{unit.name}' includes unknown "
                f"units: {', '.join(unknown_includes)}"
            )

    visited: set[str] = set()
    active: list[str] = []

    def visit(name: str) -> None:
        if name in active:
            cycle = " -> ".join([*active[active.index(name) :], name])
            raise ConfigurationError(
                f"Skill loading units form a cycle: {cycle}"
            )
        if name in visited:
            return
        active.append(name)
        for included_name in units_by_name[name].includes:
            visit(included_name)
        active.pop()
        visited.add(name)

    for name in units_by_name:
        visit(name)


def expand_loading_unit(
    loading_unit: SkillLoadingUnit,
    loading_units: Iterable[SkillLoadingUnit],
) -> tuple[SkillLoadingMember, ...]:
    """Return the members declared by a loading unit and its included units.

    The configuration loader validates the graph first. Then,
    ``expand_loading_unit`` appends included units in declaration order.
    Downstream consumers deduplicate concrete files selected by overlapping
    members.
    """
    units_by_name = {unit.name: unit for unit in loading_units}
    members: list[SkillLoadingMember] = []

    def append_members(unit: SkillLoadingUnit) -> None:
        for included_name in unit.includes:
            append_members(units_by_name[included_name])
        members.extend(unit.members)

    append_members(loading_unit)
    return tuple(members)
