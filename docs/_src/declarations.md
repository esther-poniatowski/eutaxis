# Declarations

External declaration acquisition: verifies one external corpus and exposes its portable source coordinates and exact support resources through an authenticated result.

## External acquisition result

```{eval-rst}
.. automodule:: eutaxis.declarations.external_result
   :members: AcquiredResource, AcquisitionSourceCoordinate, ExternalAcquisitionResult, acquire_external_declarations, acquire_external_declarations_from_path
   :show-inheritance:
```

## External resolution

```{eval-rst}
.. automodule:: eutaxis.declarations.external_resolution
   :members: ExternalResolutionResult, resolve_external_compilation_unit
   :show-inheritance:
```

## External cumulative composition

```{eval-rst}
.. automodule:: eutaxis.declarations.external_composition
   :members: ExternalCumulativeArtifact, ExternalCumulativeCompositionPlan, assemble_external_cumulative_artifact, plan_external_cumulative_composition
   :show-inheritance:
```

## Declaration catalog

```{eval-rst}
.. automodule:: eutaxis.declarations.catalog
   :members: CATALOG_INDEX_REVISION, CatalogSource, DeclarationCatalog, ExactContractKey, build_declaration_catalog, catalog_json_bytes
   :show-inheritance:
```

## Persisted catalog

```{eval-rst}
.. automodule:: eutaxis.declarations.persisted_catalog
   :members: PersistedCatalogEntry, PersistedCatalogIndex, PersistedCatalogProvenance, PersistedCatalogRelation, load_persisted_catalog_index
   :show-inheritance:
```

## Catalog schema

```{eval-rst}
.. automodule:: eutaxis.declarations.catalog_schema
   :members: catalog_index_schema, catalog_index_schema_path
```
