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

## Query packets

Completed external resolutions can be detached as canonical JSON query packets. Each packet records the normalized context, certified unit, complete declaration record and selection outcome of every compilation candidate, the manifest, rule-set and policy control closure, the active decision dependencies of effective rules, the exact typed evaluator and operation contract closure of the effective declarations, acquired support resources, resolver trace, portable source coordinates, acquisition-derived record locations and normalized content digests, hashes, and content revisions. The validator uses this index to bind each candidate, control, decision and contract to the acquired file, document path and normalized record body that declared it. It also rechecks procedure actions against their operation inputs, outcomes, effects and invariants. A consumer holding the module-issued packet can therefore inspect or apply the selected contract without reopening declaration sources. Resolution failures remain diagnostics rather than packets because they do not certify a compilation unit.

The process-local `QueryPacket` is the certified capability: its canonical serializer rejects a value not issued by Eutaxis or changed after issuance. Canonical JSON bytes are a portable projection, not a signature. Their embedded digests establish internal integrity and identify acquired content, but an independently received byte sequence needs an external trust root to establish its origin. `validate_query_packet_payload` checks the closed structural and semantic relations of such a projection; it does not authenticate its producer.

Upon failure, the external resolver issues an acquisition-bound `ExternalResolutionError` instead of a partial compilation unit. Its canonical diagnostic uses the separate format identifier `eutaxis:resolution-diagnostic@1`. The diagnostic records the failure code, portable source coordinates and authenticated trace prefix. Its packaged schema and semantic validator reject altered event fields, provenance, ordinals, causes and applicability results.

```{eval-rst}
.. automodule:: eutaxis.declarations.query_packet
   :members: QUERY_PACKET_SCHEMA, QueryPacket, QuerySelection, QuerySelectionOutcome, QuerySourceRevision, build_external_query_packet, query_packet_json_bytes
   :show-inheritance:

.. automodule:: eutaxis.declarations.query_packet_schema
   :members: query_packet_schema, query_packet_schema_path, validate_query_packet_payload

.. automodule:: eutaxis.declarations.resolution_diagnostic
   :members: RESOLUTION_DIAGNOSTIC_SCHEMA, external_resolution_failure_json_bytes

.. automodule:: eutaxis.declarations.resolution_diagnostic_schema
   :members: resolution_diagnostic_schema, resolution_diagnostic_schema_path, validate_resolution_diagnostic_payload
```

## External attention requirements

```{eval-rst}
.. automodule:: eutaxis.declarations.external_attention
   :members: ExternalAttentionRequirements, derive_external_attention_requirements
   :show-inheritance:
```

## External cumulative composition

```{eval-rst}
.. automodule:: eutaxis.declarations.external_composition
   :members: ExternalCumulativeArtifact, ExternalCumulativeCompositionPlan, assemble_external_cumulative_artifact, plan_external_cumulative_composition
   :show-inheritance:
```

## Artifact-facade source

The facade source binds the authenticated source revisions, certified component sequence and exact contributing declarations to the cumulative candidate bytes and their digest before acquisition authority is retired.

```{eval-rst}
.. automodule:: eutaxis.declarations.facade_report
   :members: ResolvedArtifactSelection, ResolvedCumulativeSource, resolve_external_cumulative_source_from_path
   :show-inheritance:
```

## Structured procedure Skill planning

```{eval-rst}
.. autoclass:: eutaxis.declarations.models.SupportResourceReference
   :members:

.. automodule:: eutaxis.declarations.structured_skill
   :members: PlannedSupportResource, StructuredSkillPlan, plan_structured_skill
   :show-inheritance:

.. automodule:: eutaxis.declarations.structured_skill_rendering
   :members: CONTRACT_FILENAME, render_structured_skill
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
