# Adversarial Review — Eutaxis Cross-Agent Configuration Compiler Proposal

*Reviewer: independent architecture reviewer with no involvement in authoring the proposal.*
*Materials examined: [PROPOSAL-cross-agent-compiler.md](PROPOSAL-cross-agent-compiler.md); [README.md](README.md); supporting notes under `techne/tutorials/ai-agents/` (customization-mechanisms.md, claude/output-styles.md, claude/skills.md, codex/profiles.md, codex/skills.md, codex/agents-loading-precedence.md). Web access not exercised; verification rests on the supporting notes.*

---

## 1. Objections, ordered by severity

### O1 — The session-preset regime is mismodeled, not merely approximate

**Problematic assumption.** §5 maps the session-preset regime to a Claude Code output style *and* a Codex `[profiles.<id>]` block carrying `developer_instructions`. The principle P3 holds that the regime drives mechanism selection; the matrix asserts the chosen Codex mechanism is a profile.

**Failure mode.** A Codex profile is not a per-role behavioural module: it bundles `model`, `model_reasoning_effort`, `model_verbosity`, `personality`, `developer_instructions`, `approval_policy`, `sandbox_mode`, and so on. Only one profile is active per session, and selection is governed by the top-level `profile = "<name>"` key in `config.toml` or by `--profile`. Two consequences follow:

1. **Activation is not configurable from a role component.** Eutaxis can install `[profiles.<id>]` blocks but cannot make a Codex session *respect* a particular session-preset for a given task. The user must select it. The compiler delivers a catalogue; the regime's promise — "fixed for the duration of a session" — only holds after a human action that Eutaxis does not perform.
2. **Setting `profile = "<id>"` is destructive.** It is a single top-level key. Writing it on behalf of a role component overwrites the user's active profile. If Eutaxis is to make the regime fire, it must write that key — and §7's claim that capability writes are the only privileged path is then false.

A Claude Code output style suffers a milder version of the same: activation is `outputStyle` in a settings file, also a single value, also session-scoped, also requires writing into shared settings to take effect.

The two mechanisms are also categorically different in semantics — output style is **substitutive** (replaces the software-engineering portion of the system prompt), Codex profile + `developer_instructions` is **additive**. Calling this "approximate" understates the asymmetry: the same Eutaxis role component yields a *replacement* of the base prompt on one agent and an *addition* on the other. Behavioural divergence is structural, not a fidelity-grade nuance.

**Recommended correction.** Either (a) demote session-preset from a first-class regime to a *catalogued artifact* the user must activate (so the compiler emits files but explicitly disclaims activation), or (b) split the regime into two: a Claude-side "role substitution" mechanism (output style) and a Codex-side "configuration preset" mechanism (profile), with the understanding that the source component must declare which it targets. Routing role components to subagents (currently deferred in §11) deserves serious reconsideration, because subagents are the native role-isolation mechanism on both agents and align better with P3 than profile/output-style do.

---

### O2 — Intra-artifact composition, ordering, and conflict are undefined

**Problematic assumption.** P5 ("native precedence, not a parallel engine") is offered as the answer to layering. The mapping matrix shows multiple components compile into the *same* output artifact: many always-on components → one `CLAUDE.md` and one `AGENTS.md`; multiple session-preset components → output styles and profiles that share a single active slot; many on-demand components → many `SKILL.md` files (this is the only case that genuinely escapes the problem).

**Failure mode.** Native precedence rules cover global-vs-project layering. They do **not** answer:

- In what order do two always-on components from the same scope appear inside `CLAUDE.md`? Order matters for instruction priming.
- What happens when two components contradict each other within the same scope? "The platform resolves it" is false: the platform sees one merged file.
- What happens when two session-preset components target the same Codex profile name, or different role components want different `model` settings within one profile?
- How are §10's "router-referenced instruction modules" generated and ordered, given that they cross between always-on (the router text) and on-demand (the module)?

This is not a Section 10 detail; it is the core compilation semantics, and P5 disclaims responsibility without filling the gap.

