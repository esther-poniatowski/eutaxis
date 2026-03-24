# Audits

> [!INFO] Part of the [agent instruction system](motivations-problem-statement.md)

## Overview

**Directory**: `governance/audits/`

Audits are **post-draft verification**, separated from rules and specifications because they operate after the drafting pass rather than during generation. The audit pass receives the draft note, the integration record, and the pre-draft specification as its baseline, and produces a separate audit report as its output artifact.

The directory contains two files:

- `governance/audits/checklists.md` — eight audit dimensions with binary questions
- `governance/audits/report_template.md` — fill-in template for audit reports

## Audit checklists

`governance/audits/checklists.md` contains eight audit dimensions, each with a checklist of binary questions. The sections correspond one-to-one to the audit report sections. Each dimension verifies one or more decision rules by cross-referencing the corresponding file in `governance/rules/`.

- **Contract compliance audit.** Verifies that the atomic question was answered exactly, the minimal target result was delivered, and the termination criterion was respected.
- **Coherence audit.** Verifies the [local necessity rule](decision-rules.md#^admissibility-rule), the [retention audit operator](decision-rules.md#^drift-detection), and [deductive continuity](decision-rules.md#^deductive-articulation). Questions: Does the note answer exactly one atomic question? Does each major section contribute directly? Could any section be removed without loss? Does each section use a specific output from a preceding section? Does each section's output-consumer pair remain on the main result path? Does the skeleton declare and use an admissible decomposition pattern?
- **Mathematical audit.** Verifies [proof strategies](decision-rules.md#^proof-strategies) (including the [explanatory target](decision-rules.md#^explanatory-target)) and [premise legitimacy](decision-rules.md#^premise-legitimacy). Questions: Are assumptions explicit? Is the proof strategy stated before the proof? Is the proof family named appropriately? Does the derivation reveal the committed explanatory target or merely verify the result? Does it build forward from the problem in the family-appropriate way? Is every non-trivial premise proved locally or declared?
- **Redundancy audit.** Verifies [premise legitimacy](decision-rules.md#^premise-legitimacy) (background-restatement test), the [side-result criterion](decision-rules.md#^forbid-free-expansion), and [Test C of the retention audit operator](decision-rules.md#^non-redundancy-test). Questions: Does the note rederive prior results? Restate background that should be linked? Duplicate interpretation written elsewhere?
- **Argumentative audit.** Verifies [claim / derivation / interpretation separation](decision-rules.md#^claim-derivation-interpretation-separation). Questions: Do result statements perform proof work? Do proof paragraphs carry interpretation beyond what the next move requires? Do interpretation paragraphs merely restate the claim? Are unit-role tags present in the annotated derivation and preserved correctly in the draft?
- **Motivation audit.** Verifies the [functional motivation rule](decision-rules.md#^functional-motivation) and the [interpretive sub-criterion](decision-rules.md#^bounded-interpretive-radius). Questions: Are major constructs introduced through genuine obstacles? Does each major construct cite the exact later step it enables? Are there rhetorical rather than functional motivations? Does any interpretive passage fail the four-question admissibility criterion?
- **Terminology audit.** Enforced by `tools/lint_terminology.py` against `registry/terminology.yaml`. Questions: Does any prose use a forbidden variant? Does any newly introduced term lack a registry entry?
- **Integration audit.** Questions: Are dependencies correctly cited? Is the output directly usable by downstream notes? Has the registry been updated?

## Audit report template

`governance/audits/report_template.md` is the fill-in template for audit reports. The audit should exist as a separate artifact, not merely as a paragraph appended to the note. The report opens with a Metadata block (note audited, contract checked) followed by nine numbered sections corresponding one-to-one to the checklists above: (1) Contract compliance, (2) Coherence, (3) Mathematical rigor, (4) Redundancy, (5) Argumentative, (6) Motivation, (7) Terminology, (8) Integration, (9) Required revisions. Sections 1–8 record findings, each citing the specific checklist question that was violated. Section 9 collects all required revisions with severity and recommended action.

## Audit enforcement by note type

The audit pass must verify that the note's declared type matches its actual content. If a note contains sections that match a forbidden pattern for its declared type (see [note types](note-types.md)), the audit must flag the violation and recommend one of:

- excise the offending section
- defer it to a new note of the appropriate type
- reclassify the note if the content is legitimate but the type declaration is wrong
