---
tags: []
aliases:
  - Prompt-level component activation
index: "[Architecture decisions](_index.md)"
---

# Prompt-level component activation

## Status

**Superseded** by [compiler-not-runtime-activation](compiler-not-runtime-activation.md).

This ADR documented an earlier direction in which Eutaxis exposed a runtime prompt directive (`@eutaxis rule:... role:...`) interpreted by per-agent adapters. An adversarial audit found the runtime directive unsound (portable as a string but not as behaviour, sigil collision with file-reference preprocessing in both target clients, runtime context injection at odds with golden-file review).

The replacement direction is a build-time compiler; see the new ADR above and the framework set it links to. The content below is retained for historical context and is **not** a description of current behaviour.

---

## Original status (retained)

Accepted (prior decision; now superseded).

## Context

Eutaxis assembles modular instruction files from reusable Markdown sources. The initial use case is generated global and project-level agent instructions, but the same architecture is expected to support modular rules, roles, output styles, tool directives, and other typed components.

Generated instruction files can tell an agent when to load a module, but this remains an interpretive contract. The agent may miss the trigger, load the wrong module, or ignore the rule when the user asks for a task that requires it.

A more user-friendly and robust interaction pattern is explicit prompt-level activation. The user should be able to request components directly in the prompt without editing configuration files or running a terminal command before every task.

Slash syntax is attractive because it resembles native agent commands:

```text
/eutaxis: prose-writing git-workflows
```

or:

```text
/eutaxis-rule: prose-writing
/eutaxis-role: reviewer
```

However, slash commands are not agent-neutral. Some clients intercept slash commands before the prompt reaches the model. The available extension points and the exact command syntax differ by agent.

Claude Code supports personal, project, and plugin skills that are invoked as slash commands. It also supports hooks such as `UserPromptSubmit` and `UserPromptExpansion`, which can inject additional context into the model request before the agent responds.

Codex also has slash commands processed before the model sees the prompt, but its cross-project extension surface is centered on skills, global instructions, and command-line workflows rather than arbitrary Eutaxis-defined slash commands.

## Decision

Eutaxis will separate the portable activation language from agent-specific command adapters.

The canonical internal identifier format is typed:

```text
rule:prose-writing
rule:git-workflows
role:reviewer
style:concise
tool:browser
```

The recommended portable prompt directive is not a slash command:

```text
@eutaxis rule:prose-writing rule:git-workflows role:reviewer
```

For structured prompts, the equivalent block form is:

```yaml
eutaxis:
  rules:
    - prose-writing
    - git-workflows
  role: reviewer
  style: concise
```

Eutaxis will maintain a component registry that maps stable IDs to source files, descriptions, aliases, dependencies, conflicts, and supported agent adapters.

The registry should support entries shaped like:

```yaml
components:
  - id: rule:prose-writing
    kind: rule
    source: instructions/tasks/prose-writing.md
    description: Prose-writing conventions.
    aliases:
      - prose
      - writing
    requires: []
    conflicts: []
```

Agent adapters may expose native command surfaces when available:

- Claude Code may use generated skills, plugin commands, MCP prompts, or hooks that resolve Eutaxis component IDs and inject the resolved context.
- Codex may use generated skills, generated global instructions, and optional wrapper commands that expand Eutaxis directives before launching or continuing a session.

Eutaxis should provide a user-level resolver command for environments that can run local utilities:

```sh
eutaxis resolve rule:prose-writing role:reviewer
```

Project repositories should not need to install or know about Eutaxis unless they author their own modular instruction system. A user-level installation or tool shim is appropriate when runtime resolution is needed across projects.

## Rationale

The typed ID format keeps the registry extensible. It avoids overloading `rule-id` once Eutaxis supports roles, output styles, tool policies, and other component kinds.

The `@eutaxis` directive is portable because it can pass through any agent as ordinary prompt text. It can be interpreted by generated instructions, a wrapper, an MCP prompt, a hook, or a future native integration.

Slash commands remain useful, but only as adapters. Treating slash syntax as the canonical language would make Eutaxis depend on the command parser of each client.

The resolver command gives Eutaxis a deterministic mechanism for assembling the requested context. Agent-specific integrations can call this resolver instead of duplicating registry logic.

## Consequences

Eutaxis needs a registry model for typed components before robust prompt-level activation can be implemented.

Generated instruction files should mention the portable directive only as a fallback behavior. Robust clients should use native adapters or wrappers that inject the resolved context before the model answers.

Claude Code can receive a relatively strong implementation through skills, plugins, MCP prompts, and prompt hooks.

Codex support should begin with generated skills and global instructions, with a CLI wrapper as the more deterministic path when prompt pre-processing is needed.

The same registry can later drive documentation, validation, dependency checks, and conflict detection for rules, roles, styles, and tool directives.

## Open questions

The exact registry schema still needs to be designed.

The resolver output format should be specified. It may need plain Markdown, agent-specific Markdown, structured JSON, or all three.

Codex skill invocation and custom command support should be rechecked against the current official Codex documentation before implementation, because this surface is still evolving.

Claude Code hook integration should be designed as an optional adapter, not as a mandatory dependency for all users.