**Recommended correction.** Add an explicit intra-artifact composition layer between Resolution and Adapter: deterministic ordering keys on components, a documented conflict policy (fail / last-writer / explicit-merge), and a per-mechanism rule for what "one artifact, many components" means. Without this, the compiler is not deterministic in any usable sense.

---

### O3 — Ownership policy is deferred but structurally load-bearing

**Problematic assumption.** §10 Q3 marks ownership policy (whole-file vs managed-region) as an open question. §7 simultaneously claims the policy *protects* non-Eutaxis content.

**Failure mode.** The architecture writes into `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, and project `AGENTS.md` / `CLAUDE.md`. These files almost universally contain hand-authored content (project conventions, personal preferences accumulated over time). The choice of ownership model is not a detail — it determines whether the compiler is *usable at all*:

- Whole-file ownership requires migration: every existing hand-written line must move into a source fragment, or the file must be reserved for Eutaxis. This is a hard onboarding cost the proposal never quantifies.
- Managed-region ownership requires delimiter syntax, robust idempotency, and a story for what happens when the user edits inside the managed region.

§7's security claim — "under whole-file ownership Eutaxis refuses to overwrite a file it does not recognise as its own" — depends on a policy that has not been chosen. The security argument is therefore conditional on an unresolved decision.

**Recommended correction.** Resolve this before Phase 1, not after. Whole-file ownership for *new* generated artifacts and managed-region for the always-on regime (where collision with hand-written content is the dominant case) is a defensible compromise, but the decision cannot be deferred — Phase 1 ships the always-on regime.

---

### O4 — "Exact fidelity" for the on-demand regime is overstated

**Problematic assumption.** §5 grades the on-demand regime as "Exact (Agent Skills open standard; adapter handles path, frontmatter, and invocation-sigil deltas)".

**Failure mode.** The supporting notes document deltas that exceed the "path / frontmatter / sigil" framing:

- **Invocation control surfaces are different shapes.** Claude Code controls implicit invocation through `SKILL.md` frontmatter (`disable-model-invocation`, `user-invocable`) and through a settings field (`skillOverrides`). Codex controls implicit invocation through a *separate file*, `agents/openai.yaml`, which §11 explicitly defers. Eutaxis cannot emit equivalent control on Codex without engaging a deferred surface.
- **Tool-restriction frontmatter (`allowed-tools`) is Claude-only.** A skill that depends on tool gating cannot be expressed identically on Codex.
- **Discovery semantics differ.** Claude's project skills load from `.claude/skills/` from start dir up to repo root *plus* nested dirs on demand; Codex's `.agents/skills/` follows a different walk. Both work, but a component whose intended scope is "subdirectory only" maps differently.
- **Live-reload semantics differ.** Claude reloads skills mid-session; Codex's reload behaviour is not documented as equivalent. This affects iteration-time fidelity, which the matrix does not record.

The behavioural-equivalence claim (the same procedure runs when triggered) is mostly true. The *operational* claim (the skill is invocable and controllable the same way) is not. Grading this as Exact undersells the asymmetry — at minimum it is "Exact body, approximate envelope", and §10 Q4 should be a deliberate decision, not "Exact" by default.

**Recommended correction.** Demote on-demand from a single fidelity grade to two: payload-fidelity (Exact, both agents) and invocation-fidelity (Approximate, until Codex's `agents/openai.yaml` is taken out of §11). Surface this in `eutaxis explain`.

---

### O5 — The capability regime conflates tool wiring with security policy

**Problematic assumption.** §4.4 and §5 fold "tool, MCP server, or permission binding" into a single regime, then grade fidelity as "Exact for MCP server definitions; approximate for permission and command policy."

**Failure mode.** MCP server definitions and permission/command policy are categorically different objects:

- MCP definitions are *declarative tool wiring*. An approximation that points to the same server on both agents is acceptable.
- Permission rules (Claude `Bash(...)` patterns, `allow`/`deny`) and Codex Starlark `rules` are *security boundaries*. "Approximate" here means one agent grants slightly more or slightly less than the other. That is not fidelity degradation — it is a vulnerability if the looser side authorises something the stricter side blocks, and a usability failure if vice versa. The fidelity vocabulary obscures the security stakes.

Further, the proposal allows external rule-owning projects (vitruv, hermeneia) to ship source components. Permitting an external fragment to expand the permission boundary, even with diff-and-review, is a supply-chain surface that the proposal acknowledges in §7 ("integrity hashes") but does not address at the level of *what kinds* of changes are reviewable. A permission widening hidden inside a 200-line `developer_instructions` payload is hard to spot even with diffs.

**Recommended correction.** Split the capability regime into (a) `tool-wiring` (MCP server definitions, on-by-default after opt-in), and (b) `policy` (permission rules, command policy, sandbox/approval). For (b), refuse cross-repo source components by default, refuse "approximate" compilation entirely (fail the build if exact policy parity cannot be represented), and require a separate review gate beyond the unified `eutaxis plan` diff. Codex Starlark rules in particular should remain hand-authored — they are §11-deferred for good reason, and compiling them is not yet justified.

---

### O6 — Deferring subagents while routing roles to session-preset is inconsistent

**Problematic assumption.** §11 defers subagents because the declaration models differ between agents. §5 routes role/session-preset components to output styles and profiles.

**Failure mode.** Subagents are the *native* role-isolation mechanism in both Claude Code and Codex — separate context, separate tool set, separate model. A "role" component, in the sense the prior proposal used (`role:reviewer`, `role:writer`), maps cleanly to a subagent on both platforms. Routing such a component instead to a Codex profile (per O1) is a poor fit. The architecture has chosen to defer the mechanism best aligned with P3 ("activation regime is the classification axis") and to fully model the mechanism that is worst aligned with it.

The justification — that declaration models differ — applies equally to profiles (TOML, single active slot, top-level selection key) and output styles (markdown plus settings activation). The differences are real for subagents but not more severe than for the regime already supported.

**Recommended correction.** Promote subagents from §11 to §10 (open, but in scope) and reconsider the session-preset mapping in light of subagent availability. At minimum, surface the asymmetry: the proposal silently picks the worse-fit native mechanism.

---

### O7 — Drift detection is necessary but not sufficient

**Problematic assumption.** §4.8 reduces verification to "re-execute the pipeline and compare against on-disk artifacts" plus the fidelity report. P7 frames golden-file review as the correctness contract.

**Failure mode.** Golden files verify *what was emitted*, not *what the agent does with it*. The README references "behavioral testing" and "profile-based validation" as project capabilities. The proposal contains no behavioural validation loop, no contract tests against the agents' actual responses, no oracle for "this output style actually makes Claude write differently". For an architecture whose advertised guarantee is "same source, not same behaviour", the absence of behavioural validation means the fidelity grades in §5 are *claimed*, not *measured*.

This is the answer to Q10: artifact-level review is necessary but not sufficient to support a correctness claim across heterogeneous targets.

**Recommended correction.** Either (a) add a behavioural-validation phase (smoke prompts run against each target with the compiled configuration, compared against expected response signatures) and gate Phase-3-style claims on it, or (b) reframe the contract publicly: Eutaxis guarantees deterministic artifact generation, not behavioural equivalence, and the fidelity grades are *advisory*. The current text reads as the latter while occasionally suggesting the former.

---

### O8 — Cross-repository source acquisition is mentioned but unspecified

**Problematic assumption.** §4.2 and §7 mention that components originate in external rule-owning projects and are pinned with integrity hashes in a lockfile.

**Failure mode.** Acquisition mechanism is undefined: git submodule, tarball, network fetch at build time, vendoring? Each has different supply-chain properties. The lockfile pins identity but does not constrain *how* the fragment arrived. A network fetch at build time turns `eutaxis generate` into an outbound-network operation; a vendored copy turns it into a vendoring workflow. The proposal commits to neither.

Combined with O5, this is the missing half of the supply-chain story. §10 Q5 (versioning) hints at this but does not surface it.

**Recommended correction.** Specify the acquisition mode before Phase 1 ships, even minimally (e.g., "fragments are resolved from a path-based registry; network fetch is out of scope for v1"). This is genuinely small as a decision but consequential as a posture.

---

### O9 — The "stable substrate" claim of §11 is empirically thin

**Problematic assumption.** §11 commits the adapter to "stable substrates: the instruction-file layer and the Agent Skills open standard," and defers what is unstable.

**Failure mode.** Both committed substrates have moved materially in the last 18 months. Skills absorbed custom commands (Claude) and deprecated custom prompts (Codex); `AGENTS.override.md` and `project_doc_max_bytes` are recent additions; the Agent Skills "open standard" is young and its open-standard status is asserted by the agents' own docs rather than by an independent body. The proposal treats stability as a binary and pins itself to "stable". A stricter framing: the mapping matrix must be versioned per adapter against a particular vendor doc revision, and `eutaxis explain` should surface the doc version it was last reconciled to.

**Recommended correction.** Add a `adapter-version` and `vendor-doc-revision` field per adapter and require the verification phase to flag drift between vendor docs and adapter assumptions. This is a small addition but it is the closest the architecture gets to honest about substrate volatility.

---

### O10 — Identifier and namespace semantics are under-specified for a registry that will eat external fragments

The example identifier `hermeneia/prose-writing` is namespaced by repository. The proposal defers the namespacing rules (Q5) but the architecture already presumes a registry, dependency resolution, and conflict semantics in the Resolution core (§4.5). Without a defined namespace algebra, "dependency" and "conflict" have no addressable referent. This is lower severity than O1–O5 because it is genuinely a schema decision, but it is one of the few §10 items where deferral does cost real Phase-1 scope.

---

## 2. Verification findings

| Claim | Status | Architectural dependency |
| --- | --- | --- |
| Output styles in Claude Code are substitutive, system-prompt-level, session-scoped, file-based; Codex has no registry counterpart | **Confirmed** (techne notes: claude/output-styles.md, customization-mechanisms.md) | §5 session-preset row; O1 |
| Codex profiles are TOML presets; `developer_instructions` is additive | **Confirmed** (codex/profiles.md) | §5 session-preset row; O1 |
| Only one Codex profile is active per session, selected via top-level `profile=` or `--profile` | **Confirmed** (codex/profiles.md) | O1 (the proposal does not mention this constraint) |
| Both agents follow the Agent Skills open standard and the `SKILL.md` directory pattern; differ in paths, frontmatter, invocation, implicit-invocation control | **Confirmed but the *extent* of difference is understated in the proposal** (codex/skills.md, claude/skills.md) | §5 on-demand row; O4 |
| Codex implicit-invocation control lives in `agents/openai.yaml`, not in skill frontmatter | **Confirmed** (codex/skills.md) | §11 (defers `agents/openai.yaml`) collides with §5 "Exact" grade — O4 |
| AGENTS.md / CLAUDE.md use cumulative global-then-project loading with documented precedence | **Confirmed** for Codex (codex/agents-loading-precedence.md, root-to-leaf merge with `project_doc_max_bytes` 32 KiB default); Claude side is *referenced as analogous* in customization-mechanisms.md but not read in detail. **Imprecise**: the proposal asserts cumulative loading without distinguishing the override-file mechanism (`AGENTS.override.md`) which interacts with managed-region ownership | §5 always-on rows; O3 |
| `project_doc_max_bytes` default 32 KiB | **Confirmed** | §4.4 (router argument), but the budget is not surfaced as a compile-time check anywhere in §4.5 |
| MCP configuration locations | **Confirmed for Codex** (`[mcp_servers.<id>]` in `config.toml`). **Imprecise for Claude**: the proposal cites `.mcp.json` and "settings permission rules" together; the supporting notes also list `~/.claude.json` at user/local scope. The matrix needs the user-level path. | §5 capability row; O5 |
| Codex custom prompts deprecated; Claude Code custom commands merged into skills | **Confirmed** (customization-mechanisms.md, codex/skills.md) | §8 ("Slash commands as adapters" subsumed) — correctly resolved |

I did not exercise web access to `https://developers.openai.com/codex` or `https://code.claude.com/docs`. All confirmations rest on the supporting techne notes. Any of these findings is invalidated if the underlying notes are themselves stale relative to current vendor docs.

