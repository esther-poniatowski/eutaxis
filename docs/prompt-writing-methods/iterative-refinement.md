# Iterative refinement

## Human-side testing

An evidence-informed refinement protocol is:

1. **Behavioral testing against adversarial inputs**: construct inputs that probe the boundary of each constraint. Failure modes reveal underspecified or conflicting rules.
2. **Coverage analysis**: for each behavioral requirement in the original specification, verify a corresponding instruction exists. Missing instructions are the primary source of silent failures.
3. **Redundancy elimination**: duplicate instructions create maintenance coupling and can produce contradictions under independent modification. Each behavioral requirement should have exactly one authoritative instruction.
4. **Compression without information loss**: every sentence that does not alter behavior may be removed.

## Model-side verification

Human-side testing addresses prompt _design_; model-side verification addresses output _quality at inference time_. Three mechanisms are increasingly standard in production systems:

- **Self-audit against the constraint set.** The instruction file explicitly directs the model to check its output against the stated constraints before committing. This is a lightweight postcondition pass built into the prompt itself (e.g., "before returning your response, verify that every section required by the contract is present and that no forbidden pattern appears").
- **Constitutional critique-revision cycles.** The model generates a candidate output, then critiques it against a specified set of principles, then revises. This can be implemented as a single-prompt loop (generate → critique → revise) or as a multi-turn orchestration. The critique step is most effective when the principles are stated as verifiable conditions, not vague desiderata.
- **Self-consistency sampling.** Multiple generations are produced for the same input and compared. Agreement across samples increases confidence; disagreement flags underspecified instructions or ambiguous inputs. This is especially useful for tasks where correctness is hard to verify but consistency is informative.

These mechanisms complement human-side testing: testing catches systematic prompt defects; model-side verification catches per-instance failures at inference time.
