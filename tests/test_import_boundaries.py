"""Regression tests for dependency-neutral public imports."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_instruction_rule_parser_imports_in_fresh_interpreter() -> None:
    """The parser must not depend on another package's import order."""
    source_root = Path(__file__).parents[1] / "src"
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.path.insert(0, {str(source_root)!r}); "
            "from eutaxis.instructions.rules import RULE_PARSER_CONTRACT, parse_module; "
            "assert not any(name == 'eutaxis.declarations' or "
            "name.startswith('eutaxis.declarations.') for name in sys.modules); "
            "assert RULE_PARSER_CONTRACT == "
            "'eutaxis.instructions.rules.parse_module@1'; "
            "assert parse_module('**example**:\\n', module='test').rules[0].label "
            "== 'example'",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
