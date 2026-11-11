**projection/all-modalities**:

✓ `required`: Agent MUST retain every required field before rendering.

*How to apply.* Keep `authored Markdown` intact.

Preserve its paragraph boundary.

*Why.* Required content defines the lower bound

✗ `prohibited`: Agent MUST NOT restore excluded content.

✓ `recommended`: Agent SHOULD retain the recommended form.

*Decision criterion.* recommended-check

✗ `discouraged`: Agent SHOULD NOT select the discouraged form.

*Decision criterion.* discouraged-check

✓ `permitted`: Agent MAY choose either equivalent form.

*Why.* The projection must preserve the complete effective rule

*Success criteria.*
- `required-check` [eutaxis/manual-judgment@1]: Required fields remain visible
- `prohibited-check` [eutaxis/manual-judgment@1]: Excluded content is not restored
- `recommended-check` [eutaxis/manual-judgment@1]: The recommendation is retained when its criterion wins
- `discouraged-check` [eutaxis/manual-judgment@1]: The discouraged form is absent when its criterion wins
- `permitted-check` [eutaxis/manual-judgment@1]: The discretionary choice remains explicit

**projection/branching-procedure** (procedure):

Exercises a graph whose entry is not its first authored node

*Why.* A rendered numbered list would misstate this graph

*Parameters.*

```json
{"additionalProperties":false,"properties":{"source":{"type":"string"}},"required":["source"],"type":"object"}
```

*Entry.* `choose`

*Preconditions.*

**`source-ready` (guard).**
- Evaluator: `eutaxis/manual-judgment@1`
- Observes: None
- Expression:

```json
{"facet":"projection.enabled","operator":"equals","value":true}
```

*Actions.*

**`finalize`.**
- Operation: `projection/transform@1`
- Bindings:
  - `marker`: literal `"final"`
  - `source`: parameter `source`
- On success: `complete`
- On failure:
  - `choose-failed` → `failed`
  - `finalize-failed` → `failed`
  - `recover-failed` → `failed`

**`recover`.**
- Operation: `projection/transform@1`
- Bindings:
  - `marker`: literal ````"value ``` with backticks"````
  - `source`: parameter `source`
- On success: `complete`
- On failure:
  - `choose-failed` → `failed`
  - `finalize-failed` → `failed`
  - `recover-failed` → `failed`

**`choose`.**
- Operation: `projection/transform@1`
- Bindings:
  - `marker`: literal `"choose"`
  - `source`: parameter `source`
- On success: `finalize`
- On failure:
  - `choose-failed` → `recover`
  - `finalize-failed` → `recover`
  - `recover-failed` → `recover`

*Invariants.*

**`source-remains-stable` (invariant).**
- Evaluator: `eutaxis/manual-judgment@1`
- Observes: `projection/source`
- Expression:

```json
{"facet":"projection.stable","operator":"equals","value":true}
```

*Effects.*
- `projection/artifact`

*Postconditions.*

**`complete` (postcondition).**
- Evaluator: `eutaxis/manual-judgment@1`
- Observes: None
- Expression:

```json
{"facet":"projection.done","operator":"equals","value":true}
```

*Failure outcomes.*
- `failed`

*Operation contracts.*

**`projection/transform@1`.**

*Why.* One exact operation serves every graph node in this fixture

*Inputs.*

```json
{"additionalProperties":false,"properties":{"marker":{"type":"string"},"source":{"type":"string"}},"required":["source","marker"],"type":"object"}
```

*Outputs.*

```json
{"additionalProperties":false,"properties":{"changed":{"type":"boolean"}},"required":["changed"],"type":"object"}
```

*Preconditions.*

**`source-ready` (guard).**
- Evaluator: `eutaxis/manual-judgment@1`
- Observes: None
- Expression:

```json
{"facet":"projection.enabled","operator":"equals","value":true}
```

*Method.*

Transform each source in declared order.

Inspect the `result` before publication.

*Effects.*
- `projection/artifact`

*Failure outcomes.*
- `choose-failed`
- `finalize-failed`
- `recover-failed`

*Recovery.* Preserve the input and report the failed graph node
