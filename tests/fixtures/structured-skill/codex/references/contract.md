# Complete procedure contract

**oikos/complete-module**:

*Kind.* Procedure.

Complete one module through guarded index publication

*Parameters.*

```json
{"additionalProperties":false,"properties":{},"type":"object"}
```

*Entry.* `publish`

*Preconditions.*
- None

*Actions.*

**`publish`.**
- Operation: `oikos/publish-index@1`
- Bindings:
  - None
- On success: `published`
- On failure:
  - `publish-failed` → `publish-failed`

*Effects.*
- `git/index`

*Postconditions.*

**`published` (postcondition).**
- Evaluator: None
- Observes: None
- Expression:

```json
{"facet":"artifact.created","operator":"equals","value":true}
```

*Failure outcomes.*
- `publish-failed`

*Operation contracts.*

**`oikos/publish-index@1`.**

*Inputs.*

```json
{"additionalProperties":false,"properties":{},"type":"object"}
```

*Outputs.*

```json
{"additionalProperties":false,"properties":{},"type":"object"}
```

*Preconditions.*
- None

*Method.*

Publish only the guarded Git-index paths.

*Support resources.*
- `oikos/publish-index` → `scripts/publish-index.py`

*Effects.*
- `git/index`

*Failure outcomes.*
- `publish-failed`

*Recovery.* Leave the guarded paths unchanged.
