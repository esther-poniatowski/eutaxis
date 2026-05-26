# Regime translation and permission mapping per adapter

## Status

Accepted. Specialises [activation-regime-as-classification-axis](activation-regime-as-classification-axis.md) for the on-demand regime as compiled by the commands subsystem.

## Context

The source declares an **activation regime** that captures *who can invoke this artifact*. See [activation-regime-as-classification-axis](activation-regime-as-classification-axis.md) for the framework-level discussion of the four regimes; this ADR covers how `regime: user-invoked` (the v1 vocabulary) is translated into per-agent native flags. The v1 vocabulary has one value:

- `regime: user-invoked` — the artifact is invoked only by the user, never auto-selected by the model.

Each agent has its own native switch for this concept:

- **Claude**: `disable-model-invocation: true` in `SKILL.md` frontmatter (`claude/skills-authoring.md:60`, `claude/skills.md:55`). The model cannot pick the skill; the user must invoke explicitly with `/<name>`.
- **Codex**: `policy.allow_implicit_invocation: false` in `agents/openai.yaml` (`codex/skills.md:91-102`). Codex will not select the skill from the user's prompt, but explicit `$<name>` invocation still works.

Permission grants for shell commands the skill needs to run also diverge sharply between the two agents:

- **Claude `allowed-tools`** is a first-class permission grant that applies for the duration of the skill's activation (`claude/skills-authoring.md:194-207`). Pattern syntax is space-and- glob: `Bash(<cmd> <args>*)`.
- **Codex `allowed-tools`** is marked **experimental** in the Agent Skills standard and is documented as *metadata only, not a permission grant* (`skills-comparison.md:106`). The colon convention `Bash(<cmd>:*)` is informational. Real pre-approval lives outside the artifact, in `~/.codex/config.toml` (sandbox / approval policy / rules) — host configuration, not artifact metadata.

A naive cross-agent compiler that emits `allowed-tools` on both sides misleads the author into believing pre-approval is in effect on Codex.

## Decision

Adapters translate the regime per agent rather than emit it verbatim, and they enforce the permission asymmetry at the adapter boundary.

**Claude adapter:**

- Emits `disable-model-invocation: true` whenever `source.regime == "user-invoked"`.
- Honours `adapters.claude.frontmatter.allowed-tools` as a first-class permission grant; the rendered value reaches `SKILL.md` verbatim.
- Honours `argument_hint` from the source's top-level `argument-hint` key.

**Codex adapter:**

- Emits a derived `agents/openai.yaml` carrying `policy.allow_implicit_invocation: false` when `source.regime == "user-invoked"`. Any author-supplied `adapters.codex.files["agents/openai.yaml"]` is **deep-merged** on top of the derived defaults, so authors can extend `dependencies.tools` or `interface` without losing the regime policy.
- **Refuses** `adapters.codex.frontmatter.allowed-tools` with a `CommandError` whose message points at `~/.codex/config.toml` for real pre-approval. Silent acceptance would let authors ship artifacts that look pre-approved and are not.
- Does not emit `disable-model-invocation` (Claude-only).

The user takes a one-time Bash approval on Codex's first invocation of any skill that runs a shell command. The docs are explicit that there is no in-artifact way to skip this on Codex; this is documented in the adapter's module docstring and in the corrections report.

## Discarded alternatives

- **Emit `regime` as-is and let each adapter ignore it.** Rejected because every command source would then have to repeat both `disable-model-invocation: true` (for Claude) and the equivalent Codex `agents/openai.yaml` snippet, defeating the cross-agent compilation goal. The regime is exactly the cross-agent concept the compiler should translate.
- **Emit `allowed-tools` on Codex matching the Claude form.** Rejected because the docs are explicit that it is metadata only; emitting it would mislead authors into believing pre-approval took effect. The artifact-level error is a deliberate footgun guard.
- **Silently drop `adapters.codex.frontmatter.allowed-tools`.** Rejected because silent drops train authors to assume their declarations took effect. Raising at render time forces a correction at authoring.
- **Hard-code `agents/openai.yaml` from the regime and ignore passthrough.** Rejected because Codex `dependencies.tools` is legitimately author-controlled (it surfaces in the Codex UI), and `interface.*` fields are too. Deep-merge preserves both author control and the regime-derived policy.
- **Translate the regime in the loader rather than in the adapter.** Rejected because the translation is adapter-specific by definition; putting it in the loader would re-introduce per-agent special cases in a layer that should stay adapter-neutral.

## Rationale

Translating one cross-agent concept (`user-invoked`) into two native flags keeps the source DRY and forces the adapters — not the source — to know about each agent's permission model. Refusing footgun keys at adapter boundaries makes the cross-agent asymmetry visible at authoring time, when it can still be corrected.

## Consequences

- A source author who needs Codex pre-approval must edit `~/.codex/config.toml` separately; the artifact cannot grant it. This is called out in the adapter's module docstring.
- Authors who care about declared tool dependencies on Codex (UI hint, not permission) use `adapters.codex.files["agents/openai.yaml"]` with a `dependencies.tools` block; the adapter deep-merges it with the regime-derived `policy`.
- Extending the regime vocabulary in future (e.g. `model-invoked-only`, `path-scoped`) requires touching both adapters in the same change. This is intentional — regimes are the cross-agent contract.
- The Codex adapter's refusal of `allowed-tools` passthrough is asymmetric: Claude accepts the same key. This asymmetry is documented in [adapter-passthrough-source-schema](adapter-passthrough-source-schema.md).
