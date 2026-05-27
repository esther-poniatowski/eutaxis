# TODO

## Recently shipped

- [x] **Skills compilation surface for rule-set / task-module sources.** The `commands` subsystem accepts config-driven sources via `load_from_instruction_config`. A new `eutaxis skills` CLI sub-app (`list` / `show` / `install` / `uninstall` / `diff`) compiles every instruction file registered in an instruction-assembly configuration to a native Agent Skill artifact under each adapter's user-scope or project-scope skill directory. Both adapters omit the model-invocation block when `model` appears in the source's `invocation` list. See ADRs [agent-skills-as-target-surface](docs/adr/agent-skills-as-target-surface.md) and [convergence-on-agent-skills-standard](docs/adr/convergence-on-agent-skills-standard.md) for the target surface.
- [x] **Source-schema fields and compiler gate.** Every Skill source declares `invocation` (list of permitted routes `user`, `model`), `failure-mode` (`silent` | `visible`, mandatory), and `required-visibility` (`pre-invocation` | `pre-action`, mandatory when silent). The renderer refuses model-invocation routing for silent-failure sources and refuses any skill from a silent source whose `required-visibility` is `pre-invocation`. The gate is unconditional (no `--force` escape). See ADR [failure-mode-as-source-field](docs/adr/failure-mode-as-source-field.md), which closes the open question on silent-failure classification.
- [x] **`task_modules_router_enabled` config flag.** Suppresses the router section in the cumulative instruction file when set to `false`, while keeping the `task_modules:` list available for the Skills compiler. Consumers that have migrated to native Skills set it to `false`; the default stays `true` for backward compatibility.
- [x] **Ownership-boundaries navigation ADR.** [instruction-file-ownership-boundaries](docs/adr/instruction-file-ownership-boundaries.md) records the boundary between the three target classes and the ADR (or open question) that governs each one. The on-demand half is owned by [dual-ownership-marker](docs/adr/dual-ownership-marker.md); the always-on whole-file behaviour follows current generator semantics; the always-on partial-ownership case remains open. Narrows the scope of [instruction-file-ownership](docs/open-questions/instruction-file-ownership.md).
- [x] **User-facing documentation rewrite.** README realigned with the Keystone template (Overview / Features / Quick Start / Documentation / Contributing / Acknowledgments / License); one-line description restored; Conda and Last-Commit badges restored. A Supported agents table lists each agent and its cumulative-file and skill-directory paths; the rest of the documentation refers to that table by cross-link and stays platform-neutral. `docs/guide/concepts.md` is rewritten around the two compilation surfaces, the source schema, and the activation regimes. `docs/guide/usage.md` is reorganised around user goals. `docs/guide/configuration.md` documents `task_modules` and the new router flag.
- [x] Implement a functionality to clean memory in both agents. Shipped as the commands subsystem (`eutaxis commands install clean-memory`) plus the doer (`eutaxis ops clean-memory`). Compiles to an Agent Skill on both Claude and Codex.

## Priority

- [ ] In Oikos, reformat the rules systematically (label, do, do not with embedded examples).
- [ ] Clean the TODO itself for outdated or irrelevant items.
- [ ] Review the archived sources and decide which content to include, which can be deleted safely.
- [ ] Implement a functionality to cleanup config files. This involves:
  - detecting the configs in Codex (TOML) and Claude code (JSON) that violate the recommended patterns,
  - enforcing the recommended practices.
- [ ] Implement a rule template validation to enforce a uniform structure in instruction files.
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

- [ ] Turn eutaxis into a fully configurable rule generator. Predefine behavioral rules with identifiers and let users decide how to configure each rule in YAML. Then eutaxis generates instructions for these rules in the appropriate instruction files. Users can override the rule formulations if needed.
- [ ] Review the design architecture.
- [ ] Complete the workflows and audit parts.
- [ ] Create one subfolder for each type of decision rules: epistemology (content validity, logical inference, relevance), argumentation (exposition, presentation structure), stylistic (redaction).
- [ ] Create one note per quality criteria, stating the norm, rationale, and precise operational procedures.
- [ ] Create the templates for the notes types and audits.
- [ ] Write the workflow prompts.
- [ ] Design the registry files and utilities.
- [ ] Migrate the existing notes.
