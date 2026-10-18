"""Query individual rules of instruction modules and deployed skills.

The package answers one question: what does the rule labelled ``<label>``
state, in full or in one of its parts. It reads the modules that an
instruction-assembly configuration declares, or the skills deployed in a
skills directory, and resolves a label to one rule record of
:mod:`eutaxis.instructions.rules`.

Public objects
--------------
RuleCatalog, LocatedRule, LocatedRejection
    Rules collected from one source, located at their files.
catalog_from_config, catalog_from_skills_dir
    Build a catalog from authored modules or from deployed skills.
resolve_rule, select_parts
    Resolve a label to one rule and a part name to its parts.
RuleQueryError, RuleSourceError, UnknownRuleError, AmbiguousRuleError, UnknownPartError
    Exception hierarchy.
"""

from .catalog import (
    LocatedRejection,
    LocatedRule,
    RuleCatalog,
    resolve_rule,
    select_parts,
)
from .exceptions import (
    AmbiguousRuleError,
    RuleQueryError,
    RuleSourceError,
    UnknownPartError,
    UnknownRuleError,
)
from .sources import catalog_from_config, catalog_from_skills_dir

__all__ = [
    "AmbiguousRuleError",
    "LocatedRejection",
    "LocatedRule",
    "RuleCatalog",
    "RuleQueryError",
    "RuleSourceError",
    "UnknownPartError",
    "UnknownRuleError",
    "catalog_from_config",
    "catalog_from_skills_dir",
    "resolve_rule",
    "select_parts",
]
