---
tags: []
aliases:
  - Agent Skills as the command target surface
index: "[Architecture decisions](_index.md)"
---

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

### Bounded loading routes

A native Skill selects a workflow. A loading route selects the bounded files required by that workflow. Eutaxis keeps these choices separate. Publishing a loading unit generates a manifest inside the workflow Skill. Eutaxis also adds a route index to the owner entrypoint. Each route manifest records:

- its ordered batches;
- its deduplicated installed files;
- its size;
- its closure digest.

Only the graph of loading units determines the files in a route. Therefore, Eutaxis hashes the generated manifests together with their owner Skill. The drift command checks them, and the sync command manages them. A loading route remains a support file because agents cannot invoke it independently. Each task retains one picker entry. The native Skill picker continues to list the tasks available to the user.

## Discarded alternatives

- **Claude `.claude/commands/<name>.md` and Codex `~/.codex/prompts/<name>.md`** (the original implementation). Rejected because Codex documents the path as deprecated, the project-scope variant does not exist on Codex, and neither legacy form exposes a permission-grant slot for the shell command the skill needs to run.
- **Dual-emit: skill plus legacy file on each agent.** Rejected because the legacy form has no permission slot in any case, so dual-emit clutters two surfaces without fixing the underlying problem and doubles the install and uninstall surface for no benefit.
- **Skill on Claude, legacy custom prompt on Codex.** Rejected because the asymmetry is precisely what Codex documentation discourages, and the long-term direction P6 of the cross-agent compiler proposal already anticipated skills on both.
- **One native Skill per loading route.** Rejected because route Skills would duplicate the workflow's picker entry and require metadata for an independently callable route. The loading-unit model owns no such metadata. A native agent would still load only the route entrypoint, so the additional Skill would not load its referenced files automatically.
- **Handwritten route manifests.** Rejected because they would duplicate the configured loading-unit graph and could drift from the closure measured by the budget command.

## Rationale

Agent Skills give both vendors one modern target. The Skills route no longer asks the user to approve each Bash call. This change resolves Defect 2 in the original review. In exchange, the adapter Protocol must support multi-file artifacts.

## Consequences

- The `AgentAdapter` Protocol returns a multi-file artifact rather than `(Path, str)`; see [multi-file-artifact-model](multi-file-artifact-model.md).
- The Codex invocation symbol changes from `/prompts:<name>` to `$<name>`.
- The `CommandSource.scope_default` semantics carry over unchanged; both scopes are supported on both adapters, so Defect 1 from the review (Codex project-scope writes a file Codex never reads) dissolves.
- Pre-approval on Codex still lives in `~/.codex/config.toml` outside the artifact; see [regime-and-permission-mapping](regime-and-permission-mapping.md).
- Published loading routes are support files of their owner Skill. Published route files add no Skill-picker entry and must resolve every selected file within the same adapter and deployment scope.
