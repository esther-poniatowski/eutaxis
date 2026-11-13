<a id="declarations"></a>

# Declarations

External declaration acquisition: verifies one external corpus and exposes its portable source coordinates and exact support resources through an authenticated result.

<a id="module-eutaxis.declarations.external_result"></a>

<a id="external-acquisition-result"></a>

## External acquisition result

Publish authenticated external declarations as one opaque capability.

<a id="eutaxis.declarations.external_result.AcquisitionSourceCoordinate"></a>

### *class* eutaxis.declarations.external_result.AcquisitionSourceCoordinate(namespace, path, sha256)

Bases: `object`

Identify one acquired declaration file without transport-specific paths.

* **Parameters:**
  * **namespace** (*str*)
  * **path** (*str*)
  * **sha256** (*str*)

<a id="eutaxis.declarations.external_result.AcquisitionSourceCoordinate.namespace"></a>

#### namespace *: str*

<a id="eutaxis.declarations.external_result.AcquisitionSourceCoordinate.path"></a>

#### path *: str*

<a id="eutaxis.declarations.external_result.AcquisitionSourceCoordinate.sha256"></a>

#### sha256 *: str*

<a id="eutaxis.declarations.external_result.AcquiredResource"></a>

### *class* eutaxis.declarations.external_result.AcquiredResource(namespace, id, path, media_type, sha256, data)

Bases: `object`

Expose one exact authenticated external text resource.

* **Parameters:**
  * **namespace** (*str*)
  * **id** (*str*)
  * **path** (*str*)
  * **media_type** (*str*)
  * **sha256** (*str*)
  * **data** (*bytes*)

<a id="eutaxis.declarations.external_result.AcquiredResource.namespace"></a>

#### namespace *: str*

<a id="eutaxis.declarations.external_result.AcquiredResource.id"></a>

#### id *: str*

<a id="eutaxis.declarations.external_result.AcquiredResource.path"></a>

#### path *: str*

<a id="eutaxis.declarations.external_result.AcquiredResource.media_type"></a>

#### media_type *: str*

<a id="eutaxis.declarations.external_result.AcquiredResource.sha256"></a>

#### sha256 *: str*

<a id="eutaxis.declarations.external_result.AcquiredResource.data"></a>

#### data *: bytes*

<a id="eutaxis.declarations.external_result.ExternalAcquisitionResult"></a>

### *class* eutaxis.declarations.external_result.ExternalAcquisitionResult(\*\_args, \*\*\_kwargs)

Bases: `object`

Retain one fully verified external declaration corpus.

Instances are process-local capabilities. Eutaxis issues them only after
byte, transport, declaration, and cross-record checks all succeed.

* **Parameters:**
  * **\_args** (*object*)
  * **\_kwargs** (*object*)

<a id="eutaxis.declarations.external_result.ExternalAcquisitionResult.manifest"></a>

#### *property* manifest *: AcquisitionManifest*

Return the exact manifest admitted by this acquisition.

<a id="eutaxis.declarations.external_result.ExternalAcquisitionResult.lock"></a>

#### *property* lock *: AcquisitionLock*

Return the exact canonical lock admitted by this acquisition.

<a id="eutaxis.declarations.external_result.ExternalAcquisitionResult.facet_registry"></a>

#### *property* facet_registry *: CompositeFacetRegistry*

Return the issued composite facet registry used for parsing.

<a id="eutaxis.declarations.external_result.ExternalAcquisitionResult.source_coordinates"></a>

#### *property* source_coordinates *: tuple[[AcquisitionSourceCoordinate](#eutaxis.declarations.external_result.AcquisitionSourceCoordinate), ...]*

Return portable declaration coordinates in acquisition order.

<a id="eutaxis.declarations.external_result.ExternalAcquisitionResult.resources"></a>

#### *property* resources *: tuple[[AcquiredResource](#eutaxis.declarations.external_result.AcquiredResource), ...]*

Return exact acquired resource bytes in source and manifest order.

<a id="eutaxis.declarations.external_result.acquire_external_declarations"></a>

### eutaxis.declarations.external_result.acquire_external_declarations(workspace, manifest_path, lock_path)

Acquire external declarations through a caller-owned workspace capability.

* **Parameters:**
  * **workspace** (*TrustedDirectory*)
  * **manifest_path** (*str*)
  * **lock_path** (*str*)
