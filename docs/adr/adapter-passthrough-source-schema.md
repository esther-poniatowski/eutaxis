# Adapter-passthrough frontmatter and files in the source schema

## Status

Accepted.

## Context

The two supported agents diverge sharply on permission and metadata fields, and the source schema has to let a single declaration target both.

Claude `allowed-tools` is a first-class permission grant that applies while the skill is active (`claude/skills-authoring.md:194-207`). Codex `allowed-tools` is **experimental** and explicitly documented as *metadata only, not a permission grant* (`skills-comparison.md:106`); the pattern syntax also differs (Claude space-and-glob `Bash(cmd <args>*)`, Codex colon `Bash(cmd:*)`). Codex carries `policy.allow_implicit_invocation` and `dependencies.tools[]` in `agents/openai.yaml`, which has no Claude analogue (`codex/skills.md:79-100`). Claude carries `disable-model-invocation`, `user-invocable`, `argument-hint`, `arguments`, `paths`, `model`, `effort`, `context`, `agent`, `hooks`, `shell` in `SKILL.md` frontmatter (`claude/skills-authoring.md:55-69`), most without a Codex counterpart.

The legacy schema hard-coded each adapter's frontmatter inside its adapter class. To author a `clean-memory` that grants `Bash(eutaxis ops clean-memory*)` on Claude, a user had to edit `adapters/claude.py` — the proposal's §7 promise ("drop a `.md` into `~/.eutaxis/commands/`") broke down for any non-trivial command.

## Decision

Add a top-level `adapters` mapping to the source frontmatter. Each key is an adapter name; each value carries two slots:

```yaml
adapters:
  claude:
    frontmatter:
      allowed-tools: "Bash(eutaxis ops clean-memory*)"
  codex:
    files:
      "agents/openai.yaml": |
        dependencies:
          tools:
            - type: shell
              value: eutaxis
              description: Eutaxis CLI used by clean-memory.
```

- `adapters.<name>.frontmatter` — extra keys merged into the rendered `SKILL.md` frontmatter for that adapter.
- `adapters.<name>.files` — sibling file contents keyed by POSIX relative path. Templated against the same context as the body.

The loader parses these into `AdapterPassthrough(frontmatter: dict, files: dict[str, str])` records on `CommandSource`. Adapters consume their own passthrough during rendering; unknown adapter names are tolerated, which keeps the schema forward-compatible.

Adapters may **reject** passthrough keys they consider unsafe. The Codex adapter raises `CommandError` if `adapters.codex.frontmatter` contains `allowed-tools`, pointing the author at `~/.codex/config.toml` for real pre-approval. The Claude adapter raises if any passthrough sets the reserved `x-eutaxis-owned` marker key.

## Discarded alternatives

- **Hard-code per-adapter frontmatter inside each adapter class** (the legacy approach). Rejected because the source can no longer specialise its output without editing the adapter; cross-agent compilation becomes a non-promise for any command that needs more than `name` and `description`.
- **A single, flat extended frontmatter** with no per-adapter scoping. Rejected because keys mean different things on different agents: `disable-model-invocation` is Claude-only, `policy.allow_implicit_invocation` is Codex-only, and `allowed-tools` is a permission grant on one side and metadata on the other.
- **Passthrough frontmatter only** (no `files` slot). Rejected because Codex `agents/openai.yaml` is a sibling file, not a frontmatter key; representing it as frontmatter would require the adapter to invent one-off serialisation rules.
- **Silently drop disallowed passthrough keys per adapter.** Rejected because silent drops train authors to assume their declarations took effect; raising surfaces the cross-agent asymmetry at authoring time and forces a correction.

## Rationale

The schema mirrors the documentation: shared fields at the top level, adapter-specific extensions under `adapters.<name>.{frontmatter,files}`. This stays honest about the cross-agent divergence rather than papering over it. Refusing unsafe keys at the adapter boundary makes the divergence visible where it matters — at the moment the artifact is built — instead of at runtime where the failure is harder to attribute.

## Consequences

- The loader validates the nested shape; tests cover non-string file contents and non-mapping `adapters[<name>]`.
- The Codex adapter is a deliberate surface for authoring footguns (refused `allowed-tools` passthrough; mismatched UI metadata can be introduced freely).
- Adding a third agent is an isolated change: register an adapter, read its own slot under `adapters.<new-name>`, ignore the others.
- The author of a built-in command (e.g. `clean-memory`) declares per-agent metadata in one source file rather than in separate per-adapter modules.
