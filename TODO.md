# TODO

## Priority

- [ ] In Oikos, reformat the rules systematically (label, do, do not with embedded examples).
- [ ] Clean the TODO itself for outdated or irrelevant items.
- [ ] Review the archived sources and decide which content to include, which can be deleted safely.
- [ ] Implement a functionality to cleanup config files. This involves:
  - detecting the configs in Codex (TOML) and Claude code (JSON) that violate the recommended patterns,
  - enforcing the recommended practices.
- [x] Implement a functionality to clean memory in both agents. Shipped as the commands subsystem (`eutaxis commands install clean-memory`) plus the doer (`eutaxis ops clean-memory`). Compiles to an Agent Skill on both Claude and Codex. See [docs/adr/](docs/adr/index.md) for the design decisions and [docs/open-questions/](docs/open-questions/_index.md) for the remaining framework-level questions.
- [ ] Implement a rule template validation to enforce a uniform structure in instruction files.

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
