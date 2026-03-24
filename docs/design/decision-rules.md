# Decision rules

> [!INFO] Part of the [agent instruction system](../design/motivations-problem-statement.md)

> [!TIP] Single source of truth
> This section specifies the contents of the `governance/rules/` directory, which is the **authoritative definition** of each decision rule in the implemented system — one file per rule, with an `_index.md` as the cross-referencing hub. Other locations (contract templates, audit checklists) **instantiate** or **verify** these rules but must not redefine them. When a rule is updated, update the corresponding file in `governance/rules/`; all downstream instantiations reference it via anchors.

## Overview

**Priority stratification**: The rule system is organized by the aspect of note production each rule governs. The same rule may have different enforcement weight depending on the note type and workflow stage.

| Layer             | Governs                                                                                                                                                                                                                                 | Priority | Enforcement                                                                        |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ---------------------------------------------------------------------------------- |
| **Epistemic**     | *What is claimed* (contents, inference validity, strength and relevance of the arguments, what must be proven, which content may enter, why new objects are introduced, which proof route is allowed, which premises are legitimate...) | Highest  | Broad generation-time criteria held in working memory during planning and drafting |
| **Argumentative** | *How the claim is articulated* (exposition structure, functional role separation, sequencing for cognitive processing, transitions...)                                                                                                  | Medium   | Narrower operators enforced at planning time and audit                             |
| **Stylistic**     | *How the result is expressed* (prose register, paragraph construction, notation formatting, terminological coherence...)                                                                                                                | Lowest   | Writing principles and lints at draft time                                         |

**Rule structure.** Each decision rule specifies simultaneously:

- a **normative constraint**: the quality criterion it enforces,
- the **checks** by which any workflow stage may verify compliance.

==TODO: Determine what a decision rule file must specify to be actionable for AI agents across distinct workflow stages.==

> [!NOTE]
> Post-hoc routing protocols are external to the rule system and belong to [procedural workflows](../design/procedural-workflows.md) (e.g. divergence resolution, contract amendment).
