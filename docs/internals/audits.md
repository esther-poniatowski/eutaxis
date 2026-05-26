# Audits

> [!INFO] Part of the [agent instruction system](motivations-problem-statement.md)

## Overview

**Directory**: `governance/audits/`

Audits are **post-draft verification**, separated from rules and specifications because they operate after the drafting pass rather than during generation. The audit pass receives the draft note, the integration record, and the pre-draft specification as its baseline, and produces a separate audit report.

The directory contains two files:

- `governance/audits/checklists.md` — eight audit dimensions with binary questions
- `governance/audits/report_template.md` — fill-in template for audit reports

## Audit checklists

`governance/audits/checklists.md` contains eight audit dimensions, each with a checklist of binary questions. The sections correspond one-to-one to the audit report sections. Each dimension verifies one or more decision rules by cross-referencing the corresponding file in `governance/rules/`.

Each dimension verifies one or more project-declared decision rules. The wording below lists the generic audit questions. Specific verification targets are project-declared and recorded in `governance/rules/`.

- **Contract compliance audit.** Verifies that the contracted question was answered exactly, the minimal target output was delivered, and the termination criterion was respected.
- **Coherence audit.** Verifies that the note's content holds together as a single argument toward the contracted question. Questions: Does the note answer exactly one contracted question? Does each major section contribute directly? Could any section be removed without loss? Does each section use a specific output from a preceding section? Does each section's output-consumer pair remain on the main result path? Does the skeleton declare and use an admissible decomposition pattern?
- **Redundancy audit.** Verifies that the note does not repeat material established elsewhere. Questions: Does the note rederive prior outputs? Does it restate background that should be linked? Does it duplicate interpretation written elsewhere?
- **Argumentative audit.** Verifies the separation between claim, development, and interpretation. Questions: Do result statements perform development work? Do development paragraphs carry interpretation beyond what the next move requires? Do interpretation paragraphs merely restate the claim? Are unit-role tags present in the annotated development and preserved correctly in the draft?
- **Motivation audit.** Verifies that constructs are introduced through genuine obstacles, rather than rhetorical ones. Questions: Are major constructs introduced through a stated obstacle? Does each major construct cite the exact later step it enables? Are there rhetorical rather than functional motivations? Does any interpretive passage fail the project's interpretive admissibility criterion?
- **Terminology audit.** Enforced by `tools/lint_terminology.py` against `registry/terminology.yaml`. Questions: Does any prose use a forbidden variant? Does any newly introduced term lack a registry entry?
- **Integration audit.** Questions: Are dependencies correctly cited? Is the output directly usable by downstream notes? Has the registry been updated?

Domain-specific audits — verifying domain rules such as proof strategies, evidential standards, or empirical adequacy — are added by the project deploying eutaxis as additional dimensions in `governance/audits/checklists.md`.

## Audit report template

`governance/audits/report_template.md` is the fill-in template for audit reports. The audit must exist as a separate artifact, rather than as a paragraph appended to the note. The report opens with a Metadata block (note audited, contract checked) followed by numbered sections corresponding one-to-one to the checklist dimensions above, plus any project-declared additional dimensions, plus a final **Required revisions** section. Each finding cites the specific checklist question that was violated. The Required revisions section collects all required revisions with severity and recommended action.

## Audit enforcement by note type

The audit pass must verify that the note's declared type matches its actual content. If a note contains sections that match a forbidden pattern for its declared type (per the project-declared note specifications in `governance/specs/`), the audit must flag the violation and recommend one of:

- excise the offending section
- defer it to a new note of the appropriate type
- reclassify the note if the content is legitimate but the type declaration is wrong