* **Return type:**
  [*ExternalAcquisitionResult*](#eutaxis.declarations.external_result.ExternalAcquisitionResult)

<a id="eutaxis.declarations.external_result.acquire_external_declarations_from_path"></a>

### eutaxis.declarations.external_result.acquire_external_declarations_from_path(workspace_path, manifest_path, lock_path)

Acquire external declarations through an exact workspace path.

* **Parameters:**
  * **workspace_path** (*str*)
  * **manifest_path** (*str*)
  * **lock_path** (*str*)
* **Return type:**
  [*ExternalAcquisitionResult*](#eutaxis.declarations.external_result.ExternalAcquisitionResult)

<a id="module-eutaxis.declarations.external_resolution"></a>

<a id="external-resolution"></a>

## External resolution

Resolve authenticated external corpora without exposing their registries.

<a id="eutaxis.declarations.external_resolution.ExternalResolutionError"></a>

### *exception* eutaxis.declarations.external_resolution.ExternalResolutionError(\*\_args, \*\*\_kwargs)

Bases: `ResolutionError`

Report one acquisition-bound external semantic-resolution failure.

* **Parameters:**
  * **\_args** (*object*)
  * **\_kwargs** (*object*)
* **Return type:**
  None

<a id="eutaxis.declarations.external_resolution.ExternalResolutionResult"></a>

### *class* eutaxis.declarations.external_resolution.ExternalResolutionResult(\*\_args, \*\*\_kwargs)

Bases: `object`

Expose one resolved unit and trace without its private registry.

* **Parameters:**
  * **\_args** (*object*)
  * **\_kwargs** (*object*)

<a id="eutaxis.declarations.external_resolution.ExternalResolutionResult.unit"></a>

#### *property* unit *: ResolvedCompilationUnit*

Return the authenticated resolved compilation unit.

<a id="eutaxis.declarations.external_resolution.ExternalResolutionResult.trace"></a>

#### *property* trace *: ResolutionTrace*

Return the authenticated semantic-resolution trace.

<a id="eutaxis.declarations.external_resolution.resolve_external_compilation_unit"></a>

### eutaxis.declarations.external_resolution.resolve_external_compilation_unit(acquisition, manifest_id, context)

Resolve one manifest while retaining its exact acquisition authority.

* **Parameters:**
  * **acquisition** ([*ExternalAcquisitionResult*](#eutaxis.declarations.external_result.ExternalAcquisitionResult))
  * **manifest_id** (*str*)
  * **context** (*Mapping* *[**str* *,* *object* *]*)
* **Return type:**
  [*ExternalResolutionResult*](#eutaxis.declarations.external_resolution.ExternalResolutionResult)

<a id="query-packets"></a>

## Query packets

Completed external resolutions can be detached as canonical JSON query packets. Each packet records the normalized context, certified unit, complete declaration record and selection outcome of every compilation candidate, the manifest, rule-set and policy control closure, the active decision dependencies of effective rules, the exact typed evaluator and operation contract closure of the effective declarations, acquired support resources, resolver trace, portable source coordinates, acquisition-derived record locations and normalized content digests, hashes, and content revisions. The validator uses this index to bind each candidate, control, decision and contract to the acquired file, document path and normalized record body that declared it. It also rechecks procedure actions against their operation inputs, outcomes, effects and invariants. A consumer holding the module-issued packet can therefore inspect or apply the selected contract without reopening declaration sources. Resolution failures remain diagnostics rather than packets because they do not certify a compilation unit.

The process-local `QueryPacket` is the certified capability: its canonical serializer rejects a value not issued by Eutaxis or changed after issuance. Canonical JSON bytes are a portable projection, not a signature. Their embedded digests establish internal integrity and identify acquired content, but an independently received byte sequence needs an external trust root to establish its origin. `validate_query_packet_payload` checks the closed structural and semantic relations of such a projection; it does not authenticate its producer.

Upon failure, the external resolver issues an acquisition-bound `ExternalResolutionError` instead of a partial compilation unit. Its canonical diagnostic uses the separate format identifier `eutaxis:resolution-diagnostic@1`. The diagnostic records the failure code, portable source coordinates and authenticated trace prefix. Its packaged schema and semantic validator reject altered event fields, provenance, ordinals, causes and applicability results.

<a id="module-eutaxis.declarations.query_packet"></a>

Project authenticated external resolution into portable query packets.

<a id="eutaxis.declarations.query_packet.QuerySelectionOutcome"></a>

### *class* eutaxis.declarations.query_packet.QuerySelectionOutcome(\*values)

Bases: `StrEnum`

The closed final-state vocabulary for considered declarations.

<a id="eutaxis.declarations.query_packet.QuerySelectionOutcome.EFFECTIVE"></a>

#### EFFECTIVE *= 'effective'*

<a id="eutaxis.declarations.query_packet.QuerySelectionOutcome.EXCLUDED"></a>

#### EXCLUDED *= 'excluded'*

<a id="eutaxis.declarations.query_packet.QuerySelectionOutcome.INAPPLICABLE"></a>

#### INAPPLICABLE *= 'inapplicable'*

<a id="eutaxis.declarations.query_packet.QuerySelectionOutcome.INACTIVE"></a>

#### INACTIVE *= 'inactive'*

<a id="eutaxis.declarations.query_packet.QuerySourceRevision"></a>

### *class* eutaxis.declarations.query_packet.QuerySourceRevision(role, namespace, kind, content_revision)

Bases: `object`

Identify one acquired source group and its content revision.

* **Parameters:**
  * **role** (*Literal* *[* *'facet-base'* *,*  *'facet-extension'* *,*  *'declaration-source'* *]*)
  * **namespace** (*str*)
  * **kind** (*str*)
  * **content_revision** (*str*)

<a id="eutaxis.declarations.query_packet.QuerySourceRevision.role"></a>

#### role *: Literal['facet-base', 'facet-extension', 'declaration-source']*

<a id="eutaxis.declarations.query_packet.QuerySourceRevision.namespace"></a>

#### namespace *: str*

<a id="eutaxis.declarations.query_packet.QuerySourceRevision.kind"></a>

#### kind *: str*

<a id="eutaxis.declarations.query_packet.QuerySourceRevision.content_revision"></a>

#### content_revision *: str*

<a id="eutaxis.declarations.query_packet.QuerySelection"></a>

### *class* eutaxis.declarations.query_packet.QuerySelection(declaration, outcome, source_revision, source, reason_events)

Bases: `object`

Explain the final state of one declaration considered by resolution.

* **Parameters:**
  * **declaration** (*str*)
  * **outcome** ([*QuerySelectionOutcome*](#eutaxis.declarations.query_packet.QuerySelectionOutcome))
  * **source_revision** (*str*)
  * **source** ([*AcquisitionSourceCoordinate*](#eutaxis.declarations.external_result.AcquisitionSourceCoordinate))
  * **reason_events** (*tuple* *[**int* *,*  *...* *]*)

<a id="eutaxis.declarations.query_packet.QuerySelection.declaration"></a>

#### declaration *: str*

<a id="eutaxis.declarations.query_packet.QuerySelection.outcome"></a>

#### outcome *: [QuerySelectionOutcome](#eutaxis.declarations.query_packet.QuerySelectionOutcome)*

<a id="eutaxis.declarations.query_packet.QuerySelection.source_revision"></a>

#### source_revision *: str*

<a id="eutaxis.declarations.query_packet.QuerySelection.source"></a>

#### source *: [AcquisitionSourceCoordinate](#eutaxis.declarations.external_result.AcquisitionSourceCoordinate)*

<a id="eutaxis.declarations.query_packet.QuerySelection.reason_events"></a>

#### reason_events *: tuple[int, ...]*

<a id="eutaxis.declarations.query_packet.QueryPacket"></a>

### *class* eutaxis.declarations.query_packet.QueryPacket(\*\_args, \*\*\_kwargs)

Bases: `object`

One module-issued, deterministic projection of a completed query.

Callers cannot construct, copy or pickle this capability. Obtain an issued
value from [`build_external_query_packet()`](#eutaxis.declarations.query_packet.build_external_query_packet) and use
[`query_packet_json_bytes()`](#eutaxis.declarations.query_packet.query_packet_json_bytes) for its portable, unsigned projection.

* **Parameters:**
  * **\_args** (*object*)
  * **\_kwargs** (*object*)

<a id="eutaxis.declarations.query_packet.QueryPacket.payload"></a>

#### *property* payload *: Mapping[str, None | bool | int | float | str | tuple[None | bool | int | float | str | tuple[JsonValue, ...] | Mapping[str, JsonValue], ...] | Mapping[str, None | bool | int | float | str | tuple[JsonValue, ...] | Mapping[str, JsonValue]]]*

Return the immutable normalized packet payload.

<a id="eutaxis.declarations.query_packet.QueryPacket.manifest"></a>

#### *property* manifest *: str*

Return the resolved manifest identifier.

<a id="eutaxis.declarations.query_packet.QueryPacket.context"></a>

#### *property* context *: Mapping[str, None | bool | int | float | str | tuple[None | bool | int | float | str | tuple[JsonValue, ...] | Mapping[str, JsonValue], ...] | Mapping[str, None | bool | int | float | str | tuple[JsonValue, ...] | Mapping[str, JsonValue]]]*

Return the normalized context used by resolution.

<a id="eutaxis.declarations.query_packet.QueryPacket.source_revisions"></a>

#### *property* source_revisions *: tuple[[QuerySourceRevision](#eutaxis.declarations.query_packet.QuerySourceRevision), ...]*

Return the acquired source groups and their exact revisions.

<a id="eutaxis.declarations.query_packet.QueryPacket.sources"></a>

#### *property* sources *: tuple[[AcquisitionSourceCoordinate](#eutaxis.declarations.external_result.AcquisitionSourceCoordinate), ...]*

Return the portable coordinates of every acquired declaration file.

<a id="eutaxis.declarations.query_packet.QueryPacket.selections"></a>

#### *property* selections *: tuple[[QuerySelection](#eutaxis.declarations.query_packet.QuerySelection), ...]*

Return the final state and explanation events of each candidate.

<a id="eutaxis.declarations.query_packet.build_external_query_packet"></a>

### eutaxis.declarations.query_packet.build_external_query_packet(result)

Build a portable packet from one authenticated completed resolution.

The packet deliberately includes the complete normalized context and
applicability observations. Callers must therefore apply their disclosure
policy before storing or forwarding its canonical bytes.

* **Parameters:**
  **result** ([*ExternalResolutionResult*](#eutaxis.declarations.external_resolution.ExternalResolutionResult))
* **Return type:**
  [*QueryPacket*](#eutaxis.declarations.query_packet.QueryPacket)

<a id="eutaxis.declarations.query_packet.query_packet_json_bytes"></a>

### eutaxis.declarations.query_packet.query_packet_json_bytes(packet)

Return canonical JSON bytes for one module-issued query packet.

* **Parameters:**
  **packet** ([*QueryPacket*](#eutaxis.declarations.query_packet.QueryPacket))
* **Return type:**
  bytes

<a id="module-eutaxis.declarations.query_packet_schema"></a>

Load and apply the packaged query-packet schema.

<a id="eutaxis.declarations.query_packet_schema.query_packet_schema_path"></a>

### eutaxis.declarations.query_packet_schema.query_packet_schema_path()

Return the packaged path of the query-packet schema.

* **Return type:**
  *Path*

<a id="eutaxis.declarations.query_packet_schema.query_packet_schema"></a>

### eutaxis.declarations.query_packet_schema.query_packet_schema()

Return an isolated copy of the query-packet schema.

* **Return type:**
  dict[str, object]

<a id="eutaxis.declarations.query_packet_schema.validate_query_packet_payload"></a>

### eutaxis.declarations.query_packet_schema.validate_query_packet_payload(payload)

Validate one query-packet payload and return its mapping.

* **Parameters:**
  **payload** (*object*)
* **Return type:**
  *Mapping*[str, object]

<a id="module-eutaxis.declarations.resolution_diagnostic"></a>

Project failed external resolutions into closed diagnostic JSON.

<a id="eutaxis.declarations.resolution_diagnostic.external_resolution_failure_json_bytes"></a>

### eutaxis.declarations.resolution_diagnostic.external_resolution_failure_json_bytes(error)

Return canonical JSON for one authenticated failed resolution.

* **Parameters:**
  **error** ([*ExternalResolutionError*](#eutaxis.declarations.external_resolution.ExternalResolutionError))
* **Return type:**
  bytes

<a id="module-eutaxis.declarations.resolution_diagnostic_schema"></a>

Load and apply the packaged failed-resolution diagnostic schema.

<a id="eutaxis.declarations.resolution_diagnostic_schema.resolution_diagnostic_schema_path"></a>

### eutaxis.declarations.resolution_diagnostic_schema.resolution_diagnostic_schema_path()

Return the packaged path of the failed-resolution schema.

* **Return type:**
  *Path*

<a id="eutaxis.declarations.resolution_diagnostic_schema.resolution_diagnostic_schema"></a>

### eutaxis.declarations.resolution_diagnostic_schema.resolution_diagnostic_schema()

Return an isolated copy of the failed-resolution schema.

* **Return type:**
  dict[str, object]

<a id="eutaxis.declarations.resolution_diagnostic_schema.validate_resolution_diagnostic_payload"></a>

### eutaxis.declarations.resolution_diagnostic_schema.validate_resolution_diagnostic_payload(payload)

Validate one closed failed-resolution diagnostic projection.

* **Parameters:**
  **payload** (*object*)
* **Return type:**
  *Mapping*[str, object]

<a id="module-eutaxis.declarations.external_attention"></a>

<a id="external-attention-requirements"></a>

## External attention requirements

Derive enforcement requirements from external resolutions without registry access.

<a id="eutaxis.declarations.external_attention.ExternalAttentionRequirements"></a>

### *class* eutaxis.declarations.external_attention.ExternalAttentionRequirements(\*\_args, \*\*\_kwargs)

Bases: `object`

Expose canonical enforcement requirements without the private registry.

* **Parameters:**
  * **\_args** (*object*)
  * **\_kwargs** (*object*)

<a id="eutaxis.declarations.external_attention.ExternalAttentionRequirements.completion"></a>

#### *property* completion *: tuple[CompletionRequirement, ...]*

Return every canonical requirement in execution order.

<a id="eutaxis.declarations.external_attention.ExternalAttentionRequirements.deliberative"></a>

#### *property* deliberative *: tuple[DeliberativeAttentionRequirement, ...]*

Return requirements decided by unaided judgment.

<a id="eutaxis.declarations.external_attention.ExternalAttentionRequirements.assisted"></a>

#### *property* assisted *: tuple[RunnableAttentionRequirement, ...]*

Return requirements supported by candidate detectors.

<a id="eutaxis.declarations.external_attention.ExternalAttentionRequirements.mechanical"></a>

#### *property* mechanical *: tuple[RunnableAttentionRequirement, ...]*

Return requirements decided by authoritative checkers.

<a id="eutaxis.declarations.external_attention.derive_external_attention_requirements"></a>

### eutaxis.declarations.external_attention.derive_external_attention_requirements(resolution, \*, checker_registry=None, detector_registry=None)

Derive canonical requirements through an authenticated external boundary.

* **Parameters:**
  * **resolution** ([*ExternalResolutionResult*](#eutaxis.declarations.external_resolution.ExternalResolutionResult))
  * **checker_registry** (*CheckerRunnerRegistry* *|* *None*)
  * **detector_registry** (*DetectorRunnerRegistry* *|* *None*)
* **Return type:**
  [*ExternalAttentionRequirements*](#eutaxis.declarations.external_attention.ExternalAttentionRequirements)

<a id="module-eutaxis.declarations.external_composition"></a>

<a id="external-cumulative-composition"></a>

## External cumulative composition

Compose authenticated external resolutions without exposing their registries.

<a id="eutaxis.declarations.external_composition.ExternalCumulativeCompositionPlan"></a>

### *class* eutaxis.declarations.external_composition.ExternalCumulativeCompositionPlan(\*\_args, \*\*\_kwargs)

Bases: `object`

Expose an authenticated cumulative plan without its private registry.

* **Parameters:**
  * **\_args** (*object*)
  * **\_kwargs** (*object*)

<a id="eutaxis.declarations.external_composition.ExternalCumulativeCompositionPlan.manifest"></a>

#### *property* manifest *: str*

Return the authenticated composition-manifest identifier.

<a id="eutaxis.declarations.external_composition.ExternalCumulativeCompositionPlan.scope"></a>

#### *property* scope *: str*

Return the authenticated artifact scope.

<a id="eutaxis.declarations.external_composition.ExternalCumulativeCompositionPlan.target"></a>

#### *property* target *: str*

Return the authenticated artifact target.

<a id="eutaxis.declarations.external_composition.ExternalCumulativeCompositionPlan.components"></a>

#### *property* components *: tuple[PlannedComponent, ...]*

Return the authenticated component order.

<a id="eutaxis.declarations.external_composition.ExternalCumulativeArtifact"></a>

### *class* eutaxis.declarations.external_composition.ExternalCumulativeArtifact(\*\_args, \*\*\_kwargs)

Bases: `object`

Expose cumulative bytes that remain bound to external authority.

* **Parameters:**
  * **\_args** (*object*)
  * **\_kwargs** (*object*)

<a id="eutaxis.declarations.external_composition.ExternalCumulativeArtifact.manifest"></a>

#### *property* manifest *: str*

Return the authenticated composition-manifest identifier.

<a id="eutaxis.declarations.external_composition.ExternalCumulativeArtifact.scope"></a>

#### *property* scope *: str*

Return the authenticated artifact scope.

<a id="eutaxis.declarations.external_composition.ExternalCumulativeArtifact.target"></a>

#### *property* target *: str*

Return the authenticated artifact target.

<a id="eutaxis.declarations.external_composition.ExternalCumulativeArtifact.content"></a>

#### *property* content *: bytes*

Return the authenticated canonical artifact bytes.

<a id="eutaxis.declarations.external_composition.ExternalCumulativeArtifact.text"></a>

#### *property* text *: str*

Decode the authenticated canonical bytes as strict UTF-8.

<a id="eutaxis.declarations.external_composition.plan_external_cumulative_composition"></a>

### eutaxis.declarations.external_composition.plan_external_cumulative_composition(resolution)

Plan one external cumulative unit through its private registry.

* **Parameters:**
  **resolution** ([*ExternalResolutionResult*](#eutaxis.declarations.external_resolution.ExternalResolutionResult))
* **Return type:**
  [*ExternalCumulativeCompositionPlan*](#eutaxis.declarations.external_composition.ExternalCumulativeCompositionPlan)

<a id="eutaxis.declarations.external_composition.assemble_external_cumulative_artifact"></a>

### eutaxis.declarations.external_composition.assemble_external_cumulative_artifact(plan, fragments)

Assemble one external plan while rechecking its complete authority.

* **Parameters:**
  * **plan** ([*ExternalCumulativeCompositionPlan*](#eutaxis.declarations.external_composition.ExternalCumulativeCompositionPlan))
  * **fragments** (*Mapping* *[**str* *,* *str* *]*)
* **Return type:**
  [*ExternalCumulativeArtifact*](#eutaxis.declarations.external_composition.ExternalCumulativeArtifact)

<a id="eutaxis.declarations.external_composition.render_external_cumulative_markdown"></a>

### eutaxis.declarations.external_composition.render_external_cumulative_markdown(plan, \*, profile=CumulativeMarkdownProfile.AUDITABLE)

Render one external cumulative plan for a declared consumer profile.

* **Parameters:**
  * **plan** ([*ExternalCumulativeCompositionPlan*](#eutaxis.declarations.external_composition.ExternalCumulativeCompositionPlan))
  * **profile** (*CumulativeMarkdownProfile*)
* **Return type:**
  [*ExternalCumulativeArtifact*](#eutaxis.declarations.external_composition.ExternalCumulativeArtifact)

<a id="artifact-facade-source"></a>

## Artifact-facade source

The facade source binds the authenticated source revisions and certified component sequence to the exact cumulative candidate bytes and their digest before acquisition authority is retired.

<a id="module-eutaxis.declarations.facade_report"></a>

Project authenticated resolution into concise artifact-facade reports.

<a id="eutaxis.declarations.facade_report.ResolvedArtifactSelection"></a>

### *class* eutaxis.declarations.facade_report.ResolvedArtifactSelection(manifest, mechanism, scope, target, records)

Bases: `object`

Identify one resolved artifact and its ordered effective records.

* **Parameters:**
  * **manifest** (*str*)
  * **mechanism** (*str*)
  * **scope** (*str*)
  * **target** (*str*)
  * **records** (*tuple* *[**str* *,*  *...* *]*)

<a id="eutaxis.declarations.facade_report.ResolvedArtifactSelection.manifest"></a>

#### manifest *: str*

<a id="eutaxis.declarations.facade_report.ResolvedArtifactSelection.mechanism"></a>

#### mechanism *: str*

<a id="eutaxis.declarations.facade_report.ResolvedArtifactSelection.scope"></a>

#### scope *: str*

<a id="eutaxis.declarations.facade_report.ResolvedArtifactSelection.target"></a>

#### target *: str*

<a id="eutaxis.declarations.facade_report.ResolvedArtifactSelection.records"></a>

#### records *: tuple[str, ...]*

<a id="eutaxis.declarations.facade_report.ResolvedCumulativeSource"></a>

### *class* eutaxis.declarations.facade_report.ResolvedCumulativeSource(selection, source_revisions, content, sha256)

Bases: `object`

Bind certified inputs and selection to exact cumulative candidate bytes.

* **Parameters:**
  * **selection** ([*ResolvedArtifactSelection*](#eutaxis.declarations.facade_report.ResolvedArtifactSelection))
  * **source_revisions** (*tuple* *[*[*QuerySourceRevision*](#eutaxis.declarations.query_packet.QuerySourceRevision) *,*  *...* *]*)
  * **content** (*bytes*)
  * **sha256** (*str*)

<a id="eutaxis.declarations.facade_report.ResolvedCumulativeSource.selection"></a>

#### selection *: [ResolvedArtifactSelection](#eutaxis.declarations.facade_report.ResolvedArtifactSelection)*

<a id="eutaxis.declarations.facade_report.ResolvedCumulativeSource.source_revisions"></a>

#### source_revisions *: tuple[[QuerySourceRevision](#eutaxis.declarations.query_packet.QuerySourceRevision), ...]*

<a id="eutaxis.declarations.facade_report.ResolvedCumulativeSource.content"></a>

#### content *: bytes*

<a id="eutaxis.declarations.facade_report.ResolvedCumulativeSource.sha256"></a>

#### sha256 *: str*

<a id="eutaxis.declarations.facade_report.ResolvedCumulativeSource.text"></a>

#### *property* text *: str*

Decode the certified candidate as strict UTF-8.

<a id="eutaxis.declarations.facade_report.resolved_artifact_selection"></a>

### eutaxis.declarations.facade_report.resolved_artifact_selection(result)

Return the concise facade projection of an authenticated resolution.

* **Parameters:**
  **result** ([*ExternalResolutionResult*](#eutaxis.declarations.external_resolution.ExternalResolutionResult))
* **Return type:**
  [*ResolvedArtifactSelection*](#eutaxis.declarations.facade_report.ResolvedArtifactSelection)

<a id="eutaxis.declarations.facade_report.resolve_external_cumulative_source_from_path"></a>

### eutaxis.declarations.facade_report.resolve_external_cumulative_source_from_path(workspace, acquisition_manifest, acquisition_lock, composition_manifest, context)

Issue one immutable candidate plan before retiring source authority.

* **Parameters:**
  * **workspace** (*str*)
  * **acquisition_manifest** (*str*)
  * **acquisition_lock** (*str*)
  * **composition_manifest** (*str*)
  * **context** (*Mapping* *[**str* *,* *None* *|* *bool* *|* *int* *|* *float* *|* *str* *|* *tuple* *[**None* *|* *bool* *|* *int* *|* *float* *|* *str* *|* *tuple* *[**JsonValue* *,*  *...* *]*  *|* *Mapping* *[**str* *,* *JsonValue* *]* *,*  *...* *]*  *|* *Mapping* *[**str* *,* *None* *|* *bool* *|* *int* *|* *float* *|* *str* *|* *tuple* *[**JsonValue* *,*  *...* *]*  *|* *Mapping* *[**str* *,* *JsonValue* *]* *]* *]*)
* **Return type:**
  [*ResolvedCumulativeSource*](#eutaxis.declarations.facade_report.ResolvedCumulativeSource)

<a id="structured-procedure-skill-planning"></a>

## Structured procedure Skill planning

<a id="eutaxis.declarations.models.SupportResourceReference"></a>

### *class* eutaxis.declarations.models.SupportResourceReference(resource, destination)

Bases: `object`

Place one acquired resource inside an operation’s Skill artifact.

* **Parameters:**
  * **resource** (*str*)
  * **destination** (*str*)

<a id="eutaxis.declarations.models.SupportResourceReference.resource"></a>

#### resource *: str*

<a id="eutaxis.declarations.models.SupportResourceReference.destination"></a>

#### destination *: str*

<a id="module-eutaxis.declarations.structured_skill"></a>

Plan one authenticated structured procedure Skill and its resource closure.

<a id="eutaxis.declarations.structured_skill.PlannedSupportResource"></a>

### *class* eutaxis.declarations.structured_skill.PlannedSupportResource(operation, resource, destination)

Bases: `object`

Bind one operation dependency to exact acquired bytes and a destination.

* **Parameters:**
  * **operation** (*VersionedReference*)
  * **resource** ([*AcquiredResource*](#eutaxis.declarations.external_result.AcquiredResource))
  * **destination** (*str*)

<a id="eutaxis.declarations.structured_skill.PlannedSupportResource.operation"></a>

#### operation *: VersionedReference*

<a id="eutaxis.declarations.structured_skill.PlannedSupportResource.resource"></a>

#### resource *: [AcquiredResource](#eutaxis.declarations.external_result.AcquiredResource)*

<a id="eutaxis.declarations.structured_skill.PlannedSupportResource.destination"></a>

#### destination *: str*

<a id="eutaxis.declarations.structured_skill.StructuredSkillPlan"></a>

### *class* eutaxis.declarations.structured_skill.StructuredSkillPlan(\*\_args, \*\*\_kwargs)

Bases: `object`

Expose an authenticated structured procedure and resource closure.

* **Parameters:**
  * **\_args** (*object*)
  * **\_kwargs** (*object*)

<a id="eutaxis.declarations.structured_skill.StructuredSkillPlan.manifest"></a>

#### *property* manifest *: CompositionManifestDeclaration*

Return the exact separate-directory manifest.

<a id="eutaxis.declarations.structured_skill.StructuredSkillPlan.name"></a>

#### *property* name *: str*

Return the authenticated Skill name.

<a id="eutaxis.declarations.structured_skill.StructuredSkillPlan.scope"></a>

#### *property* scope *: str*

Return the authenticated installation scope.

<a id="eutaxis.declarations.structured_skill.StructuredSkillPlan.invocation"></a>

#### *property* invocation *: tuple[str, ...]*

Return the authenticated invocation routes.

<a id="eutaxis.declarations.structured_skill.StructuredSkillPlan.procedure"></a>

#### *property* procedure *: ProcedureDeclaration*

Return the exact selected root procedure.

<a id="eutaxis.declarations.structured_skill.StructuredSkillPlan.operations"></a>

#### *property* operations *: tuple[OperationDeclaration, ...]*

Return exact operations in first action-reference order.

<a id="eutaxis.declarations.structured_skill.StructuredSkillPlan.support_resources"></a>

#### *property* support_resources *: tuple[[PlannedSupportResource](#eutaxis.declarations.structured_skill.PlannedSupportResource), ...]*

Return the authenticated operation-owned resource closure.

<a id="eutaxis.declarations.structured_skill.plan_structured_skill"></a>

### eutaxis.declarations.structured_skill.plan_structured_skill(resolution)

Close one resolved procedure over exact operations and support resources.

* **Parameters:**
  **resolution** ([*ExternalResolutionResult*](#eutaxis.declarations.external_resolution.ExternalResolutionResult))
* **Return type:**
  [*StructuredSkillPlan*](#eutaxis.declarations.structured_skill.StructuredSkillPlan)

<a id="module-eutaxis.declarations.structured_skill_rendering"></a>

Render authenticated structured procedure plans as bounded Agent Skills.

<a id="eutaxis.declarations.structured_skill_rendering.render_structured_skill"></a>

### eutaxis.declarations.structured_skill_rendering.render_structured_skill(plan, adapter, \*, entrypoint_max_bytes, artifact_max_bytes)

Render one issued plan within explicit entrypoint and artifact limits.

* **Parameters:**
  * **plan** ([*StructuredSkillPlan*](#eutaxis.declarations.structured_skill.StructuredSkillPlan))
  * **adapter** (*AgentAdapter*)
  * **entrypoint_max_bytes** (*int*)
  * **artifact_max_bytes** (*int*)
* **Return type:**
  [*RenderedArtifact*](commands.md#eutaxis.commands.models.RenderedArtifact)

<a id="module-eutaxis.declarations.catalog"></a>

<a id="declaration-catalog"></a>

## Declaration catalog

Build a portable static catalog from a validated declaration registry.

<a id="eutaxis.declarations.catalog.ExactContractKey"></a>

### *class* eutaxis.declarations.catalog.ExactContractKey(kind, id, version)

Bases: `object`

One exact evaluator or operation contract key.

* **Parameters:**
  * **kind** (*DeclarationKind*)
  * **id** (*str*)
  * **version** (*int*)

<a id="eutaxis.declarations.catalog.ExactContractKey.kind"></a>

#### kind *: DeclarationKind*

<a id="eutaxis.declarations.catalog.ExactContractKey.id"></a>

#### id *: str*

<a id="eutaxis.declarations.catalog.ExactContractKey.version"></a>

#### version *: int*

<a id="eutaxis.declarations.catalog.CatalogSource"></a>

### *class* eutaxis.declarations.catalog.CatalogSource(namespace, path, sha256)

Bases: `object`

Portable provenance for one source snapshot.

* **Parameters:**
  * **namespace** (*str* *|* *None*)
  * **path** (*str*)
  * **sha256** (*str*)

<a id="eutaxis.declarations.catalog.CatalogSource.namespace"></a>

#### namespace *: str | None*

<a id="eutaxis.declarations.catalog.CatalogSource.path"></a>

#### path *: str*

<a id="eutaxis.declarations.catalog.CatalogSource.sha256"></a>

#### sha256 *: str*

<a id="eutaxis.declarations.catalog.DeclarationCatalog"></a>

### *class* eutaxis.declarations.catalog.DeclarationCatalog(revision, facet_content_revision, source_root, sources, declarations, contracts, conflicts)

Bases: `object`

Immutable static lookups over one validated declaration registry.

* **Parameters:**
  * **revision** (*int*)
  * **facet_content_revision** (*str* *|* *None*)
  * **source_root** (*Path* *|* *None*)
  * **sources** (*tuple* *[*[*CatalogSource*](#eutaxis.declarations.catalog.CatalogSource) *,*  *...* *]*)
  * **declarations** (*Mapping* *[**str* *,* *RegisteredDeclaration* *]*)
  * **contracts** (*Mapping* *[*[*ExactContractKey*](#eutaxis.declarations.catalog.ExactContractKey) *,* *RegisteredDeclaration* *]*)
  * **conflicts** (*tuple* *[**tuple* *[**str* *,* *str* *]* *,*  *...* *]*)

<a id="eutaxis.declarations.catalog.DeclarationCatalog.revision"></a>

#### revision *: int*

<a id="eutaxis.declarations.catalog.DeclarationCatalog.facet_content_revision"></a>

#### facet_content_revision *: str | None*

<a id="eutaxis.declarations.catalog.DeclarationCatalog.source_root"></a>

#### source_root *: Path | None*

<a id="eutaxis.declarations.catalog.DeclarationCatalog.sources"></a>

#### sources *: tuple[[CatalogSource](#eutaxis.declarations.catalog.CatalogSource), ...]*

<a id="eutaxis.declarations.catalog.DeclarationCatalog.declarations"></a>

#### declarations *: Mapping[str, RegisteredDeclaration]*

<a id="eutaxis.declarations.catalog.DeclarationCatalog.contracts"></a>

#### contracts *: Mapping[[ExactContractKey](#eutaxis.declarations.catalog.ExactContractKey), RegisteredDeclaration]*

<a id="eutaxis.declarations.catalog.DeclarationCatalog.conflicts"></a>

#### conflicts *: tuple[tuple[str, str], ...]*

<a id="eutaxis.declarations.catalog.DeclarationCatalog.get"></a>

#### get(identifier)

Return one unversioned record, or `None` when it is absent.

* **Parameters:**
  **identifier** (*str*)
* **Return type:**
  *RegisteredDeclaration* | None

<a id="eutaxis.declarations.catalog.DeclarationCatalog.get_contract"></a>

#### get_contract(kind, identifier, version)

Return one exact evaluator or operation contract when present.

* **Parameters:**
  * **kind** (*DeclarationKind*)
  * **identifier** (*str*)
  * **version** (*int*)
* **Return type:**
  *RegisteredDeclaration* | None

<a id="eutaxis.declarations.catalog.DeclarationCatalog.filter_static"></a>

#### filter_static(query)

Return records whose stored fields satisfy every exact predicate.

* **Parameters:**
  **query** (*StaticCatalogQuery*)
* **Return type:**
  tuple[*RegisteredDeclaration*, …]

<a id="eutaxis.declarations.catalog.DeclarationCatalog.filter_enforcement"></a>

#### filter_enforcement(enforcement)

Return authored obligations with one declared enforcement class.

* **Parameters:**
  **enforcement** (*EnforcementClass*)
* **Return type:**
  tuple[*RuleCriterionEnforcement* | *ProcedurePredicateEnforcement* | *OperationPredicateEnforcement*, …]

<a id="eutaxis.declarations.catalog.build_declaration_catalog"></a>

### eutaxis.declarations.catalog.build_declaration_catalog(result)

Build revision 2 lookups from one issued external acquisition result.

* **Parameters:**
  **result** ([*ExternalAcquisitionResult*](#eutaxis.declarations.external_result.ExternalAcquisitionResult))
* **Return type:**
  [*DeclarationCatalog*](#eutaxis.declarations.catalog.DeclarationCatalog)

<a id="eutaxis.declarations.catalog.catalog_json_bytes"></a>

### eutaxis.declarations.catalog.catalog_json_bytes(catalog)

Serialize one revision 2 catalog as deterministic portable JSON.

* **Parameters:**
  **catalog** ([*DeclarationCatalog*](#eutaxis.declarations.catalog.DeclarationCatalog))
* **Return type:**
  bytes

<a id="module-eutaxis.declarations.persisted_catalog"></a>

<a id="persisted-catalog"></a>

## Persisted catalog

Load an immutable static projection from persisted catalog-index JSON.

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogRelation"></a>

### *class* eutaxis.declarations.persisted_catalog.PersistedCatalogRelation(type, target)

Bases: `object`

One typed relation retained by a persisted index row.

* **Parameters:**
  * **type** (*str*)
  * **target** (*str*)

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogRelation.type"></a>

#### type *: str*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogRelation.target"></a>

#### target *: str*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogProvenance"></a>

### *class* eutaxis.declarations.persisted_catalog.PersistedCatalogProvenance(namespace, path, document_path, line, column)

Bases: `object`

Portable source coordinates retained by a persisted index row.

* **Parameters:**
  * **namespace** (*str* *|* *None*)
  * **path** (*str*)
  * **document_path** (*tuple* *[**str* *|* *int* *,*  *...* *]*)
  * **line** (*int*)
  * **column** (*int*)

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogProvenance.namespace"></a>

#### namespace *: str | None*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogProvenance.path"></a>

#### path *: str*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogProvenance.document_path"></a>

#### document_path *: tuple[str | int, ...]*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogProvenance.line"></a>

#### line *: int*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogProvenance.column"></a>

#### column *: int*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry"></a>

### *class* eutaxis.declarations.persisted_catalog.PersistedCatalogEntry(id, kind, owner, status, source_revision, schema_version, applicability, relations, query, containing_rule_set, source, version)

Bases: `object`

A lossy static index row, not a semantic source declaration.

* **Parameters:**
  * **id** (*str*)
  * **kind** (*DeclarationKind*)
  * **owner** (*str*)
  * **status** (*DeclarationStatus*)
  * **source_revision** (*str*)
  * **schema_version** (*int*)
  * **applicability** (*Mapping* *[**str* *,* *None* *|* *bool* *|* *int* *|* *float* *|* *str* *|* *tuple* *[**None* *|* *bool* *|* *int* *|* *float* *|* *str* *|* *tuple* *[**JsonValue* *,*  *...* *]*  *|* *Mapping* *[**str* *,* *JsonValue* *]* *,*  *...* *]*  *|* *Mapping* *[**str* *,* *None* *|* *bool* *|* *int* *|* *float* *|* *str* *|* *tuple* *[**JsonValue* *,*  *...* *]*  *|* *Mapping* *[**str* *,* *JsonValue* *]* *]* *]*)
  * **relations** (*tuple* *[*[*PersistedCatalogRelation*](#eutaxis.declarations.persisted_catalog.PersistedCatalogRelation) *,*  *...* *]*)
  * **query** (*Mapping* *[**str* *,* *None* *|* *bool* *|* *int* *|* *float* *|* *str* *|* *tuple* *[**None* *|* *bool* *|* *int* *|* *float* *|* *str* *|* *tuple* *[**JsonValue* *,*  *...* *]*  *|* *Mapping* *[**str* *,* *JsonValue* *]* *,*  *...* *]*  *|* *Mapping* *[**str* *,* *None* *|* *bool* *|* *int* *|* *float* *|* *str* *|* *tuple* *[**JsonValue* *,*  *...* *]*  *|* *Mapping* *[**str* *,* *JsonValue* *]* *]* *]*)
  * **containing_rule_set** (*str* *|* *None*)
  * **source** ([*PersistedCatalogProvenance*](#eutaxis.declarations.persisted_catalog.PersistedCatalogProvenance))
  * **version** (*int* *|* *None*)

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.id"></a>

#### id *: str*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.kind"></a>

#### kind *: DeclarationKind*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.owner"></a>

#### owner *: str*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.status"></a>

#### status *: DeclarationStatus*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.source_revision"></a>

#### source_revision *: str*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.schema_version"></a>

#### schema_version *: int*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.applicability"></a>

#### applicability *: Mapping[str, None | bool | int | float | str | tuple[None | bool | int | float | str | tuple[JsonValue, ...] | Mapping[str, JsonValue], ...] | Mapping[str, None | bool | int | float | str | tuple[JsonValue, ...] | Mapping[str, JsonValue]]]*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.relations"></a>

#### relations *: tuple[[PersistedCatalogRelation](#eutaxis.declarations.persisted_catalog.PersistedCatalogRelation), ...]*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.query"></a>

#### query *: Mapping[str, None | bool | int | float | str | tuple[None | bool | int | float | str | tuple[JsonValue, ...] | Mapping[str, JsonValue], ...] | Mapping[str, None | bool | int | float | str | tuple[JsonValue, ...] | Mapping[str, JsonValue]]]*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.containing_rule_set"></a>

#### containing_rule_set *: str | None*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.source"></a>

#### source *: [PersistedCatalogProvenance](#eutaxis.declarations.persisted_catalog.PersistedCatalogProvenance)*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.version"></a>

#### version *: int | None*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex"></a>

### *class* eutaxis.declarations.persisted_catalog.PersistedCatalogIndex(revision, facet_content_revision, sources, declarations, contracts, conflicts)

Bases: `object`

An immutable query projection, never a registry or resolver input.

* **Parameters:**
  * **revision** (*int*)
  * **facet_content_revision** (*str* *|* *None*)
  * **sources** (*tuple* *[*[*CatalogSource*](#eutaxis.declarations.catalog.CatalogSource) *,*  *...* *]*)
  * **declarations** (*Mapping* *[**str* *,* [*PersistedCatalogEntry*](#eutaxis.declarations.persisted_catalog.PersistedCatalogEntry) *]*)
  * **contracts** (*Mapping* *[*[*ExactContractKey*](#eutaxis.declarations.catalog.ExactContractKey) *,* [*PersistedCatalogEntry*](#eutaxis.declarations.persisted_catalog.PersistedCatalogEntry) *]*)
  * **conflicts** (*tuple* *[**tuple* *[**str* *,* *str* *]* *,*  *...* *]*)

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex.revision"></a>

#### revision *: int*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex.facet_content_revision"></a>

#### facet_content_revision *: str | None*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex.sources"></a>

#### sources *: tuple[[CatalogSource](#eutaxis.declarations.catalog.CatalogSource), ...]*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex.declarations"></a>

#### declarations *: Mapping[str, [PersistedCatalogEntry](#eutaxis.declarations.persisted_catalog.PersistedCatalogEntry)]*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex.contracts"></a>

#### contracts *: Mapping[[ExactContractKey](#eutaxis.declarations.catalog.ExactContractKey), [PersistedCatalogEntry](#eutaxis.declarations.persisted_catalog.PersistedCatalogEntry)]*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex.conflicts"></a>

#### conflicts *: tuple[tuple[str, str], ...]*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex.get"></a>

#### get(identifier)

Return one unversioned row, or `None` when it is absent.

* **Parameters:**
  **identifier** (*str*)
* **Return type:**
  [*PersistedCatalogEntry*](#eutaxis.declarations.persisted_catalog.PersistedCatalogEntry) | None

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex.get_contract"></a>

#### get_contract(kind, identifier, version)

Return one exact evaluator or operation row when present.

* **Parameters:**
  * **kind** (*DeclarationKind*)
  * **identifier** (*str*)
  * **version** (*int*)
* **Return type:**
  [*PersistedCatalogEntry*](#eutaxis.declarations.persisted_catalog.PersistedCatalogEntry) | None

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex.filter_static"></a>

#### filter_static(query)

Return rows whose stored fields satisfy every exact predicate.

* **Parameters:**
  **query** (*StaticCatalogQuery*)
* **Return type:**
  tuple[[*PersistedCatalogEntry*](#eutaxis.declarations.persisted_catalog.PersistedCatalogEntry), …]

<a id="eutaxis.declarations.persisted_catalog.load_persisted_catalog_index"></a>

### eutaxis.declarations.persisted_catalog.load_persisted_catalog_index(data, \*, source=None)

Load and validate one persisted static index without semantic recovery.

* **Parameters:**
  * **data** (*bytes*)
  * **source** (*Path* *|* *None*)
* **Return type:**
  [*PersistedCatalogIndex*](#eutaxis.declarations.persisted_catalog.PersistedCatalogIndex)

<a id="module-eutaxis.declarations.catalog_schema"></a>

<a id="catalog-schema"></a>

## Catalog schema

Load and apply the packaged static catalog-index schema.

<a id="eutaxis.declarations.catalog_schema.catalog_index_schema_path"></a>

### eutaxis.declarations.catalog_schema.catalog_index_schema_path()

Return the packaged path of the current static catalog-index schema.

* **Return type:**
  *Path*

<a id="eutaxis.declarations.catalog_schema.catalog_index_schema"></a>

### eutaxis.declarations.catalog_schema.catalog_index_schema()

Return an isolated copy of the current static catalog-index schema.

* **Return type:**
  dict[str, object]

<a id="eutaxis.declarations.catalog_schema.validate_catalog_index_payload"></a>

### eutaxis.declarations.catalog_schema.validate_catalog_index_payload(payload, \*, source=None)

Validate one index payload and return its mapping representation.

* **Parameters:**
  * **payload** (*object*)
  * **source** (*Path* *|* *None*)
* **Return type:**
  *Mapping*[str, object]
