# AI prompts - section demarcation

Use unambiguous delimiters to demarcate content regions.

**Preferred option**: XML-style tags (e.g. `<role>`, `<constraints>`, `<output_format>`) are often effective, especially for nested structure:

- Tags are parsed as **structural** delimiters and are interpreted by the model through its training on structured data formats.
- Tags activate **schema-like processing** in addition to semantic priming. For this reason, XML-tagged rule blocks with carefully chosen tag names produce more consistent compliance.
- Tags can be **referenced** in later instructions (e.g. "as specified in `<constraints>`").

**Alternative**: Markdown headings can also serve as delimiters, especially when combined with explicit instructions and examples, but they carry weaker structural signal than XML tags for nested or machine-parsed content.

**Avoid**: Natural language labels are the weakest option — they are parsed as _descriptive_ annotations rather than structural boundaries (e.g. "Constraints:", etc).

A **rule block** per constraint dominates in practice, instead of a flat list of bullets:

```xml
<rule id="R1">
  <statement>
    Subjective informal pronouns are forbidden. Replace with syntactically
    complete neutral constructions that preserve propositional content.
  </statement>
  <invalid>
    "You can see that the gradient vanishes in the limit."
    "We define the kernel as follows."
    "I will now state the main theorem."
  </invalid>
  <valid>
    "The gradient vanishes in the limit."
    "The kernel is defined as follows."
    "The main theorem is stated below."
  </valid>
  <note>
    Deletion of the pronoun is insufficient when the resulting sentence
    loses a logical subject. Restructure; do not merely delete.
  </note>
</rule>
```

The `<note>` field is critical and systematically underused: it encodes **the non-obvious implication** of the rule — the part that a naive reading of the statement would miss. This is where most instruction failures originate.
