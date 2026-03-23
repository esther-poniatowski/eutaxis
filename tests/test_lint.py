"""Basic tests for the eutaxis lint module."""

from pathlib import Path

from eutaxis.lint import LintConfig, lint_file, is_trivial_inline_equality


def test_trivial_equality_numeric():
    assert is_trivial_inline_equality("d = 2")


def test_trivial_equality_identifier():
    assert is_trivial_inline_equality("j = k")


def test_trivial_chained_equality():
    assert is_trivial_inline_equality(r"\alpha_1 = \alpha_2 = 1/2")


def test_nontrivial_equality():
    assert not is_trivial_inline_equality(r"x = \frac{a}{b}")


def test_config_disables_rule(tmp_path):
    md = tmp_path / "test.md"
    md.write_text("We show that this works.\n")

    issues_default = lint_file(md)
    assert any(i.rule == "first_person" for i in issues_default)

    config = LintConfig(disabled_rules={"first_person"})
    issues_disabled = lint_file(md, config=config)
    assert not any(i.rule == "first_person" for i in issues_disabled)


def test_imperative_detection(tmp_path):
    md = tmp_path / "test.md"
    md.write_text("Define $X$ as the set of all solutions.\n")

    issues = lint_file(md)
    assert any(i.rule == "imperative" for i in issues)


def test_display_punctuation(tmp_path):
    md = tmp_path / "test.md"
    md.write_text("The result satisfies:\n$$\nx = 1.\n$$\n")

    issues = lint_file(md)
    assert any(i.rule == "display_punctuation" for i in issues)
