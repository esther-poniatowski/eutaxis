<a id="declarations"></a>

# Declarations

External declaration acquisition: verify one external corpus and expose its portable source coordinates through an authenticated result.

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
