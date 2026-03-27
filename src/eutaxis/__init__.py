"""
Initialization logic and public interface for the `eutaxis` package.

Eutaxis is a domain-agnostic quality validation framework. It provides a linting
engine, instruction-file generation, registry validation, and workspace scaffolding.
Domain content (rules, audit prompts, standards, templates) is organized under
`data/domains/` and selected per project via the `domain` configuration field.

Bundled domain packages:

- ``software``: design principles, writing standards, audit prompts, AI agent templates.
- ``math``: mathematical writing lint rules and audit prompts.
- ``pedagogy``: stub for future development.

Variables
---------
__version__ : str, default "0.0.0+unknown"
    Version of the package. If the package metadata is unavailable (e.g. in editable or source-only
    environments), a fallback value is provided (PEP 440 compliant).
__all__ : list
    Public objects exposed by this package.

Functions
---------
info() -> str
    Format diagnostic information about the package and platform.
data_path() -> Path
    Return the absolute path to the package data directory.
domain_path(domain) -> Path
    Return the absolute path to a specific domain directory under ``data/domains/``.
"""
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import platform

try:
    if __package__ is None:  # erroneous script execution
        raise PackageNotFoundError
    __version__ = version(__package__)
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = ["info", "data_path", "domain_path", "__version__"]


def info() -> str:
    """Format diagnostic information on package and platform."""
    return f"{__package__} {__version__} | Platform: {platform.system()} Python {platform.python_version()}"


def data_path() -> Path:
    """Return the absolute path to the package data directory.

    This path can be used both when eutaxis is installed as a package
    and when it is included as a Git submodule.
    """
    return Path(__file__).parent / "data"


def domain_path(domain: str) -> Path:
    """Return the absolute path to a domain directory.

    Parameters
    ----------
    domain
        Name of the domain (e.g. ``"math"``, ``"software"``, ``"pedagogy"``).

    Returns
    -------
    Path
        Absolute path to ``data/domains/<domain>/``.

    Raises
    ------
    ValueError
        If the requested domain directory does not exist.
    """
    path = data_path() / "domains" / domain
    if not path.is_dir():
        available = [p.name for p in (data_path() / "domains").iterdir() if p.is_dir()]
        raise ValueError(
            f"Domain '{domain}' not found. Available domains: {', '.join(sorted(available))}."
        )
    return path