---

## 3. What the proposal gets right

- **Killing the runtime directive is correct.** The reframing eliminates the activation-protocol portability failure, the sigil collision, and the runtime context-injection vector identified in the prior audit. None of these are reintroduced.
- **"Same source, not same behaviour" (P2) is the honest contract.** It is the right ceiling, and naming it explicitly is more useful than pretending equivalence.
- **Native-precedence reliance (P5) is correct as far as it goes.** Refusing to invent a parallel resolution engine is the right call, even if it leaves O2 unanswered.
- **Phased rollout puts the safest, exact-fidelity regimes first** and defers the privilege-granting and unstable surfaces. The ordering reflects the actual risk gradient.
- **Section 8 disposition table is unusually disciplined**: each element of the prior proposal is either reused or explicitly retired. This is the kind of accounting that prevents architecture drift.
- **§11 is honest about what is deferred and why.** Hooks, Codex rules, plugin manifests are correctly deferred. (Subagents is the exception — see O6.)
- **The architecture is incremental over the shipped feature.** §8 correctly notes that current `eutaxis generate` *is* the always-on regime; the proposal extends rather than replaces, which keeps migration risk low.

---

## 4. Assessment of open questions and deferrals

| Item | Safe to defer? | Reasoning |
| --- | --- | --- |
| §10 Q1 — Source schema | **Yes** | Schema choices do not constrain the architecture; they constrain ergonomics. Defer with low risk. |
| §10 Q2 — Regime-to-mechanism mapping | **Partially** | The mapping itself is in §5, so this question is really "confirm §5 + decide router-vs-skills for task-conditional content". Confirmation is required before Phase 1. The router-vs-skills sub-question is safe to defer because both choices are recoverable. |
| §10 Q3 — Ownership policy | **No.** Wrongly deferred (O3). The architecture writes into shared user files in Phase 1 and §7's security claim depends on this decision. Resolve before Phase 1. |
| §10 Q4 — Fidelity policy | **Yes**, but with caveat. The build/warn/configurable choice is recoverable. However, the underlying *fidelity grades* in §5 are themselves under-specified (O4, O5) and that is not a Q4 issue — it is a §5 issue. |
| §10 Q5 — Identifier and versioning | **No, partially.** Naming algebra is required before a cross-repo registry can resolve dependencies. Lockfile format can wait. |
| §10 Q6 — Scope granularity | **Yes** | Directory-level scope is an extension; absence does not break the v1 architecture. |
| §10 Q7 — Capability-generation gate | **No, partially.** The gate is required before Phase 3, but per O5 the regime should be redesigned before the gate is specified. |
| §10 Q8 — Packaging | **Yes** | Plugin packaging is purely additive. |
| §11 — Hooks, Codex rules, plugin manifests | **Yes** | Correctly deferred. |
| §11 — Subagents | **No.** Wrongly deferred (O6). Subagents are the native role-isolation mechanism; the session-preset regime currently routes role components to a worse-fit target. At minimum, move subagents into §10 with a default position. |

