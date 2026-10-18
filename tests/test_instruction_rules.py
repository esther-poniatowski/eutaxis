"""Tests for the rule parser of instruction modules."""

from __future__ import annotations

from textwrap import dedent

from eutaxis.instructions.rules import (
    LABEL_PATTERN,
    HeadingBlock,
    RuleBlock,
    TextBlock,
    field_key,
    parse_module,
)

MODULE = dedent("""\
    ---
    name: sample
    description: Sample module.
    ---

    # Sample

    Module preamble.

    ## Register

    Section intro.

    **first-rule**:

    ✓ Do the first thing.
    ✗ Do not do the opposite.

    *Why the order matters.* Because the order is load-bearing.

    *Exceptions.* Quoted text is exempt.

    **second-rule**:

    Lead sentence of the second rule.

    ✓ Do the second thing.

    *Exception*: Titles are exempt.

    *Notes.* A plural note.

    ### Nested

    **third-rule**:

    ✓ Run the command.

    ```sh
    # not a heading
    **not-a-label**:
    ✓ not a statement
    ```

    *Why.* Plain rationale.

    *Precedence among the three rules.* The first wins.

    ## Other section

    Prose without labels.
    """)


def _parsed():
    return parse_module(MODULE, module="sample")


def test_labels_match_generator_grammar() -> None:
    parsed = _parsed()
    labels = [rule.label for rule in parsed.rules]
    assert labels == ["first-rule", "second-rule", "third-rule"]
    # The generator's whole-text scan also matches the label inside the
    # fenced block, which the parser treats as code.
    assert LABEL_PATTERN.findall(MODULE) == [*labels, "not-a-label"]


def test_rule_block_ends_at_next_label() -> None:
    first = _parsed().rule("first-rule")
    assert first is not None
    assert first.text.splitlines()[0] == "**first-rule**:"
    assert "second-rule" not in first.text
    assert first.text.splitlines()[-1] == "*Exceptions.* Quoted text is exempt."


def test_rule_block_ends_at_heading_and_records_heading_path() -> None:
    parsed = _parsed()
    second = parsed.rule("second-rule")
    third = parsed.rule("third-rule")
    assert second is not None and third is not None
    assert "Nested" not in second.text
    assert second.heading_path == ("Sample", "Register")
    assert third.heading_path == ("Sample", "Register", "Nested")
    assert "Other section" not in third.text
    assert "Prose without labels." not in third.text


def test_line_numbers_count_frontmatter() -> None:
    lines = MODULE.splitlines()
    first = _parsed().rule("first-rule")
    assert first is not None
    assert lines[first.start_line - 1] == "**first-rule**:"
    assert lines[first.end_line - 1] == "*Exceptions.* Quoted text is exempt."


def test_statements_and_fields_are_split() -> None:
    first = _parsed().rule("first-rule")
    assert first is not None
    assert first.valid == ("✓ Do the first thing.",)
    assert first.invalid == ("✗ Do not do the opposite.",)
    assert first.part_keys == ("valid", "invalid", "why", "exception")
    assert first.summary == "Do the first thing."


def test_plural_and_colon_markers_merge_with_singular_key() -> None:
    first = _parsed().rule("first-rule")
    second = _parsed().rule("second-rule")
    assert first is not None and second is not None
    assert first.parts_for("exception")[0].title == "Exceptions"
    assert second.parts_for("exception")[0].text == "*Exception*: Titles are exempt."
    assert second.parts_for("note")[0].title == "Notes"


def test_titled_why_variant_shares_the_why_key() -> None:
    first = _parsed().rule("first-rule")
    third = _parsed().rule("third-rule")
    assert first is not None and third is not None
    assert first.parts_for("why")[0].title == "Why the order matters"
    assert third.parts_for("why")[0].title == "Why"


def test_other_titled_paragraph_is_keyed_by_slug() -> None:
    third = _parsed().rule("third-rule")
    assert third is not None
    assert "precedence-among-the-three-rules" in third.part_keys


def test_missing_field_yields_no_part() -> None:
    second = _parsed().rule("second-rule")
    assert second is not None
    assert second.parts_for("test") == ()
    assert "why" not in second.fields


def test_lead_text_before_first_statement() -> None:
    second = _parsed().rule("second-rule")
    assert second is not None
    assert second.parts_for("lead")[0].text == "Lead sentence of the second rule."


def test_fenced_code_is_opaque() -> None:
    parsed = _parsed()
    third = parsed.rule("third-rule")
    assert third is not None
    assert parsed.rule("not-a-label") is None
    assert "# not a heading" in third.text
    assert third.valid == (
        "✓ Run the command.\n\n```sh\n# not a heading\n**not-a-label**:\n"
        "✓ not a statement\n```",
    )
    headings = [b.text for b in parsed.blocks if isinstance(b, HeadingBlock)]
    assert "not a heading" not in headings


def test_blocks_cover_text_outside_rules() -> None:
    parsed = _parsed()
    texts = ["\n".join(b.lines) for b in parsed.blocks if isinstance(b, TextBlock)]
    assert any("Module preamble." in text for text in texts)
    assert any("Section intro." in text for text in texts)
    assert any("Prose without labels." in text for text in texts)
    assert sum(isinstance(b, RuleBlock) for b in parsed.blocks) == 3


def test_rejected_label_lines_are_reported_and_end_the_previous_rule() -> None:
    text = dedent("""\
        **kept-rule**:

        ✓ Keep this.

        **3d-plots**:

        Text of a rule with a rejected label.

         **indented-rule**:

        More text.
        """)
    parsed = parse_module(text, module="m")
    assert [rule.label for rule in parsed.rules] == ["kept-rule"]
    kept = parsed.rule("kept-rule")
    assert kept is not None and "3d-plots" not in kept.text
    assert [(r.token, r.line_number) for r in parsed.rejected] == [
        ("3d-plots", 5),
        ("indented-rule", 9),
    ]
    assert "lowercase letter" in parsed.rejected[0].reason
    assert "indented" in parsed.rejected[1].reason


def test_bold_lead_in_with_text_is_not_a_label_line() -> None:
    parsed = parse_module("**Constraint**: inline text.\n", module="m")
    assert parsed.rules == () and parsed.rejected == ()


def test_summary_falls_back_to_first_part() -> None:
    parsed = parse_module("**plain**:\n\nPlain prose rule.\n", module="m")
    assert parsed.rules[0].summary == "Plain prose rule."


def test_field_key_normalization() -> None:
    assert field_key("Why, and this is the trap") == "why"
    assert field_key("Notes") == "note"
    assert field_key("Test for the given–new order") == "test"
    assert field_key("Full rule") == "full-rule"
