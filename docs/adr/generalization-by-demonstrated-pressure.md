# Generalisation requires demonstrated maintenance pressure

## Status

Accepted.

## Context

A prompt composition framework that anticipates every future
abstraction tends to ship the wrong abstractions. The eutaxis design
space invites premature generalisation: cross-family bundles, family
registries, source-mapping metadata graphs, prompt-prose checkers
decomposed into a rules engine, universal section taxonomies. Each is
defensible on paper. None has been demanded by the existing
artifacts.

The framework's first consumers (vitruv, hermeneia) ship coherent
prompt families that share methodology bundles internally but do
**not** repeatedly demand cross-family abstractions. The first
abstraction layer is the prompt family; the second layer (cross-family
generalisation) has no empirical pressure yet.

## Decision

Generalisation in eutaxis is **driven by demonstrated maintenance
pressure, not by forecast symmetry**. Abstractions are introduced
when evidence makes them load-bearing, not when they would be elegant
in advance.

The promotion rule is explicit:

- **One prompt needs it** → keep it local. The fragment lives in the
  prompt's own files.
- **All prompts in a family need it and it changes together** →
  promote to a family bundle. This is the methodology-bundle layer.
- **Multiple families need it with stable meaning** → promote to a
  cross-family abstraction. This is Phase 2 work and is gated on
  the existence of at least two maintained families with a real
  shared concern.

The signals that promote a Phase-1 concept early:

1. A standard change requires coordinated updates across more than
   two prompts and the `sources:` list proves insufficient.
2. A bundle's parameterised slots diverge enough that the template
   no longer captures a coherent shared structure.
3. A new family member creates scope-coordination pressure that the
   current profile model cannot express.

Items explicitly deferred until evidence accumulates:

- A first-class task-posture taxonomy.
- A universal section taxonomy across all prompts.
- A domain manifest layer above prompt families.
- A cross-domain enforcement engine for prompt-prose rules.
- A registry of micro-blocks.

These are not rejected on principle. They are deferred because the
current artifacts do not need them; introducing them now would
codify guesses.

## Discarded alternatives

- **Front-load the registry of micro-blocks.** Rejected: the
  observed maintenance pattern is text-that-changes-together at the
  family-bundle level, not at the paragraph level. A micro-registry
  introduces a coordination layer with no payoff.
- **Adopt a universal section taxonomy across all prompts.**
  Rejected because the observed prompts diverge in section structure
  (`role`, `objective`, `scope`, `methodology`, `output`) and
  imposing one taxonomy would force coercion.
- **Anticipate cross-family bundles from day one.** Rejected:
  cross-family reuse pressure has not been observed because there is
  only one maintained family in some domains and two in others. The
  rule is "promote when pressure appears", and the pressure has not
  appeared.
- **Define a domain manifest layer above families.** Rejected on the
  same grounds — no demonstrated cross-domain coordination
  requirement.

## Rationale

Abstraction guided by forecast is the most reliable source of dead
abstractions in a framework's history. Abstraction guided by
demonstrated pressure produces a framework that fits its consumers,
because the consumers wrote the evidence. The rule "one consumer → keep
local; one family → family bundle; multiple families → cross-family"
is mechanically applicable and avoids both extremes.

## Consequences

- Phase 1 ships the framework plus its first consumer; no
  cross-family generalisation is introduced.
- Phase 2 begins when at least two maintained families exist across
  domain-specific projects and a real shared concern appears.
- An abstraction that turns out to fit one family only stays as
  family-local infrastructure. It does not get promoted.
- The rule for moving text is part of the authoring workflow; see
  the documentation in `docs/guide/usage.md` for the practical
  application.
- New family members exercise the existing model first; the model
  is extended only if the new member cannot fit.