---

## 5. Verdict

**Accept with modifications.**

The reframing is sound at the level of stance: build-time compilation, no runtime directive, source unification, per-agent adapters, golden-file review. None of the identified objections threatens that stance.

However, three issues must be resolved before Phase 1 ships, not deferred:

1. **Ownership policy** (O3 / §10 Q3): the architecture writes into shared user files in Phase 1 and the §7 security argument depends on a decision that has not been made.
2. **Intra-artifact composition semantics** (O2): deterministic compilation across many components into one artifact is undefined.
3. **Session-preset mapping** (O1) and the **subagent deferral** (O6) jointly need rework: the current routing of role components to Codex profiles is structurally wrong and the better-fit native mechanism is in §11.

Two further issues must be resolved before Phase 3 ships: the **capability-regime split** (O5) and a **policy on cross-repository fragment acquisition** (O8). The fidelity claims for on-demand (O4) and the behavioural-validation gap (O7) should be addressed by re-grading and by reframing the contract, respectively, but they do not block Phase 1.

Subject to those corrections, the architecture is sound and incremental over the shipped feature. Without them, the proposal ships with a hidden behavioural divergence (O1), a non-deterministic compile (O2), and an undecided contact surface with user-authored content (O3) — any one of which would justify a redesign verdict; all three are addressable without architectural rework.
