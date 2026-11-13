"""Validate and expand the graph of declared Skill loading units."""

from __future__ import annotations

from collections.abc import Iterable

from .exceptions import ConfigurationError
from .models import RequiredLoadingRoute, SkillLoadingMember, SkillLoadingUnit


def validate_loading_units(
    loading_units: Iterable[SkillLoadingUnit],
    module_ids: Iterable[str],
    required_routes: Iterable[RequiredLoadingRoute] = (),
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
            raise ConfigurationError(f"Skill loading units form a cycle: {cycle}")
        if name in visited:
            return
        active.append(name)
        for included_name in units_by_name[name].includes:
            visit(included_name)
        active.pop()
        visited.add(name)

    for name in units_by_name:
        visit(name)

    for unit in units:
        if unit.publish_to is None:
            continue
        if unit.publish_to not in known_modules:
            raise ConfigurationError(
                f"Skill loading unit '{unit.name}' publishes to unknown "
                f"task module: {unit.publish_to}"
            )
        owner_members = [
            member
            for member in expand_loading_unit(unit, units)
            if member.module == unit.publish_to and member.include_entrypoint
        ]
        if not owner_members:
            raise ConfigurationError(
                f"Skill loading unit '{unit.name}' must include the entrypoint "
                f"of its publication owner '{unit.publish_to}'"
            )

    for requirement in required_routes:
        required_unit = units_by_name.get(requirement.name)
        if required_unit is None:
            raise ConfigurationError(
                f"Required loading route '{requirement.name}' is not declared"
            )
        if required_unit.publish_to != requirement.owner:
            actual = required_unit.publish_to or "unpublished"
            raise ConfigurationError(
                f"Required loading route '{requirement.name}' must publish to "
                f"'{requirement.owner}', not '{actual}'"
            )


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
