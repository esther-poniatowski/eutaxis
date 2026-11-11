<a id="declarations"></a>

# Declarations

External declaration acquisition: verifies one external corpus and exposes its portable source coordinates and exact support resources through an authenticated result.

<a id="module-eutaxis.declarations.external_result"></a>

<a id="external-acquisition-result"></a>

## External acquisition result

Publish authenticated external declarations as one opaque capability.

<a id="eutaxis.declarations.external_result.AcquisitionSourceCoordinate"></a>

### *class* eutaxis.declarations.external_result.AcquisitionSourceCoordinate(namespace, path, sha256)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Identify one acquired declaration file without transport-specific paths.

* **Parameters:**
  * **namespace** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **path** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **sha256** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))

<a id="eutaxis.declarations.external_result.AcquisitionSourceCoordinate.namespace"></a>

#### namespace *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.external_result.AcquisitionSourceCoordinate.path"></a>

#### path *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.external_result.AcquisitionSourceCoordinate.sha256"></a>

#### sha256 *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.external_result.AcquiredResource"></a>

### *class* eutaxis.declarations.external_result.AcquiredResource(namespace, id, path, media_type, sha256, data)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Expose one exact authenticated external text resource.

* **Parameters:**
  * **namespace** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **id** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **path** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **media_type** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **sha256** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **data** ([*bytes*](https://docs.python.org/3/builtins/stdtypes.html#bytes))

<a id="eutaxis.declarations.external_result.AcquiredResource.namespace"></a>

#### namespace *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.external_result.AcquiredResource.id"></a>

#### id *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.external_result.AcquiredResource.path"></a>

#### path *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.external_result.AcquiredResource.media_type"></a>

#### media_type *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.external_result.AcquiredResource.sha256"></a>

#### sha256 *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.external_result.AcquiredResource.data"></a>

#### data *: [bytes](https://docs.python.org/3/builtins/stdtypes.html#bytes)*

<a id="eutaxis.declarations.external_result.ExternalAcquisitionResult"></a>

### *class* eutaxis.declarations.external_result.ExternalAcquisitionResult(\*\_args, \*\*\_kwargs)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Retain one fully verified external declaration corpus.

Instances are process-local capabilities. Eutaxis issues them only after
byte, transport, declaration, and cross-record checks all succeed.

* **Parameters:**
  * **\_args** ([*object*](https://docs.python.org/3/builtins/functions.html#object))
  * **\_kwargs** ([*object*](https://docs.python.org/3/builtins/functions.html#object))

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

#### *property* source_coordinates *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[AcquisitionSourceCoordinate](#eutaxis.declarations.external_result.AcquisitionSourceCoordinate), ...]*

Return portable declaration coordinates in acquisition order.

<a id="eutaxis.declarations.external_result.ExternalAcquisitionResult.resources"></a>

#### *property* resources *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[AcquiredResource](#eutaxis.declarations.external_result.AcquiredResource), ...]*

Return exact acquired resource bytes in source and manifest order.

<a id="eutaxis.declarations.external_result.acquire_external_declarations"></a>

### eutaxis.declarations.external_result.acquire_external_declarations(workspace, manifest_path, lock_path)

Acquire external declarations through a caller-owned workspace capability.

* **Parameters:**
  * **workspace** (*TrustedDirectory*)
  * **manifest_path** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **lock_path** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  [*ExternalAcquisitionResult*](#eutaxis.declarations.external_result.ExternalAcquisitionResult)

<a id="eutaxis.declarations.external_result.acquire_external_declarations_from_path"></a>

### eutaxis.declarations.external_result.acquire_external_declarations_from_path(workspace_path, manifest_path, lock_path)

Acquire external declarations through an exact workspace path.

* **Parameters:**
  * **workspace_path** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **manifest_path** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **lock_path** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  [*ExternalAcquisitionResult*](#eutaxis.declarations.external_result.ExternalAcquisitionResult)

<a id="module-eutaxis.declarations.external_resolution"></a>

<a id="external-resolution"></a>

## External resolution

Resolve authenticated external corpora without exposing their registries.

<a id="eutaxis.declarations.external_resolution.ExternalResolutionResult"></a>

### *class* eutaxis.declarations.external_resolution.ExternalResolutionResult(\*\_args, \*\*\_kwargs)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Expose one resolved unit and trace without its private registry.

* **Parameters:**
  * **\_args** ([*object*](https://docs.python.org/3/builtins/functions.html#object))
  * **\_kwargs** ([*object*](https://docs.python.org/3/builtins/functions.html#object))

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
  * **manifest_id** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **context** ([*Mapping*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* [*object*](https://docs.python.org/3/builtins/functions.html#object) *]*)
* **Return type:**
  [*ExternalResolutionResult*](#eutaxis.declarations.external_resolution.ExternalResolutionResult)

<a id="module-eutaxis.declarations.external_composition"></a>

<a id="external-cumulative-composition"></a>

## External cumulative composition

Compose authenticated external resolutions without exposing their registries.

<a id="eutaxis.declarations.external_composition.ExternalCumulativeCompositionPlan"></a>

### *class* eutaxis.declarations.external_composition.ExternalCumulativeCompositionPlan(\*\_args, \*\*\_kwargs)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Expose an authenticated cumulative plan without its private registry.

* **Parameters:**
  * **\_args** ([*object*](https://docs.python.org/3/builtins/functions.html#object))
  * **\_kwargs** ([*object*](https://docs.python.org/3/builtins/functions.html#object))

<a id="eutaxis.declarations.external_composition.ExternalCumulativeCompositionPlan.manifest"></a>

#### *property* manifest *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Return the authenticated composition-manifest identifier.

<a id="eutaxis.declarations.external_composition.ExternalCumulativeCompositionPlan.scope"></a>

#### *property* scope *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Return the authenticated artifact scope.

<a id="eutaxis.declarations.external_composition.ExternalCumulativeCompositionPlan.target"></a>

#### *property* target *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Return the authenticated artifact target.

<a id="eutaxis.declarations.external_composition.ExternalCumulativeCompositionPlan.components"></a>

#### *property* components *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[PlannedComponent, ...]*

Return the authenticated component order.

<a id="eutaxis.declarations.external_composition.ExternalCumulativeArtifact"></a>

### *class* eutaxis.declarations.external_composition.ExternalCumulativeArtifact(\*\_args, \*\*\_kwargs)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Expose cumulative bytes that remain bound to external authority.

* **Parameters:**
  * **\_args** ([*object*](https://docs.python.org/3/builtins/functions.html#object))
  * **\_kwargs** ([*object*](https://docs.python.org/3/builtins/functions.html#object))

<a id="eutaxis.declarations.external_composition.ExternalCumulativeArtifact.manifest"></a>

#### *property* manifest *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Return the authenticated composition-manifest identifier.

<a id="eutaxis.declarations.external_composition.ExternalCumulativeArtifact.scope"></a>

#### *property* scope *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Return the authenticated artifact scope.

<a id="eutaxis.declarations.external_composition.ExternalCumulativeArtifact.target"></a>

#### *property* target *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Return the authenticated artifact target.

<a id="eutaxis.declarations.external_composition.ExternalCumulativeArtifact.content"></a>

#### *property* content *: [bytes](https://docs.python.org/3/builtins/stdtypes.html#bytes)*

Return the authenticated canonical artifact bytes.

<a id="eutaxis.declarations.external_composition.ExternalCumulativeArtifact.text"></a>

#### *property* text *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

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
  * **fragments** ([*Mapping*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* [*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *]*)
* **Return type:**
  [*ExternalCumulativeArtifact*](#eutaxis.declarations.external_composition.ExternalCumulativeArtifact)

<a id="eutaxis.declarations.external_composition.render_external_cumulative_markdown"></a>

### eutaxis.declarations.external_composition.render_external_cumulative_markdown(plan)

Render one external cumulative plan from its authenticated catalog.

* **Parameters:**
  **plan** ([*ExternalCumulativeCompositionPlan*](#eutaxis.declarations.external_composition.ExternalCumulativeCompositionPlan))
* **Return type:**
  [*ExternalCumulativeArtifact*](#eutaxis.declarations.external_composition.ExternalCumulativeArtifact)

<a id="structured-procedure-skill-planning"></a>

## Structured procedure Skill planning

<a id="eutaxis.declarations.models.SupportResourceReference"></a>

### *class* eutaxis.declarations.models.SupportResourceReference(resource, destination)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Place one acquired resource inside an operation’s Skill artifact.

* **Parameters:**
  * **resource** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **destination** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))

<a id="eutaxis.declarations.models.SupportResourceReference.resource"></a>

#### resource *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.models.SupportResourceReference.destination"></a>

#### destination *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="module-eutaxis.declarations.structured_skill"></a>

Plan one authenticated structured procedure Skill and its resource closure.

<a id="eutaxis.declarations.structured_skill.PlannedSupportResource"></a>

### *class* eutaxis.declarations.structured_skill.PlannedSupportResource(operation, resource, destination)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Bind one operation dependency to exact acquired bytes and a destination.

* **Parameters:**
  * **operation** (*VersionedReference*)
  * **resource** ([*AcquiredResource*](#eutaxis.declarations.external_result.AcquiredResource))
  * **destination** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))

<a id="eutaxis.declarations.structured_skill.PlannedSupportResource.operation"></a>

#### operation *: VersionedReference*

<a id="eutaxis.declarations.structured_skill.PlannedSupportResource.resource"></a>

#### resource *: [AcquiredResource](#eutaxis.declarations.external_result.AcquiredResource)*

<a id="eutaxis.declarations.structured_skill.PlannedSupportResource.destination"></a>

#### destination *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.structured_skill.StructuredSkillPlan"></a>

### *class* eutaxis.declarations.structured_skill.StructuredSkillPlan(\*\_args, \*\*\_kwargs)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Expose an authenticated structured procedure and resource closure.

* **Parameters:**
  * **\_args** ([*object*](https://docs.python.org/3/builtins/functions.html#object))
  * **\_kwargs** ([*object*](https://docs.python.org/3/builtins/functions.html#object))

<a id="eutaxis.declarations.structured_skill.StructuredSkillPlan.manifest"></a>

#### *property* manifest *: CompositionManifestDeclaration*

Return the exact separate-directory manifest.

<a id="eutaxis.declarations.structured_skill.StructuredSkillPlan.name"></a>

#### *property* name *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Return the authenticated Skill name.

<a id="eutaxis.declarations.structured_skill.StructuredSkillPlan.scope"></a>

#### *property* scope *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Return the authenticated installation scope.

<a id="eutaxis.declarations.structured_skill.StructuredSkillPlan.invocation"></a>

#### *property* invocation *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), ...]*

Return the authenticated invocation routes.

<a id="eutaxis.declarations.structured_skill.StructuredSkillPlan.procedure"></a>

#### *property* procedure *: ProcedureDeclaration*

Return the exact selected root procedure.

<a id="eutaxis.declarations.structured_skill.StructuredSkillPlan.operations"></a>

#### *property* operations *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[OperationDeclaration, ...]*

Return exact operations in first action-reference order.

<a id="eutaxis.declarations.structured_skill.StructuredSkillPlan.support_resources"></a>

#### *property* support_resources *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[PlannedSupportResource](#eutaxis.declarations.structured_skill.PlannedSupportResource), ...]*

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
  * **entrypoint_max_bytes** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **artifact_max_bytes** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
* **Return type:**
  [*RenderedArtifact*](commands.md#eutaxis.commands.models.RenderedArtifact)

<a id="module-eutaxis.declarations.catalog"></a>

<a id="declaration-catalog"></a>

## Declaration catalog

Build a portable static catalog from a validated declaration registry.

<a id="eutaxis.declarations.catalog.ExactContractKey"></a>

### *class* eutaxis.declarations.catalog.ExactContractKey(kind, id, version)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One exact evaluator or operation contract key.

* **Parameters:**
  * **kind** (*DeclarationKind*)
  * **id** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **version** ([*int*](https://docs.python.org/3/builtins/functions.html#int))

<a id="eutaxis.declarations.catalog.ExactContractKey.kind"></a>

#### kind *: DeclarationKind*

<a id="eutaxis.declarations.catalog.ExactContractKey.id"></a>

#### id *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.catalog.ExactContractKey.version"></a>

#### version *: [int](https://docs.python.org/3/builtins/functions.html#int)*

<a id="eutaxis.declarations.catalog.CatalogSource"></a>

### *class* eutaxis.declarations.catalog.CatalogSource(namespace, path, sha256)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Portable provenance for one source snapshot.

* **Parameters:**
  * **namespace** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* *None*)
  * **path** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **sha256** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))

<a id="eutaxis.declarations.catalog.CatalogSource.namespace"></a>

#### namespace *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

<a id="eutaxis.declarations.catalog.CatalogSource.path"></a>

#### path *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.catalog.CatalogSource.sha256"></a>

#### sha256 *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.catalog.DeclarationCatalog"></a>

### *class* eutaxis.declarations.catalog.DeclarationCatalog(revision, facet_content_revision, source_root, sources, declarations, contracts, conflicts)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Immutable static lookups over one validated declaration registry.

* **Parameters:**
  * **revision** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **facet_content_revision** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* *None*)
  * **source_root** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *|* *None*)
  * **sources** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*CatalogSource*](#eutaxis.declarations.catalog.CatalogSource) *,*  *...* *]*)
  * **declarations** ([*Mapping*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* *RegisteredDeclaration* *]*)
  * **contracts** ([*Mapping*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) *[*[*ExactContractKey*](#eutaxis.declarations.catalog.ExactContractKey) *,* *RegisteredDeclaration* *]*)
  * **conflicts** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* [*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *]* *,*  *...* *]*)

<a id="eutaxis.declarations.catalog.DeclarationCatalog.revision"></a>

#### revision *: [int](https://docs.python.org/3/builtins/functions.html#int)*

<a id="eutaxis.declarations.catalog.DeclarationCatalog.facet_content_revision"></a>

#### facet_content_revision *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

<a id="eutaxis.declarations.catalog.DeclarationCatalog.source_root"></a>

#### source_root *: [Path](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [None](https://docs.python.org/3/builtins/constants.html#None)*

<a id="eutaxis.declarations.catalog.DeclarationCatalog.sources"></a>

#### sources *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[CatalogSource](#eutaxis.declarations.catalog.CatalogSource), ...]*

<a id="eutaxis.declarations.catalog.DeclarationCatalog.declarations"></a>

#### declarations *: [Mapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), RegisteredDeclaration]*

<a id="eutaxis.declarations.catalog.DeclarationCatalog.contracts"></a>

#### contracts *: [Mapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[ExactContractKey](#eutaxis.declarations.catalog.ExactContractKey), RegisteredDeclaration]*

<a id="eutaxis.declarations.catalog.DeclarationCatalog.conflicts"></a>

#### conflicts *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)], ...]*

<a id="eutaxis.declarations.catalog.DeclarationCatalog.get"></a>

#### get(identifier)

Return one unversioned record, or `None` when it is absent.

* **Parameters:**
  **identifier** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  *RegisteredDeclaration* | None

<a id="eutaxis.declarations.catalog.DeclarationCatalog.get_contract"></a>

#### get_contract(kind, identifier, version)

Return one exact evaluator or operation contract when present.

* **Parameters:**
  * **kind** (*DeclarationKind*)
  * **identifier** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **version** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
* **Return type:**
  *RegisteredDeclaration* | None

<a id="eutaxis.declarations.catalog.DeclarationCatalog.filter_static"></a>

#### filter_static(query)

Return records whose stored fields satisfy every exact predicate.

* **Parameters:**
  **query** (*StaticCatalogQuery*)
* **Return type:**
  [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[*RegisteredDeclaration*, …]

<a id="eutaxis.declarations.catalog.DeclarationCatalog.filter_enforcement"></a>

#### filter_enforcement(enforcement)

Return authored obligations with one declared enforcement class.

* **Parameters:**
  **enforcement** (*EnforcementClass*)
* **Return type:**
  [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[*RuleCriterionEnforcement* | *ProcedurePredicateEnforcement* | *OperationPredicateEnforcement*, …]

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
  [bytes](https://docs.python.org/3/builtins/stdtypes.html#bytes)

<a id="module-eutaxis.declarations.persisted_catalog"></a>

<a id="persisted-catalog"></a>

## Persisted catalog

Load an immutable static projection from persisted catalog-index JSON.

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogRelation"></a>

### *class* eutaxis.declarations.persisted_catalog.PersistedCatalogRelation(type, target)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One typed relation retained by a persisted index row.

* **Parameters:**
  * **type** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **target** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogRelation.type"></a>

#### type *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogRelation.target"></a>

#### target *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogProvenance"></a>

### *class* eutaxis.declarations.persisted_catalog.PersistedCatalogProvenance(namespace, path, document_path, line, column)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Portable source coordinates retained by a persisted index row.

* **Parameters:**
  * **namespace** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* *None*)
  * **path** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **document_path** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* [*int*](https://docs.python.org/3/builtins/functions.html#int) *,*  *...* *]*)
  * **line** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **column** ([*int*](https://docs.python.org/3/builtins/functions.html#int))

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogProvenance.namespace"></a>

#### namespace *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogProvenance.path"></a>

#### path *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogProvenance.document_path"></a>

#### document_path *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str) | [int](https://docs.python.org/3/builtins/functions.html#int), ...]*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogProvenance.line"></a>

#### line *: [int](https://docs.python.org/3/builtins/functions.html#int)*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogProvenance.column"></a>

#### column *: [int](https://docs.python.org/3/builtins/functions.html#int)*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry"></a>

### *class* eutaxis.declarations.persisted_catalog.PersistedCatalogEntry(id, kind, owner, status, source_revision, schema_version, applicability, relations, query, containing_rule_set, source, version)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A lossy static index row, not a semantic source declaration.

* **Parameters:**
  * **id** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **kind** (*DeclarationKind*)
  * **owner** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **status** (*DeclarationStatus*)
  * **source_revision** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **schema_version** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **applicability** ([*Mapping*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* *None* *|* [*bool*](https://docs.python.org/3/builtins/functions.html#bool) *|* [*int*](https://docs.python.org/3/builtins/functions.html#int) *|* [*float*](https://docs.python.org/3/builtins/functions.html#float) *|* [*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* [*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[**None* *|* [*bool*](https://docs.python.org/3/builtins/functions.html#bool) *|* [*int*](https://docs.python.org/3/builtins/functions.html#int) *|* [*float*](https://docs.python.org/3/builtins/functions.html#float) *|* [*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* [*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[**JsonValue* *,*  *...* *]*  *|* [*Mapping*](https://docs.python.org/3/library/typing.html#typing.Mapping) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* *JsonValue* *]* *,*  *...* *]*  *|* [*Mapping*](https://docs.python.org/3/library/typing.html#typing.Mapping) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* *None* *|* [*bool*](https://docs.python.org/3/builtins/functions.html#bool) *|* [*int*](https://docs.python.org/3/builtins/functions.html#int) *|* [*float*](https://docs.python.org/3/builtins/functions.html#float) *|* [*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* [*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[**JsonValue* *,*  *...* *]*  *|* [*Mapping*](https://docs.python.org/3/library/typing.html#typing.Mapping) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* *JsonValue* *]* *]* *]*)
  * **relations** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*PersistedCatalogRelation*](#eutaxis.declarations.persisted_catalog.PersistedCatalogRelation) *,*  *...* *]*)
  * **query** ([*Mapping*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* *None* *|* [*bool*](https://docs.python.org/3/builtins/functions.html#bool) *|* [*int*](https://docs.python.org/3/builtins/functions.html#int) *|* [*float*](https://docs.python.org/3/builtins/functions.html#float) *|* [*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* [*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[**None* *|* [*bool*](https://docs.python.org/3/builtins/functions.html#bool) *|* [*int*](https://docs.python.org/3/builtins/functions.html#int) *|* [*float*](https://docs.python.org/3/builtins/functions.html#float) *|* [*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* [*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[**JsonValue* *,*  *...* *]*  *|* [*Mapping*](https://docs.python.org/3/library/typing.html#typing.Mapping) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* *JsonValue* *]* *,*  *...* *]*  *|* [*Mapping*](https://docs.python.org/3/library/typing.html#typing.Mapping) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* *None* *|* [*bool*](https://docs.python.org/3/builtins/functions.html#bool) *|* [*int*](https://docs.python.org/3/builtins/functions.html#int) *|* [*float*](https://docs.python.org/3/builtins/functions.html#float) *|* [*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* [*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[**JsonValue* *,*  *...* *]*  *|* [*Mapping*](https://docs.python.org/3/library/typing.html#typing.Mapping) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* *JsonValue* *]* *]* *]*)
  * **containing_rule_set** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* *None*)
  * **source** ([*PersistedCatalogProvenance*](#eutaxis.declarations.persisted_catalog.PersistedCatalogProvenance))
  * **version** ([*int*](https://docs.python.org/3/builtins/functions.html#int) *|* *None*)

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.id"></a>

#### id *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.kind"></a>

#### kind *: DeclarationKind*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.owner"></a>

#### owner *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.status"></a>

#### status *: DeclarationStatus*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.source_revision"></a>

#### source_revision *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.schema_version"></a>

#### schema_version *: [int](https://docs.python.org/3/builtins/functions.html#int)*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.applicability"></a>

#### applicability *: [Mapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [None](https://docs.python.org/3/builtins/constants.html#None) | [bool](https://docs.python.org/3/builtins/functions.html#bool) | [int](https://docs.python.org/3/builtins/functions.html#int) | [float](https://docs.python.org/3/builtins/functions.html#float) | [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[None](https://docs.python.org/3/builtins/constants.html#None) | [bool](https://docs.python.org/3/builtins/functions.html#bool) | [int](https://docs.python.org/3/builtins/functions.html#int) | [float](https://docs.python.org/3/builtins/functions.html#float) | [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[JsonValue, ...] | [Mapping](https://docs.python.org/3/library/typing.html#typing.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), JsonValue], ...] | [Mapping](https://docs.python.org/3/library/typing.html#typing.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [None](https://docs.python.org/3/builtins/constants.html#None) | [bool](https://docs.python.org/3/builtins/functions.html#bool) | [int](https://docs.python.org/3/builtins/functions.html#int) | [float](https://docs.python.org/3/builtins/functions.html#float) | [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[JsonValue, ...] | [Mapping](https://docs.python.org/3/library/typing.html#typing.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), JsonValue]]]*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.relations"></a>

#### relations *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[PersistedCatalogRelation](#eutaxis.declarations.persisted_catalog.PersistedCatalogRelation), ...]*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.query"></a>

#### query *: [Mapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [None](https://docs.python.org/3/builtins/constants.html#None) | [bool](https://docs.python.org/3/builtins/functions.html#bool) | [int](https://docs.python.org/3/builtins/functions.html#int) | [float](https://docs.python.org/3/builtins/functions.html#float) | [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[None](https://docs.python.org/3/builtins/constants.html#None) | [bool](https://docs.python.org/3/builtins/functions.html#bool) | [int](https://docs.python.org/3/builtins/functions.html#int) | [float](https://docs.python.org/3/builtins/functions.html#float) | [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[JsonValue, ...] | [Mapping](https://docs.python.org/3/library/typing.html#typing.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), JsonValue], ...] | [Mapping](https://docs.python.org/3/library/typing.html#typing.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [None](https://docs.python.org/3/builtins/constants.html#None) | [bool](https://docs.python.org/3/builtins/functions.html#bool) | [int](https://docs.python.org/3/builtins/functions.html#int) | [float](https://docs.python.org/3/builtins/functions.html#float) | [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[JsonValue, ...] | [Mapping](https://docs.python.org/3/library/typing.html#typing.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), JsonValue]]]*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.containing_rule_set"></a>

#### containing_rule_set *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.source"></a>

#### source *: [PersistedCatalogProvenance](#eutaxis.declarations.persisted_catalog.PersistedCatalogProvenance)*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogEntry.version"></a>

#### version *: [int](https://docs.python.org/3/builtins/functions.html#int) | [None](https://docs.python.org/3/builtins/constants.html#None)*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex"></a>

### *class* eutaxis.declarations.persisted_catalog.PersistedCatalogIndex(revision, facet_content_revision, sources, declarations, contracts, conflicts)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

An immutable query projection, never a registry or resolver input.

* **Parameters:**
  * **revision** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
  * **facet_content_revision** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *|* *None*)
  * **sources** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*CatalogSource*](#eutaxis.declarations.catalog.CatalogSource) *,*  *...* *]*)
  * **declarations** ([*Mapping*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* [*PersistedCatalogEntry*](#eutaxis.declarations.persisted_catalog.PersistedCatalogEntry) *]*)
  * **contracts** ([*Mapping*](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) *[*[*ExactContractKey*](#eutaxis.declarations.catalog.ExactContractKey) *,* [*PersistedCatalogEntry*](#eutaxis.declarations.persisted_catalog.PersistedCatalogEntry) *]*)
  * **conflicts** ([*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*tuple*](https://docs.python.org/3/builtins/stdtypes.html#tuple) *[*[*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *,* [*str*](https://docs.python.org/3/builtins/stdtypes.html#str) *]* *,*  *...* *]*)

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex.revision"></a>

#### revision *: [int](https://docs.python.org/3/builtins/functions.html#int)*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex.facet_content_revision"></a>

#### facet_content_revision *: [str](https://docs.python.org/3/builtins/stdtypes.html#str) | [None](https://docs.python.org/3/builtins/constants.html#None)*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex.sources"></a>

#### sources *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[CatalogSource](#eutaxis.declarations.catalog.CatalogSource), ...]*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex.declarations"></a>

#### declarations *: [Mapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [PersistedCatalogEntry](#eutaxis.declarations.persisted_catalog.PersistedCatalogEntry)]*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex.contracts"></a>

#### contracts *: [Mapping](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping)[[ExactContractKey](#eutaxis.declarations.catalog.ExactContractKey), [PersistedCatalogEntry](#eutaxis.declarations.persisted_catalog.PersistedCatalogEntry)]*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex.conflicts"></a>

#### conflicts *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)], ...]*

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex.get"></a>

#### get(identifier)

Return one unversioned row, or `None` when it is absent.

* **Parameters:**
  **identifier** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
* **Return type:**
  [*PersistedCatalogEntry*](#eutaxis.declarations.persisted_catalog.PersistedCatalogEntry) | None

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex.get_contract"></a>

#### get_contract(kind, identifier, version)

Return one exact evaluator or operation row when present.

* **Parameters:**
  * **kind** (*DeclarationKind*)
  * **identifier** ([*str*](https://docs.python.org/3/builtins/stdtypes.html#str))
  * **version** ([*int*](https://docs.python.org/3/builtins/functions.html#int))
* **Return type:**
  [*PersistedCatalogEntry*](#eutaxis.declarations.persisted_catalog.PersistedCatalogEntry) | None

<a id="eutaxis.declarations.persisted_catalog.PersistedCatalogIndex.filter_static"></a>

#### filter_static(query)

Return rows whose stored fields satisfy every exact predicate.

* **Parameters:**
  **query** (*StaticCatalogQuery*)
* **Return type:**
  [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[*PersistedCatalogEntry*](#eutaxis.declarations.persisted_catalog.PersistedCatalogEntry), …]

<a id="eutaxis.declarations.persisted_catalog.load_persisted_catalog_index"></a>

### eutaxis.declarations.persisted_catalog.load_persisted_catalog_index(data, \*, source=None)

Load and validate one persisted static index without semantic recovery.

* **Parameters:**
  * **data** ([*bytes*](https://docs.python.org/3/builtins/stdtypes.html#bytes))
  * **source** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *|* *None*)
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
  [*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

<a id="eutaxis.declarations.catalog_schema.catalog_index_schema"></a>

### eutaxis.declarations.catalog_schema.catalog_index_schema()

Return an isolated copy of the current static catalog-index schema.

* **Return type:**
  [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [object](https://docs.python.org/3/builtins/functions.html#object)]

<a id="eutaxis.declarations.catalog_schema.validate_catalog_index_payload"></a>

### eutaxis.declarations.catalog_schema.validate_catalog_index_payload(payload, \*, source=None)

Validate one index payload and return its mapping representation.

* **Parameters:**
  * **payload** ([*object*](https://docs.python.org/3/builtins/functions.html#object))
  * **source** ([*Path*](https://docs.python.org/3/library/pathlib.html#pathlib.Path) *|* *None*)
* **Return type:**
  [*Mapping*](https://docs.python.org/3/library/typing.html#typing.Mapping)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [object](https://docs.python.org/3/builtins/functions.html#object)]
