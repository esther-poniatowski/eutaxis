from __future__ import annotations

import pytest

from eutaxis.commands.exceptions import TemplateError
from eutaxis.commands.templating import render


def test_substitutes_flat_variables() -> None:
    assert render("hello {{ name }}", {"name": "world"}) == "hello world"


def test_substitutes_dotted_variables_through_dicts() -> None:
    out = render("run {{ action.template }}", {"action": {"template": "go"}})
    assert out == "run go"


def test_tolerates_whitespace_inside_braces() -> None:
    assert render("{{  x  }}", {"x": 1}) == "1"


def test_unknown_variable_raises() -> None:
    with pytest.raises(TemplateError):
        render("{{ missing }}", {})


def test_unknown_dotted_segment_raises() -> None:
    with pytest.raises(TemplateError):
        render("{{ a.b }}", {"a": {}})
