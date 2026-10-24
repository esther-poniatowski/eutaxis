---
tags: []
aliases:
  - "Links between modules in compiled Skills"
index: "[Architecture decisions](_index.md)"
---

# Links between modules in compiled Skills

## Status

Accepted.

## Context

A source module links to its sibling modules and to other files by relative Markdown links, such as `[the prose authoring workflow](prose-authoring-workflow.md)` or `[verification](../global/verification.md)`. These links resolve against the directory of the source. The compiler installs each task module as its own Skill directory. That directory holds only the files of one compiled Skill. In a split Skill, each rule file sits one directory below `SKILL.md`. Consequently, a relative link copied verbatim resolves to no file, whether the Skill is inline or split.

The targets of these links fall into three kinds:

- a sibling module compiled as a Skill from the same configuration;
- a file that is not a Skill, such as an always-on module;
- an illustrative target that names no file, such as `proof.md` in an example of link text.

## Decision

The renderer rewrites the target of each relative link in `SKILL.md` and in each rule file. The module `eutaxis.commands.links` holds the rewrite.

1. **Sibling Skill.** When a target resolves to the source of another Skill compiled from the same configuration, the target becomes the relative path to the `SKILL.md` of that Skill. The path starts from the emitting file: `../<name>/SKILL.md` from `SKILL.md`, and `../../<name>/SKILL.md` from `rules/<label>.md`. When the adapter does not receive the sibling Skill, the target becomes the absolute path of its source, as in item 2.
2. **Existing file.** When the target names no sibling Skill and exists on disk, the target becomes its absolute path. An always-on module is not a Skill, so a link to it takes this form.
3. **Missing target.** When no file exists at the target, the target keeps its text. The commands `skills show`, `skills install` and `skills diff` report it on standard error, with the source file and the line of the link.

A rewritten target keeps its fragment, such as `#^anchor`. Five kinds of link keep their text:

- an absolute URL or any other target with a scheme, `mailto:` included;
- an absolute path;
- a pure fragment;
- a link to a file of the artifact itself, such as the link from an index entry to `rules/<label>.md`;
- a link inside a code span or a fenced code block.

## Discarded alternatives

- **Copying each linked file into the artifact.** Rejected because a module linked from several Skills would exist in several copies, each covered by the ownership marker of its own artifact. An edit of the source would also leave every copy outdated until the next install.
- **The absolute source path for every target, sibling Skills included.** Rejected because the agent would read the source module, frontmatter included, whereas the installed Skill holds the text compiled for that agent.
- **A relative path from the installed Skill to the source tree.** Rejected because that path depends on the install scope and on the directory of the configuration repository, whereas an absolute path depends only on the directory of the source.

## Rationale

Every Skill of one adapter and one scope is installed under one parent directory. Therefore, a relative link to a sibling Skill stays valid wherever that directory lies. Every other existing target is reachable only through the source tree, and its absolute path does not depend on the install directory. The rewrite reads only the sources and the files present on disk. Consequently, two renders produce the same bytes as long as the sources and the files on disk are unchanged. Therefore, the command `skills diff` reports no drift right after an install.

## Consequences

- A link from a sibling module to an anchored rule of another Skill, such as `prose-authoring-workflow.md#^anchor`, points to the `SKILL.md` of that Skill. Therefore, the fragment resolves only when that Skill is inline: in a split Skill, the anchored line sits in a rule file.
- A deployed Skill holds absolute paths into the source tree. When a machine holds the source tree at another path, the render on that machine holds other targets, and `skills diff` reports them as drift.
- An illustrative link written outside a code span is read as a link. The compiler reports its target as missing, and the report disappears once the example sits in a code span.
