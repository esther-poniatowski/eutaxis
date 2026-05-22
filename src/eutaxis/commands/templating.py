"""Tiny, fail-closed ``{{ var }}`` substitution.

The engine accepts dotted names (``action.template``) and rejects any
identifier not present in the supplied context. It does not implement
conditionals, loops, or filters. Anything beyond bare substitution
should be handled by the caller before invocation.
"""

from __future__ import annotations

import re
from typing import Any

from .exceptions import TemplateError

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")


def render(template: str, context: dict[str, Any]) -> str:
    """Substitute ``{{ name }}`` placeholders against ``context``.

    Parameters
    ----------
    template : str
        Template string. Placeholders look like ``{{ name }}`` or
        ``{{ ns.name }}``. Whitespace inside the braces is tolerated.
    context : dict[str, Any]
        Variable context. Dotted names traverse nested mappings or
        attributes.

    Returns
    -------
    str
        The rendered string.

    Raises
    ------
    TemplateError
        If a placeholder references an unknown name.
    """

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        try:
            return str(_lookup(context, name))
        except KeyError as exc:
            raise TemplateError(
                f"Unknown template variable: {name!r} in {template!r}"
            ) from exc

    return _PLACEHOLDER.sub(replace, template)


def _lookup(context: dict[str, Any], dotted: str) -> Any:
    parts = dotted.split(".")
    cursor: Any = context
    for part in parts:
        if isinstance(cursor, dict) and part in cursor:
            cursor = cursor[part]
            continue
        if hasattr(cursor, part):
            cursor = getattr(cursor, part)
            continue
        raise KeyError(dotted)
    return cursor
