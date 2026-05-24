# Top-Level Entry Points

User-facing commands invoked from the CLI: generate instruction files, validate configuration, scaffold a new project, and the CLI dispatcher itself.

## CLI

```{eval-rst}
.. automodule:: eutaxis.cli
   :members:
   :undoc-members:
   :show-inheritance:
```

## Generate

`eutaxis.generate` is a thin backward-compatibility shim that re-exports
the public surface of `eutaxis.instructions`. Only the module's own
entry point is documented here; the re-exported classes appear under
[Instructions](instructions.md).

```{eval-rst}
.. autofunction:: eutaxis.generate.main
```

## Validate

```{eval-rst}
.. automodule:: eutaxis.validate
   :members:
   :undoc-members:
   :show-inheritance:
```

## Scaffold

```{eval-rst}
.. automodule:: eutaxis.scaffold
   :members:
   :undoc-members:
   :show-inheritance:
```
