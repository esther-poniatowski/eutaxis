"""
Initialization logic and public interface for the `eutaxis` package.

Eutaxis composes and validates structured agent prompts. It provides reusable
prompt templates, prompt-authoring guidance, instruction-file generation, and
scaffolding hooks for projects that maintain their own domain rules elsewhere.

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

__all__ = ["info", "data_path", "__version__"]


def info() -> str:
    """Format diagnostic information on package and platform."""
    return f"{__package__} {__version__} | Platform: {platform.system()} Python {platform.python_version()}"


def data_path() -> Path:
    """Return the absolute path to the package data directory.

    This path exposes packaged prompt templates and related reference data.
    """
    return Path(__file__).parent / "data"
