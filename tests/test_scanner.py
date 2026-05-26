from __future__ import annotations

from pathlib import Path

from eutaxis.instructions import load_config, scan_instructions


def _write_config(tmp_path: Path, body: str) -> Path:
    config = tmp_path / "agent-instructions.yaml"
    config.write_text(body.lstrip(), encoding="utf-8")
    return config


def test_scan_reports_unregistered_files(tmp_path: Path) -> None:
    (tmp_path / "instructions").mkdir()
    (tmp_path / "instructions" / "registered.md").write_text(
        "---\ndescription: r\n---\n# r\n", encoding="utf-8"
    )
    (tmp_path / "instructions" / "extra.md").write_text(
        "---\ndescription: extra\n---\n# extra\n", encoding="utf-8"
    )

    config = _write_config(
        tmp_path,
        """
common_sources:
  - instructions/registered.md
agents:
  - name: codex
    target: AGENTS.md
""",
    )

    loaded = load_config(config)
    report = scan_instructions(loaded)

    registered = {p.name for p in report.registered_present}
    unregistered = {p.name for p in report.unregistered_present}
    assert registered == {"registered.md"}
    assert unregistered == {"extra.md"}
    assert report.registered_missing == []


def test_scan_honors_enabled_false_frontmatter(tmp_path: Path) -> None:
    (tmp_path / "instructions").mkdir()
    (tmp_path / "instructions" / "registered.md").write_text(
        "---\ndescription: r\n---\n# r\n", encoding="utf-8"
    )
    (tmp_path / "instructions" / "draft.md").write_text(
        "---\ndescription: d\nenabled: false\n---\n# draft\n",
        encoding="utf-8",
    )

    config = _write_config(
        tmp_path,
        """
common_sources:
  - instructions/registered.md
agents:
  - name: codex
    target: AGENTS.md
""",
    )

    report = scan_instructions(load_config(config))

    assert report.unregistered_present == []
    assert not report.has_issues


def test_scan_reports_registered_missing(tmp_path: Path) -> None:
    (tmp_path / "instructions").mkdir()
    (tmp_path / "instructions" / "exists.md").write_text(
        "---\ndescription: e\n---\n# e\n", encoding="utf-8"
    )

    config = _write_config(
        tmp_path,
        """
common_sources:
  - instructions/exists.md
  - instructions/missing.md
agents:
  - name: codex
    target: AGENTS.md
""",
    )

    # The loader does not require sources to exist at load time, but the
    # scan reports them as missing.
    report = scan_instructions(load_config(config))

    missing_names = {p.name for p in report.registered_missing}
    assert missing_names == {"missing.md"}
    assert report.has_issues


def test_scan_reports_malformed_frontmatter(tmp_path: Path) -> None:
    (tmp_path / "instructions").mkdir()
    (tmp_path / "instructions" / "registered.md").write_text(
        "---\ndescription: r\n---\n# r\n", encoding="utf-8"
    )
    (tmp_path / "instructions" / "broken.md").write_text(
        "---\nkey: : :::\n  bad\n---\n# broken\n", encoding="utf-8"
    )

    config = _write_config(
        tmp_path,
        """
common_sources:
  - instructions/registered.md
agents:
  - name: codex
    target: AGENTS.md
""",
    )

    report = scan_instructions(load_config(config))

    assert len(report.frontmatter_errors) == 1
    assert report.frontmatter_errors[0][0].name == "broken.md"


def test_scan_root_override(tmp_path: Path) -> None:
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "stray.md").write_text(
        "---\ndescription: stray\n---\n# stray\n", encoding="utf-8"
    )
    (tmp_path / "instructions").mkdir()
    (tmp_path / "instructions" / "registered.md").write_text(
        "---\ndescription: r\n---\n# r\n", encoding="utf-8"
    )

    config = _write_config(
        tmp_path,
        """
common_sources:
  - instructions/registered.md
agents:
  - name: codex
    target: AGENTS.md
""",
    )

    report = scan_instructions(load_config(config), root=tmp_path / "other")

    unregistered = {p.name for p in report.unregistered_present}
    assert unregistered == {"stray.md"}


def test_scan_clean_on_fully_registered_config(tmp_path: Path) -> None:
    (tmp_path / "instructions").mkdir()
    (tmp_path / "instructions" / "a.md").write_text(
        "---\ndescription: a\n---\n# a\n", encoding="utf-8"
    )
    (tmp_path / "instructions" / "b.md").write_text(
        "---\ndescription: b\n---\n# b\n", encoding="utf-8"
    )

    config = _write_config(
        tmp_path,
        """
common_sources:
  - instructions/a.md
  - instructions/b.md
agents:
  - name: codex
    target: AGENTS.md
""",
    )

    report = scan_instructions(load_config(config))

    assert not report.has_issues
    assert len(report.registered_present) == 2
