---
tags: []
aliases:
  - "Rule-level access: rule query and progressive disclosure"
index: "[Architecture decisions](_index.md)"
---

# Rule-level access: rule query and progressive disclosure

## Status

Accepted.

## Context

An instruction module states each rule under a label line, `**<label>**:`. The lines below a label hold ✓ and ✗ statements and fields with an italic title, such as `*Why.*` or `*Exception.*`. The skill compiler emits the whole module into one `SKILL.md`. Two limitations follow from that layout:

- When an agent needs one field of one rule, such as the exception clause of the rule named by a linter finding, it must read the whole module. The alternative, a text window of fixed width after the label line, truncates a long rule or overruns into the next rule.
- When an agent loads a skill, it receives every rule of the module, although one task may apply only a few of them.

Both access patterns require the same structural knowledge: the boundaries of each rule block, and the field held by each paragraph. Part of that knowledge already exists: the rule index of the generator defines the label grammar `^\*\*([a-z][a-z0-9-]*)\*\*:\s*$`. That index extracts the labels alone, without the extent of each block.

## Decision

A parser of rule blocks serves two new consumers: the rule query and progressive disclosure.

1. **Rule parser.** The module `eutaxis.instructions.rules` parses the text of one instruction module into rule records. A rule block runs from its label line to the next label line or the next heading. Label lines and headings are recognized only outside fenced code. Each record carries four kinds of content:
   - the label, the module and the heading path;
   - the ✓ and ✗ statements;
   - the fields, keyed by a normalized marker;
   - the raw block, with its line numbers.

   A titled variant or a plural form of a canonical marker takes the key of that marker: `*Why the tiers.*` maps to `why`, and `*Exceptions.*` maps to `exception`. Any other title is keyed by its slug. When a line has the shape of a label line but its token violates the grammar, the parser reports the line as rejected, and the line ends the preceding block. The parser reads and writes no file. The rule index of the generator takes its label grammar from the parser.
2. **Rule query.** The command `eutaxis rule show <label> [--part <key>]` prints one rule or one part of a rule, with its file and line range. The command `eutaxis rule list` prints the label, the module and the first ✓ line of each rule, and it reports rejected lines on standard error. Both commands read one source of modules:
   - the configuration option `-c <config>` selects the modules declared by the configuration, with line numbers in the authored files. A source entry that selects sections contributes only the rules inside those sections;
   - the option `--skills-dir <dir>` selects the eutaxis-owned skills deployed in a directory;
   - without either option, the command reads the user-scope skills directory of the adapter named by `--agent`, `claude` by default.
3. **Progressive disclosure.** A source whose frontmatter declares `disclosure: progressive` compiles to a split skill. Its `SKILL.md` keeps the headings and every line outside a rule block. An index replaces each run of consecutive rule blocks. Each index entry holds the label, the first ✓ line and a relative link to `rules/<label>.md`. The linked file holds the whole rule block. The rule files are sibling files of the artifact. Therefore, the content hash and the ownership sidecar cover them, and so do the commands `skills diff` and `skills install`. The default value `inline` keeps the compiled output byte-identical to the output of a source without the key.

## Discarded alternatives

- **A configuration key for the disclosure mode.** Rejected because the renderer receives only the parsed source, and the `commands` subsystem has no configuration. The source frontmatter supplies every other field shaping a skill artifact, for the same reason.
- **The authored modules as the default source of the query.** Rejected because the path of the configuration differs between machines, whereas the adapter fixes the path of its user-scope skills directory. The query serves an agent during a task, and that agent can run in any working directory.
- **A label grammar that admits a leading digit.** Rejected because the generated rule index uses the same grammar, so widening the grammar changes the generated index. Instead, a label line with a leading digit is reported as rejected, together with its reason. The author must rename the label.

## Rationale

One parser defines the rule block for every consumer. The rule index takes the label grammar from the parser, and the rule query and the split skill take the extent of each block. Therefore, the block printed by `rule show` is the block written to `rules/<label>.md`. The deployed skills serve as the default source of the query because they hold the text given to the agent. The disclosure mode belongs to the module, because the effect of the split depends on the structure of the module. In a module structured by labels, the split replaces the rule blocks by an index. A module structured by sections holds no rule block, so it compiles identically in both modes.

## Consequences

- Without a source option, the query cannot return a rule of an always-on module, since such a module compiles into the cumulative instruction file. The error message names the configuration option `-c <config>`.
- A split `SKILL.md` carries one fixed note before its first index, stating that each linked file holds the whole rule. The module `eutaxis.commands.disclosure` owns the note and the grammar of an index entry. The rule query reads the index entries with that grammar.
- After a rule is deleted from the source, the render no longer produces the file of that rule, although the file stays listed in the sidecar on disk. Consequently, the command `skills diff` reports that file as removed. The command `skills install` compares every rendered file with its copy on disk, so it replaces any file of the artifact edited by hand, a rule file included.
- A rule file sits one directory below `SKILL.md`, so a relative link of a rule block is rewritten for that depth. The target of each rewritten link is fixed by the ADR on [links between modules](cross-module-links-in-skills.md).
