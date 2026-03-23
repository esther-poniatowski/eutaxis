"""
Entry point for the `eutaxis` package, invoked as a module.

Usage
-----
To launch the command-line interface, execute::

    python -m eutaxis


See Also
--------
eutaxis.cli: Module implementing the application's command-line interface.
"""
from .cli import app

app()
