<a id="rule-query"></a>

# Rule Query

Rule query: collect the rule records of configured modules or deployed skills, and resolve a label to one rule and a part name to its parts.

<a id="module-eutaxis.rule_query.catalog"></a>

<a id="catalog"></a>

## Catalog

Rule catalog and the resolution of one rule query.

A [`RuleCatalog`](#eutaxis.rule_query.catalog.RuleCatalog) holds the rule records collected from a set of
modules, each located at the file that holds it. The functions of this
module resolve a label to one rule and a part name to the matching parts,
and raise an error naming the available choices when the query does not
resolve. They perform no I/O.

<a id="eutaxis.rule_query.catalog.LocatedRule"></a>

### *class* eutaxis.rule_query.catalog.LocatedRule(rule, path)

Bases: `object`

A rule record and the file whose line numbers it carries.

* **Parameters:**
  * **rule** ([*Rule*](instructions.md#eutaxis.instructions.rules.Rule))
  * **path** (*Path*)

<a id="eutaxis.rule_query.catalog.LocatedRule.rule"></a>

#### rule *: [Rule](instructions.md#eutaxis.instructions.rules.Rule)*

<a id="eutaxis.rule_query.catalog.LocatedRule.path"></a>

#### path *: Path*

<a id="eutaxis.rule_query.catalog.LocatedRejection"></a>

### *class* eutaxis.rule_query.catalog.LocatedRejection(rejection, path)

Bases: `object`

A rejected label line and the file that holds it.

* **Parameters:**
  * **rejection** ([*RejectedLabel*](instructions.md#eutaxis.instructions.rules.RejectedLabel))
  * **path** (*Path*)

<a id="eutaxis.rule_query.catalog.LocatedRejection.rejection"></a>

#### rejection *: [RejectedLabel](instructions.md#eutaxis.instructions.rules.RejectedLabel)*

<a id="eutaxis.rule_query.catalog.LocatedRejection.path"></a>

#### path *: Path*

<a id="eutaxis.rule_query.catalog.RuleCatalog"></a>

### *class* eutaxis.rule_query.catalog.RuleCatalog(origin, rules, rejected=(), hint='')

Bases: `object`

Rules collected from one source of modules.

* **Parameters:**
  * **origin** (*str*)
  * **rules** (*tuple* *[*[*LocatedRule*](#eutaxis.rule_query.catalog.LocatedRule) *,*  *...* *]*)
  * **rejected** (*tuple* *[*[*LocatedRejection*](#eutaxis.rule_query.catalog.LocatedRejection) *,*  *...* *]*)
  * **hint** (*str*)

<a id="eutaxis.rule_query.catalog.RuleCatalog.origin"></a>

#### origin *: str*

Description of the source, quoted in error messages.

<a id="eutaxis.rule_query.catalog.RuleCatalog.rules"></a>

#### rules *: tuple[[LocatedRule](#eutaxis.rule_query.catalog.LocatedRule), ...]*

Rules in module order, then source order.

<a id="eutaxis.rule_query.catalog.RuleCatalog.rejected"></a>

#### rejected *: tuple[[LocatedRejection](#eutaxis.rule_query.catalog.LocatedRejection), ...]* *= ()*

Label-shaped lines that the parser rejected.

<a id="eutaxis.rule_query.catalog.RuleCatalog.hint"></a>

#### hint *: str* *= ''*

Advice appended to the message of an unknown label, such as the reason
why a label may be absent from this source.

<a id="eutaxis.rule_query.catalog.RuleCatalog.select"></a>

#### select(module=None)

Return the rules of `module`, or every rule when it is `None`.

* **Parameters:**
  **module** (*str* *|* *None*)
* **Return type:**
  tuple[[*LocatedRule*](#eutaxis.rule_query.catalog.LocatedRule), …]

<a id="eutaxis.rule_query.catalog.RuleCatalog.modules"></a>

#### *property* modules *: tuple[str, ...]*

Names of the modules that hold at least one rule, in order.

<a id="eutaxis.rule_query.catalog.resolve_rule"></a>

### eutaxis.rule_query.catalog.resolve_rule(catalog, label, \*, module=None)

Return the one rule labelled `label`.

* **Parameters:**
  * **catalog** ([*RuleCatalog*](#eutaxis.rule_query.catalog.RuleCatalog)) – Rules to search.
  * **label** (*str*) – Requested label.
  * **module** (*str* *,* *optional*) – Module that must hold the rule; required when several modules
    define the label.
* **Raises:**
  * [**UnknownRuleError**](#eutaxis.rule_query.exceptions.UnknownRuleError) – When no rule carries the label. The message lists close labels,
        a rejected label line with the same token, and the hint of the
        catalog.
  * [**AmbiguousRuleError**](#eutaxis.rule_query.exceptions.AmbiguousRuleError) – When several modules define the label and `module` is `None`.
* **Return type:**
  [*LocatedRule*](#eutaxis.rule_query.catalog.LocatedRule)

<a id="eutaxis.rule_query.catalog.select_parts"></a>

### eutaxis.rule_query.catalog.select_parts(rule, part)

Return the parts of `rule` whose key equals `part`.

* **Raises:**
  [**UnknownPartError**](#eutaxis.rule_query.exceptions.UnknownPartError) – When the rule has no such part; the message lists the parts the rule
      has.
* **Parameters:**
  * **rule** ([*Rule*](instructions.md#eutaxis.instructions.rules.Rule))
  * **part** (*str*)
* **Return type:**
  tuple[[*RulePart*](instructions.md#eutaxis.instructions.rules.RulePart), …]

### Examples

```pycon
>>> from eutaxis.instructions.rules import parse_module
>>> rule = parse_module("**r**:\n\n✓ Do.\n", module="m").rules[0]
>>> [p.text for p in select_parts(rule, "valid")]
['✓ Do.']
```

<a id="module-eutaxis.rule_query.sources"></a>

<a id="sources"></a>

## Sources

Build rule catalogs from configured modules or from deployed skills.

The query reads two source families:

- an instruction-assembly configuration, whose `common_sources`, agent
  `sources` and `task_modules` name Markdown or structured declaration
  modules. For Markdown, line numbers refer to the authored files. For a
  structured record, the displayed synthetic location names the authenticated
  cumulative artifact and its line range. When a Markdown source limits its
  scope, only the admitted rules and rejected lines enter the catalog;
- a skills directory, such as the user-scope directory of an adapter, whose
  eutaxis-owned skills are read as deployed. A skill compiled with
  `disclosure: progressive` is read through its index: each indexed rule
  is parsed from its `rules/<label>.md` file and takes the heading path of
  its index entry.

This module holds the file-system reads; parsing is delegated to
[`eutaxis.instructions.rules`](instructions.md#module-eutaxis.instructions.rules).

<a id="eutaxis.rule_query.sources.catalog_from_config"></a>

### eutaxis.rule_query.sources.catalog_from_config(config_path, root=None)

Collect the rules of every module that a configuration declares.

A module declared by several entries contributes the union of their
selections. An entry without `sections` or `exclude_sections`, and
every `task_modules` entry, selects the whole module.

* **Parameters:**
  * **config_path** (*Path*) – Instruction-assembly configuration.
  * **root** (*Path* *,* *optional*) – Folder against which the paths of the configuration resolve.
    Default: the root implied by the place of the file.
* **Raises:**
  [**RuleSourceError**](#eutaxis.rule_query.exceptions.RuleSourceError) – When a declared module is missing on disk.
* **Return type:**
  [*RuleCatalog*](#eutaxis.rule_query.catalog.RuleCatalog)

<a id="eutaxis.rule_query.sources.catalog_from_skills_dir"></a>

### eutaxis.rule_query.sources.catalog_from_skills_dir(skills_dir)

Collect the rules of every eutaxis-owned skill under `skills_dir`.

* **Parameters:**
  **skills_dir** (*Path*) – Directory holding one sub-directory per skill.
* **Raises:**
  [**RuleSourceError**](#eutaxis.rule_query.exceptions.RuleSourceError) – When the directory is missing, or when an index entry of a split
      skill points to a missing or mismatched rule file.
* **Return type:**
  [*RuleCatalog*](#eutaxis.rule_query.catalog.RuleCatalog)

<a id="module-eutaxis.rule_query.exceptions"></a>

<a id="exceptions"></a>

## Exceptions

Exceptions for the rule query.

<a id="eutaxis.rule_query.exceptions.RuleQueryError"></a>

### *exception* eutaxis.rule_query.exceptions.RuleQueryError

Bases: `Exception`

Base exception for rule queries; every one is a usage error (exit status 2).

<a id="eutaxis.rule_query.exceptions.RuleQueryError.exit_code"></a>

#### exit_code *= 2*

<a id="eutaxis.rule_query.exceptions.RuleSourceError"></a>

### *exception* eutaxis.rule_query.exceptions.RuleSourceError

Bases: [`RuleQueryError`](#eutaxis.rule_query.exceptions.RuleQueryError)

Raised when the modules or skills to query cannot be read.

<a id="eutaxis.rule_query.exceptions.UnknownRuleError"></a>

### *exception* eutaxis.rule_query.exceptions.UnknownRuleError

Bases: [`RuleQueryError`](#eutaxis.rule_query.exceptions.RuleQueryError)

Raised when no queried module defines the requested label.

<a id="eutaxis.rule_query.exceptions.AmbiguousRuleError"></a>

### *exception* eutaxis.rule_query.exceptions.AmbiguousRuleError

Bases: [`RuleQueryError`](#eutaxis.rule_query.exceptions.RuleQueryError)

Raised when several queried modules define the requested label.

<a id="eutaxis.rule_query.exceptions.UnknownPartError"></a>

### *exception* eutaxis.rule_query.exceptions.UnknownPartError

Bases: [`RuleQueryError`](#eutaxis.rule_query.exceptions.RuleQueryError)

Raised when the requested rule lacks the requested part.
