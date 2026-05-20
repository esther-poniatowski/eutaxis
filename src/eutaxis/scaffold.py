"""Prompt scaffolding helpers."""

from __future__ import annotations

from pathlib import Path
import shutil

from . import data_path


class ScaffoldError(RuntimeError):
    """Raised when a scaffold operation cannot be completed safely."""


def template_root() -> Path:
    """Return the packaged template root."""
    return data_path() / "templates"


def available_templates() -> list[str]:
    """Return available named scaffold template directories."""
    root = template_root()
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def scaffold_workspace(
    target: Path,
    *,
    template: str = "codex-project",
    force: bool = False,
) -> list[Path]:
    """Scaffold prompt-composition structure into a target project.

    Existing files are left untouched unless ``force`` is true.

    Parameters
    ----------
    target : Path
        Root of the target project.
    template : str
        Name of the template directory under ``eutaxis/data/templates``.
    force : bool
        Overwrite existing files when true.
    """
    source = template_root() / template
    if not source.is_dir():
        choices = ", ".join(available_templates()) or "<none>"
        raise ScaffoldError(f"Unknown template '{template}'. Available: {choices}")

    target = target.expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for source_path in sorted(path for path in source.rglob("*") if path.is_file()):
        relative = source_path.relative_to(source)
        target_path = target / relative

        if target_path.exists() and not force:
            raise ScaffoldError(
                f"Refusing to overwrite existing file: {target_path}. "
                "Use --force to overwrite."
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target_path)
        written.append(target_path)

    return written
