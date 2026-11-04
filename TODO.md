# TODO

This file guides work on Eutaxis. Open entries state unfinished tasks. Completed entries link to the corresponding documentation.

## Recently shipped

The following work is complete.

- [x] [Config-driven Skills compilation](docs/guide/usage.md#author-on-demand-rule-sets-as-skills) (`eutaxis skills` sub-app).
- [x] [Source-schema fields and compiler gate](docs/adr/failure-mode-as-source-field.md) (`invocation`, `failure-mode`, `required-visibility`); closes [silent-failure-classification](docs/open-questions/silent-failure-classification.md).
- [x] [Ownership-boundaries navigation ADR](docs/adr/instruction-file-ownership-boundaries.md); narrows [instruction-file-ownership](docs/open-questions/instruction-file-ownership.md) to the always-on partial-ownership case.
- [x] `task_modules_router_enabled` config flag; see [Configuration](docs/guide/configuration.md).
- [x] User-facing documentation rewrite ([README](README.md), [Concepts](docs/guide/concepts.md), [Usage](docs/guide/usage.md)).
- [x] [Clean-memory operation as a Skill](docs/adr/dual-ownership-marker.md) (`eutaxis commands install clean-memory` + `eutaxis ops clean-memory`).
- [x] [Rule query and progressive disclosure](docs/adr/rule-level-access-to-modules.md) (`eutaxis rule show|list`, `disclosure: progressive`).
- [x] [Loading-unit budgets](docs/guide/configuration.md#^skill-loading-budgets) for Skill entrypoints, read batches and complete activation routes.
- [x] [Skills command](docs/guide/cli-reference.md#^skills-command): previews changes, removes only recorded artifacts and recovers idempotently.

## Priority

- [ ] **Complete the external-source path and run the Oikos pilot.** Close every pre-pilot gate in the [staged implementation plan](docs/internals/structured-declaration-system-plan.md), then run the reversible pilot.
- [ ] **Convert additional Oikos sources only after the pilot.** Do not rename the source directories before the pilot and its rollback gate pass.
- [ ] Review the archived sources and decide which content to include, which can be deleted safely.
- [ ] Implement a functionality to cleanup config files. This involves:
  - detecting the configs in Codex (TOML) and Claude code (JSON) that violate the recommended patterns,
  - enforcing the recommended practices.
- [ ] **Ship a `regenerate-instructions` skill that wraps `eutaxis generate` as a slash command.** Surfaced in the README as a deferred item: the skill shape — a one-shot CLI invocation rather than a Markdown body — does not match the current `commands` subsystem, whose skill sources are authored as Markdown templates with optional shell-backed actions. Two routes: extend the subsystem with a CLI-invocation skill kind, or document the residual gap in the user-facing docs and accept that `eutaxis generate -c <config>` remains the direct entry point.
- [ ] **Promote a managed-region ownership ADR for the always-on regime when a real consumer surfaces.** Required to close the residual scope of [instruction-file-ownership](docs/open-questions/instruction-file-ownership.md) (delimited regions inside an otherwise hand-authored cumulative file). No current consumer; the candidate resolution (`<!-- eutaxis:begin name=... -->` / `<!-- eutaxis:end -->` delimiters with content-hash idempotency) is recorded in the open-question page and not yet ratified.

## Next steps

- [ ] Stabilize the prompt-family layout and starter templates
- [ ] Implement scaffold CLI command for prompt-composition projects
- [ ] Extend `generate` beyond plain concatenation
- [ ] Implement validate CLI command for prompt families
- [ ] Define family profiles and advisory diagnostics
- [ ] Add starter composition config templates
- [ ] Write tests for `generate`
- [ ] Write tests for CLI entry points

## Long term

- [ ] Review the design architecture.
- [ ] Complete the workflows and audit parts.
- [ ] Reassess physical rule-set boundaries after the structured-source pilot; split only when responsibilities or activation conditions compete.
- [ ] Create the templates for the notes types and audits.
- [ ] Write the workflow prompts.
- [ ] Design the registry files and utilities.
- [ ] Migrate the existing notes.
