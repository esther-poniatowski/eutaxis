---
name: clean-memory
description: Delete this agent's memory files for the current project. Run only when the user types the slash/skill invocation explicitly.
regime: user-invoked
failure-mode: silent
required-visibility: pre-action
scope_default: user
argument-hint: "[--all] [--backup] [--dry-run]"
action:
  kind: shell
  template: "eutaxis ops clean-memory --agent {{ agent }} --project {{ project_root }} --yes"
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
---

# Clean memory

Run the following to wipe my memory files for this project, then confirm the directory is empty:

```bash
{{ action.template }}
```

If the user asked to wipe **all** projects (not just the current one), append `--all` to the command above. If the user asked to keep a backup, append `--backup`.

If the user asked for a **preview** or **dry run**, replace `--yes` with `--dry-run` — this lists the files that would be removed without touching the filesystem.

After the operation completes, list the paths that were removed (or, in dry-run mode, the paths that would be removed).
