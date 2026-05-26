# Agent Skills as the command target surface

## Status

Accepted. Specialises [convergence-on-agent-skills-standard](convergence-on-agent-skills-standard.md) for the commands subsystem.

## Context

The commands subsystem renders a single source declaration into a native, user-invocable artifact on each supported agent. Both Claude Code and Codex offer more than one candidate surface, and the choice determines the artifact shape (single file vs. directory), the permission model, and the invocation syntax users learn.

Claude Code documents skills as the recommended form for *task* skills with side effects whose timing must be controlled, citing `/commit` and `/deploy` as canonical examples (`claude/skills.md:55`). Codex documents custom prompts as **deprecated** and explicitly superseded by skills, with the note that custom prompts live in `~/.codex/prompts/` and "are not shared through the repository" (`codex/comparison-mechanisms.md:27-29`). The Agent Skills specification is the convergent open standard for both agents.

The initial implementation chose Claude `.claude/commands/<name>.md` and Codex `~/.codex/prompts/<name>.md`. That surface has three concrete problems on Codex: (a) the path is deprecated; (b) Codex never reads `<project>/.codex/prompts/`, so the project scope writes a file the agent ignores; (c) the legacy form has no `allowed-tools` slot, forcing per-call Bash approval for every `clean-memory` invocation. On Claude the legacy form also lacks a permission slot.

## Decision

Compile every command source into an Agent Skill **directory** on both agents.

| Adapter | User scope | Project scope |
| --- | --- | --- |
| Claude | `~/.claude/skills/<name>/SKILL.md` | `<project>/.claude/skills/<name>/SKILL.md` |
| Codex | `$HOME/.agents/skills/<name>/SKILL.md` | `<project>/.agents/skills/<name>/SKILL.md` |

The source `name` becomes both the directory name and the `name` field in `SKILL.md`. Codex requires these to match (`skills-comparison.md:67`); Claude treats the directory name as the default. Invocation symbols follow each agent's convention: `/<name>` on Claude, `$<name>` on Codex (`skills-comparison.md:171`).

## Discarded alternatives

- **Claude `.claude/commands/<name>.md` and Codex `~/.codex/prompts/<name>.md`** (the original implementation). Rejected because Codex documents the path as deprecated, the project-scope variant does not exist on Codex, and neither legacy form exposes a permission-grant slot for the shell command the skill needs to run.
- **Dual-emit: skill plus legacy file on each agent.** Rejected because the legacy form has no permission slot in any case, so dual-emit clutters two surfaces without fixing the underlying problem and doubles the install and uninstall surface for no benefit.
- **Skill on Claude, legacy custom prompt on Codex.** Rejected because the asymmetry is precisely what Codex documentation discourages, and the long-term direction P6 of the cross-agent compiler proposal already anticipated skills on both.

## Rationale

A single, modern surface aligns the subsystem with both vendors' recommended path and removes the per-call Bash approval friction that defined the original review's Defect 2. The cost is the multi-file artifact model, which propagates through the adapter Protocol but is paid once.

## Consequences

- The `AgentAdapter` Protocol returns a multi-file artifact rather than `(Path, str)`; see [multi-file-artifact-model](multi-file-artifact-model.md).
- The Codex invocation symbol changes from `/prompts:<name>` to `$<name>`.
- The `CommandSource.scope_default` semantics carry over unchanged; both scopes are supported on both adapters, so Defect 1 from the review (Codex project-scope writes a file Codex never reads) dissolves.
- Pre-approval on Codex still lives in `~/.codex/config.toml` outside the artifact; see [regime-and-permission-mapping](regime-and-permission-mapping.md).
