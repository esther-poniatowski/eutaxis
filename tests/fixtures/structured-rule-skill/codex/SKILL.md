---
description: Test code behavior at the boundary
name: testing
x-eutaxis-owned: 497a2987ff532388
---

# Testing

Test code behavior at the boundary

*Why.* Tests must expose behavioral regressions

**test-design**:

✓ Agent MUST preserve the boundary.

*How to apply.* Pass every external collaborator explicitly

*Why.* Ambient state prevents controlled inputs

*Decision criterion.* unit-runs-with-test-doubles

*Why.* Isolated behavior reveals the failing boundary

*Exception.* `generated-boundary`: When `{"facet":"artifact.created","operator":"equals","value":false}`, waive:
- `preserve-boundary`: Agent MUST preserve the boundary.

*Why.* No generated artifact exists yet

**test-coverage**:

✓ Agent MUST preserve the boundary.
