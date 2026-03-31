# Usage

Eutaxis composes, renders, and validates structured agent prompts. Domain rules
stay in the projects that own them; eutaxis provides the composition workflow,
reusable templates, and quality enforcement.

## Composing a Prompt

The `generate` command assembles a prompt from a composition specification:

```sh
eutaxis generate -c agent-instructions.yaml
```

The composition file references a top-level shell, local fragments, and
parameterized bundles. The shell determines the final ordering and bridging
text, while bundles inject shared methodology structure with domain-specific
content through template variables.

## Validating a Prompt

The `validate` command enforces family profile requirements — required files,
required tags, and length warnings:

```sh
eutaxis validate prompts/ --family audit
```

Family profiles distinguish hard assembly requirements from advisory guidance.
A profile violation produces a non-zero exit code, suitable for CI integration.

## Reviewing Composed Output

The `render` command produces golden-file output for diff-based review:

```sh
eutaxis render -c agent-instructions.yaml --output rendered/
```

Golden files make prompt changes visible in version control diffs, enabling
iterative refinement and behavioral testing.

## Scaffolding a Prompt Workspace

The `init` command creates the prompt-composition structure in a target
project:

```sh
eutaxis init --target ../my-project/prompts
```

The generated structure includes directories for shells, fragments, bundles,
and rendered output.

## Prompt Families

Prompts group into families that share authoring workflows, methodology
patterns, output contracts, and testing strategies. Each family has a profile
that defines its structural requirements.

## Next Steps

- [Prompt-Writing Methodology](../../prompt-writing-methods.md) — Foundational
  reference for agent instruction design.
