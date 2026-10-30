---
tags: []
aliases:
  - External declaration identity and acquisition
index: "[Architecture decisions](_index.md)"
---

# External declaration identity and acquisition

## Status

Accepted.

## Purpose

An external declaration must keep one semantic identity when its transport or
checkout location changes. A build must also prove which bytes and acquisition
state supplied that identity. The acquisition boundary must reject ambiguous
names, authority impersonation, path substitution, and mutation between
verification and use before the declarations enter one registry.

## Scope

This decision governs structured declaration sources acquired from a consuming
workspace. It settles the namespace and offline acquisition prerequisite for an
Oikos pilot. It does not acquire capability configuration, fetch network
content, define semantic-version ranges, or change host-owned precedence
between generated instruction artifacts.

The Eutaxis-owned declaration corpus remains a distinct internal source. The
acquisition operation loads it through the authenticated packaged-source route
defined below; callers cannot supply a registry in its place. External
acquisition applies only to the manifest's `sources` entries. Both source
classes use one issued composite facet registry and enter one combined registry.

## Trust boundary

The trusted computing base contains four components:

- loaded Eutaxis implementation
- private authority stores
- Python interpreter
- imported implementation dependencies

Issuer checks apply only when a consumer must authenticate a process-local
object.
These consumers accept the exact objects recorded by Eutaxis. Other public APIs
accept caller values and validate them structurally. Copies and reconstructed
values fail the issuer checks. Serialized values also fail those checks when
restored. By contrast, code that changes private module or class state belongs
to the trusted base and can bypass same-process Python invariants.

Callers can supply malformed manifest or lock values. Callers can also control
filesystem bytes and Git state. The packaged-acquisition entry point accepts no
caller-supplied carrier. Its loader creates carriers from retained descriptors.
The lock supplies reviewed policy. The loader compares each acquired source with
the lock. The loader cannot determine whether an internally consistent
replacement lock received review. Finally, the contract cannot detect a change
when a filesystem actor restores every observable value between checks.

If untrusted Python code shares the host process, then an isolated worker must
load sources. The worker must also run each consumer of issued objects. The
worker cannot return a process-local token to the untrusted parent without
losing the authority boundary. Accordingly, the present contract omits this
worker protocol.

## Semantic identity

An external declaration identifier has exactly this form:

```text
<namespace>/<local-name>
```

Each part matches `[a-z0-9](?:[a-z0-9-]*[a-z0-9])?`. The complete identifier
contains exactly one slash. Uppercase letters, underscores, dots, empty parts,
leading or trailing hyphens, and nested namespaces are invalid in version 1.
The source writes the complete identifier. A consumer cannot mount, alias, or
rewrite it.

The identifier is the stable semantic identity. Content and acquisition
revisions attest one realization of that identity; neither revision becomes
part of the identifier. Versioned evaluator and operation references continue
to use the existing structured pair of `id` and positive integer `version`.

Every declaration loaded through one source entry must satisfy both conditions:

- the identifier namespace equals the entry's `namespace`
- the declaration `owner` exactly equals that namespace

These conditions apply to top-level and embedded declarations using their
source-authored complete identifiers. They prevent a source from claiming
another owner's policy authority. A reference may name a declaration
from another admitted namespace, but every declaration-reference field must
first satisfy the same identifier grammar. Unknown targets and kind or version
mismatches remain errors of the existing cross-record registry.

The combined registry admits one record or versioned family for each semantic
identity. A duplicate identifier is an error even when the records originate
from different source entries or native scopes. Host scope precedence applies
to generated artifacts; it cannot shadow semantic declarations inside one
registry.

## Acquisition manifest

One closed YAML document at a caller-supplied, workspace-relative path declares
the facet vocabulary, the required internal source, and the admitted external
sources:

```yaml
schema-version: 1
facet-extensions:
  - namespace: oikos
    kind: workspace
    root: .
    path: declarations/context-facets.yaml
internal-source:
  namespace: eutaxis
  kind: packaged
sources:
  - namespace: oikos
    kind: workspace
    root: .
    files:
      - declarations/process-core.yaml
  - namespace: hermeneia
    kind: git-submodule
    root: vendor/hermeneia
    files:
      - declarations/prose.yaml
```

The top-level mapping contains exactly `schema-version`, `facet-extensions`,
`internal-source`, and `sources`. `schema-version` is the integer `1`.
`facet-extensions` is a sequence, possibly empty, whose entries each contain
exactly `namespace`, `kind`, `root`, and `path`. Each namespace is unique. Its
namespace, kind, and root equal one external source entry. Its path is a
normalized path relative to that source root and is distinct from the entry's
declaration files. The parsed extension registry `id` namespace and `owner`
must both equal the declared namespace. The reserved `eutaxis` namespace cannot
be used here; it enters only through the packaged internal source.
`internal-source` contains exactly `namespace: eutaxis` and `kind: packaged`.
The namespace `eutaxis` is reserved for this entry. `sources` is a non-empty
sequence of external entries. Each entry contains exactly `namespace`, `kind`,
`root`, and `files`:

- `namespace` follows the namespace grammar and is unique in the manifest
- `kind` is `workspace`, `vendored`, or `git-submodule`
- `root` is one normalized POSIX path relative to the consuming workspace
- `files` is a non-empty sequence of unique normalized POSIX paths relative to
  that source root

The source-entry order and each file order are authoritative. They establish
registry traversal and therefore deterministic diagnostic ownership. Version 1
does not discover files, expand globs, follow includes, or fetch content.

The packaged internal source uses the ordered resource list embedded in Eutaxis
code. That list, rather than a package-directory scan or caller input, names
every file under `eutaxis/data/declarations/v1`. The acquisition operation
opens the declaration resource root from the same installed distribution whose
code is running, retains every named byte carrier, verifies namespace and owner
`eutaxis`, and compares the files and revisions with the lock. External
declarations may reference these internal records. The combined registry visits
the internal files first in code-owned order, then external entries in manifest
order. Identifier collisions across the two classes fail normally.

The packaged `eutaxis/context-facets` registry is the mandatory base vocabulary
for both source classes. It is loaded from the code-owned resource
`eutaxis/data/registries/context-facets-v1.yaml`, must retain namespace and owner
`eutaxis`, and is locked through the packaged-source boundary. Each manifest
extension may add only facet identifiers absent from the base and every earlier
extension. Redefining a facet fails at the later extension identifier even when
its value schema is equal. Thus each constituent owner authorizes only its own
new vocabulary; no external owner can revise an Eutaxis facet.

The loader retains and hashes each extension through the same byte and
transport boundary as that source's declaration files. It then issues one
composite facet registry containing the base followed by extensions in manifest
order, with the constituent registries and owners retained as authority. This
exact composite validates the packaged and external declarations, enters the
combined declaration registry, and governs resolution. A caller cannot supply,
reorder, merge, or replace a constituent.

Only a process-issued provenance record can supply the composite assembler.
The issuer for each source class selects the exact constituent registries and
locks. The assembler does not accept constituent values from its caller. The
packaged issuer derives its record from the issued packaged source. The
external issuer must derive its record from the complete workspace/vendored
record described below. This constraint prevents the shared assembler from
bypassing the source checks.

The composite is a distinct immutable `CompositeFacetRegistry`, not an ordinary
single-owner `FacetRegistry`. It retains `schema_version: 1`, the ordered exact
constituents, the merged immutable facet mapping, an immutable mapping from each
facet identifier to its constituent registry, and `content_revision`. Its fixed
display identifier is `composite/context-facets-v1`; the identifier conveys no
ownership and the type has no `owner`. Its `validate_context` behavior is the
existing facet-registry compatibility surface. Applicability diagnostics use
the fixed display identifier and identify a constituent when a known facet is
involved.

`ResolutionTrace` replaces `facet_source_revision` with
`facet_content_revision` and records the fixed composite display identifier in
`facet_registry`. Resolution authority retains the composite object, ordered
constituents, per-facet authority mapping, merged facets, and content revision.
Two traces with different composite revisions therefore cannot appear to use
the same vocabulary. No implementation may assign composite ownership to
Eutaxis or to an extension merely to satisfy the former single-owner model.

`workspace` identifies declarations maintained as part of the consuming
workspace. `vendored` identifies an imported copy whose upstream relationship
is managed outside Eutaxis. `git-submodule` requires the additional Git proof
below. None of the three kinds grants a different semantic authority.

Capabilities are outside version 1 external acquisition. Every acquired file
must contain only the seven structured declaration kinds governed by the YAML
declaration schema. A future capability-acquisition decision must add its own
privilege review and cannot inherit this instruction-source gate silently.

## Path and byte boundary

The caller supplies an exact consuming-workspace directory and exact
workspace-relative paths for the manifest and lock. Public APIs accept exact
built-in path and string values; subclasses and path-like objects are rejected
before traversal. Version 1 is POSIX-only. A normalized relative path is a
non-empty POSIX string with no NUL, leading slash, backslash, empty segment,
`.` segment, or `..` segment. The single root value `.` is admitted only where
the manifest's `root` field names the consuming workspace itself.

The core API begins from an already-open trusted root-directory capability. The
path wrapper opens `/` for an absolute workspace path or the current directory
for a relative workspace path and treats that descriptor as the trusted root.
Ancestors of the current directory are outside the checked path. Every supplied
component below the trusted root must be nonempty and differ from `.` and `..`,
and is traversed without following a symbolic link. A relative workspace value
of `.` names the already-open current-directory capability and supplies no path
component. The core API then retains the opened workspace directory as its
capability; it never resolves the supplied text again. Every later traversal is
relative to retained directory descriptors. Each intermediate component must
be a real directory opened without following a symbolic link. Each final
manifest, lock, declaration, or `.gitmodules` component must be a regular file
opened without following a symbolic link. A source root must be a real
directory. Mounts, hard links, and filesystems remain subject to the operating system’s ordinary
descriptor semantics; symbolic-link traversal is never an accepted fallback.
An unsupported platform fails closed.

For every external source, the loader retains the normalized workspace-relative
root path, its opened directory descriptor, and its initial directory identity.
The consuming-workspace descriptor itself is the core API authority and is not
reopened. During final verification, the loader traverses each named source
root again from that workspace descriptor without following links, requires the
same directory type and identity, and performs all verification file reads
through the revalidated root descriptor. A renamed or replaced workspace,
vendored, or submodule root therefore fails even when the original retained
directory remains readable. The repeated submodule transport proof also begins
from this revalidated root.

Each file receives one authoritative read from its retained descriptor. The
loader records file identity and size metadata before and after the read and
rejects a changed identity, type, size, modification time, or change time. The
exact retained bytes are the only bytes parsed and hashed. After parsing, a
verification pass reopens the same logical path without following links,
requires the same file identity and type, reads it again, and requires the same
bytes and metadata. The verification bytes are not parsed and do not replace
the authoritative carrier. Concurrent writers that can restore all bytes,
identity, and observed metadata between the two reads are outside the version 1
threat model and must be excluded operationally.

The running Eutaxis distribution directory is a second trusted directory
capability: its ancestors are outside the acquisition check because its code is
already executing. The packaged-source loader opens its code-owned resource
roots below that retained directory without following links, records their
identity, and applies the same authoritative and verification reads to every
named resource. Substitution of either resource root or a resource between those
reads fails.

The manifest and facet registry use the canonical YAML source boundary:
duplicate keys, aliases that produce cycles, and values outside the JSON domain
fail. The lock is parsed as I-JSON and its original bytes must equal its JSON
Canonicalization Scheme serialization with no trailing newline or other byte.
Declaration files pass to a byte-owned form of the existing declaration loader.
Thus facet validation, declaration validation, hashing, registry construction,
and later resolution share authenticated byte carriers.

## Revisions and lock

The committed lock is one canonical JSON document. Its top-level object
contains exactly `facet-registry`, `internal-source`, `schema-version`, and
`sources`. `schema-version` is the integer `1`.

`facet-registry` contains exactly `base`, `content-revision`, and `extensions`.
`base` contains exactly `acquisition-revision`, `content-revision`, `id`,
`kind`, `namespace`, `owner`, `path`, and `sha256`. Its kind, namespace, owner,
and identifier are `packaged`, `eutaxis`, `eutaxis`, and
`eutaxis/context-facets`; its code-owned path is
`registries/context-facets-v1.yaml`. `extensions` matches the manifest sequence
one for one and in order. Each member has the same eight fields, with namespace,
kind, and path matching the manifest and identifier namespace and owner matching
that namespace.

Each constituent `content-revision` hashes the exact JCS object containing
`id`, `namespace`, `owner`, `path`, and `sha256`. The base
`acquisition-revision` hashes a JCS object containing exactly:

- `schema-version: 1`
- `namespace: eutaxis`
- `kind: packaged`
- `distribution: eutaxis`
- `resource-root: data`
- `path: registries/context-facets-v1.yaml`
- its `content-revision`

A `workspace` or `vendored` extension acquisition revision hashes a JCS object
containing exactly `schema-version: 1`, `namespace`, `kind`, `root`, `path`, and
its `content-revision`. A `git-submodule` extension hashes those same fields
plus `git`. The `git` value is byte-for-value identical to the exact locked Git
object of the one external source entry with the same namespace, kind, and
root; an extension cannot introduce a second Git observation.

The composite `content-revision` hashes the exact JCS object containing `base`,
whose value is the base content revision, and `extensions`, whose value is the
ordered sequence of extension content revisions. Therefore, semantic facet
content is independent of transport while every acquisition state remains
attested. The constituent identifier, owner, and byte digest occur in its
content revision and are intentionally not duplicated in an acquisition
payload.

`internal-source` contains exactly `acquisition-revision`, `content-revision`,
`files`, `kind`, and `namespace`. Its kind and namespace are `packaged` and
`eutaxis`. Its ordered files exactly match the code-owned package resource list.
Every file object contains exactly `path` and `sha256`; the path is normalized
relative to the code-owned resource root and the digest matches retained bytes.

Each member of `sources` contains exactly `acquisition-revision`,
`content-revision`, `files`, `kind`, and `namespace`, plus `git` only for a
submodule. The sequence matches manifest external entries one for one and in
order. Each source's namespace, kind, and ordered files match its manifest
entry. Every file object contains exactly `path` and `sha256`; its digest
matches the retained bytes.

The following expanded value shows the semantic shape. Whitespace in this
display is not part of an accepted lock:

```json
{
  "facet-registry": {
    "base": {
      "acquisition-revision": "sha256:HEX",
      "content-revision": "sha256:HEX",
      "id": "eutaxis/context-facets",
      "kind": "packaged",
      "namespace": "eutaxis",
      "owner": "eutaxis",
      "path": "registries/context-facets-v1.yaml",
      "sha256": "sha256:HEX"
    },
    "content-revision": "sha256:HEX",
    "extensions": [{
      "acquisition-revision": "sha256:HEX",
      "content-revision": "sha256:HEX",
      "id": "oikos/context-facets",
      "kind": "workspace",
      "namespace": "oikos",
      "owner": "oikos",
      "path": "declarations/context-facets.yaml",
      "sha256": "sha256:HEX"
    }]
  },
  "internal-source": {
    "acquisition-revision": "sha256:HEX",
    "content-revision": "sha256:HEX",
    "files": [{"path": "manual-judgment.yaml", "sha256": "sha256:HEX"}],
    "kind": "packaged",
    "namespace": "eutaxis"
  },
  "schema-version": 1,
  "sources": [{
    "acquisition-revision": "sha256:HEX",
    "content-revision": "sha256:HEX",
    "files": [{"path": "declarations/process-core.yaml", "sha256": "sha256:HEX"}],
    "kind": "workspace",
    "namespace": "oikos"
  }]
}
```

For clarity, the following minimal no-extension lock demonstrates the exact JCS
byte form. The repeated zero digests are illustrative and do not claim a
self-verifying lock. An accepted file contains no trailing newline:

```text
{"facet-registry":{"base":{"acquisition-revision":"sha256:0000000000000000000000000000000000000000000000000000000000000000","content-revision":"sha256:0000000000000000000000000000000000000000000000000000000000000000","id":"eutaxis/context-facets","kind":"packaged","namespace":"eutaxis","owner":"eutaxis","path":"registries/context-facets-v1.yaml","sha256":"sha256:0000000000000000000000000000000000000000000000000000000000000000"},"content-revision":"sha256:0000000000000000000000000000000000000000000000000000000000000000","extensions":[]},"internal-source":{"acquisition-revision":"sha256:0000000000000000000000000000000000000000000000000000000000000000","content-revision":"sha256:0000000000000000000000000000000000000000000000000000000000000000","files":[{"path":"manual-judgment.yaml","sha256":"sha256:0000000000000000000000000000000000000000000000000000000000000000"}],"kind":"packaged","namespace":"eutaxis"},"schema-version":1,"sources":[{"acquisition-revision":"sha256:0000000000000000000000000000000000000000000000000000000000000000","content-revision":"sha256:0000000000000000000000000000000000000000000000000000000000000000","files":[{"path":"declarations/process-core.yaml","sha256":"sha256:0000000000000000000000000000000000000000000000000000000000000000"}],"kind":"workspace","namespace":"oikos"}]}
```

`HEX` denotes exactly 64 lowercase hexadecimal digits in every actual digest.

The `content-revision` is the lowercase SHA-256 digest, prefixed by `sha256:`,
of the JCS serialization of this exact object:

```json
{
  "namespace": "oikos",
  "files": [
    {"path": "declarations/process-core.yaml", "sha256": "sha256:HEX"}
  ]
}
```

It binds semantic ownership, logical paths, file order, and bytes. It excludes
the transport kind and checkout root, so the same logical source has the same
content revision when moved between admitted transports.

The packaged internal source uses the same content-revision payload. Its
acquisition revision hashes a closed JCS object containing exactly
`schema-version: 1`, `namespace: eutaxis`, `kind: packaged`,
`distribution: eutaxis`, `resource-root: data/declarations/v1`, and its
`content-revision`. This proves which code-owned package boundary supplied the
internal records without converting them into an external manifest entry.

The `acquisition-revision` is the corresponding digest of one closed
kind-specific JCS object. For `workspace` and `vendored`, the object contains
exactly:

```json
{
  "schema-version": 1,
  "namespace": "oikos",
  "kind": "workspace",
  "root": ".",
  "content-revision": "sha256:HEX"
}
```

For `git-submodule`, it additionally contains `git`:

```json
{
  "schema-version": 1,
  "namespace": "hermeneia",
  "kind": "git-submodule",
  "root": "vendor/hermeneia",
  "content-revision": "sha256:HEX",
  "git": {
    "object-format": "sha1",
    "commit": "HEX",
    "gitmodules-path": ".gitmodules",
    "gitmodules-sha256": "sha256:HEX",
    "registered-name": "hermeneia",
    "registered-path": "vendor/hermeneia",
    "parent-index-mode": "160000",
    "parent-index-gitlink": "HEX"
  }
}
```

The `git` object contains exactly these eight fields. `object-format` is `sha1`
or `sha256`; `commit` and `parent-index-gitlink` contain exactly 40 or 64
lowercase hexadecimal digits as required by that format. The lock source entry
for a submodule contains exactly the common five fields plus this same `git`
object. No acquisition field is inferred during verification.

## Git-submodule proof

A `git-submodule` entry passes only when all of these facts hold:

- the consuming workspace is a primary Git worktree whose `.git` is a real
  directory reached through the descriptor boundary; linked worktrees are
  outside version 1
- the source root is registered by exactly one `.gitmodules` section whose
  locked `registered-name` identifies the section and whose `path` equals the
  manifest root
- the retained `.gitmodules` bytes have the locked digest
- the parent index contains exactly one stage-0 `.gitmodules` entry with a
  regular blob mode, no entry at a nonzero merge stage for that path, and blob
  bytes equal to the authoritative retained worktree bytes
- the parent repository index contains exactly one stage-0 entry at the
  registered path, no entry at a nonzero merge stage for that path, mode
  `160000`, and the locked gitlink object
- the parent uses an ordinary, non-split index and both repositories use the
  files reference backend; split indexes, reftable, and unknown index or
  reference extensions are outside version 1
- the nested repository uses the same object format as the parent
- the nested worktree `HEAD`, the parent index gitlink, and both locked commit
  values are identical
- the nested object exists locally, has exact type `commit`, and requires no
  promisor remote or lazy fetch
- every listed declaration and facet-extension path resolves in that commit to
  a regular blob whose bytes equal the authoritative retained worktree bytes
- every listed declaration byte digest and the two computed revisions match
  the lock

The registered name satisfies the same normalized relative POSIX path grammar
as a source root but may differ from the registered path. The nested source
root contains one real `.git` file. Its only line is a `gitdir:` path whose
normalized target is exactly
`<parent-git-dir>/modules/<registered-name>`. The target and every component
below the parent Git directory are opened without following symbolic links.
Neither Git directory may contain `commondir` or
`objects/info/alternates`. Neither local configuration may contain `include`,
`includeIf`, `core.hooksPath`, `core.fsmonitor`, `extensions.partialClone`, a
promisor remote, or another external-program, lazy-fetch, or object-store
redirection. The parent ordinary index, each admitted symbolic or loose
reference, each admitted `packed-refs` file, both local configurations, the
nested `.git` pointer, and `.gitmodules` are retained as exact metadata
carriers with identities and digests. An unexpected index extension, reference
backend, reference carrier, or configuration source fails closed.

The parent index is normative. The parent `HEAD` tree may differ from the index
gitlink and indexed `.gitmodules` blob because a deliberate staged submodule
update is a valid acquisition state. The indexed `.gitmodules` mode must be a
regular blob mode. Each listed path in the locked commit must also have a
regular blob mode; a tree, symbolic-link blob, submodule gitlink, missing path,
or other mode fails. Unlisted dirty or untracked files inside the submodule are
admitted because the manifest file list is the explicit source closure. An
unstaged change to a listed declaration or facet extension, a worktree
`.gitmodules` file that differs from the index, an unstaged nested `HEAD`, a
duplicate or differently normalized `.gitmodules` path, a missing gitlink, or
mixed object formats fails. Eutaxis does not initialize, fetch, checkout,
update, or clean a submodule.

Git metadata is read without permitting Git configuration to invoke external
programs. The implementation clears inherited `GIT_*` variables, supplies the
retained worktree and Git-directory locations explicitly, disables system and
global configuration, optional locks, prompts, replacement objects, and
external helpers, and validates every returned object identifier and mode.
Only the retained local configuration described above may affect the query.
The commit-type and blob reads disable lazy fetching and use only the admitted
local object store. Declaration bytes still come from the descriptor boundary;
the Git blob reads are comparisons and never become parser input.

The loader performs the authoritative read of every Git metadata carrier,
declaration carrier, manifest, lock, and facet carrier, then performs the
verification reads after all declaration parsing. Each reopened path must name
the same identity and yield the same bytes and metadata. Both collections must
produce the same parent gitlink, nested `HEAD`, object format, configuration,
local commit-type result, parent-index `.gitmodules` blob, and commit-tree file
blobs. The issued result retains the authoritative bytes and the verification
evidence. A writer that restores every carrier to its
prior bytes and metadata between the two collections is an acquisition-wide
ABA attack and is outside the version 1 threat model; verified acquisition
requires exclusive operational control of these files.

## Validation and registry order

Acquisition validates one source completely before making any declaration from
it visible. The full order is:

1. validate and retain the manifest and canonical lock
2. establish the packaged resource roots and every external source root and
   initial transport proof
3. authoritatively read and parse the packaged facet base and each extension,
   then verify their lock digests and revisions
4. reject duplicate facet identifiers and issue the exact composite facet
   registry with its content revision
5. authoritatively read every code-owned packaged and listed external
   declaration, verify its file digest, and compute source revisions
6. parse each retained declaration file and validate its schema and intrinsic
   semantics against the issued facet registry
7. validate every source namespace, owner, and declaration-reference grammar
8. revalidate every external root path against its retained directory identity,
   perform the verification reads of every byte and metadata carrier through
   the revalidated roots, repeat each transport proof, and reject any changed
   observation
9. build one combined registry and apply existing cross-record contracts

Private issued records may connect these steps, but those records do not
certify that all required checks passed. A restricted workspace/vendored stage binds
one contract that contains no Git entries. The stage retains the roots,
carriers, and composite facet registry for that contract. The package does not
export the stage, and semantic consumers do not accept it. If a contract
contains a `git-submodule` entry, the restricted stage rejects the whole
contract.

Private packaged-loader methods divide their work into three ordered phases:

- read and admit the packaged facet base
- read packaged rule and procedure files after admitting every facet
- verify every carrier after the final authoritative read

The existing public packaged-only callable runs all three phases and returns
the same issued packaged source. Instead, the combined loader can place each
external facet read between the first and second phases.

Registry traversal visits packaged internal files in code-owned order, then
manifest source-entry order, explicit file order, and the top-level declaration
followed by embedded records in authored order. Intrinsic errors therefore fail
before a collision or unresolved cross-record reference could assign them a
misleading owner.

The declaration-reference class is closed by typed model traversal. It contains
exactly:

- every declaration's `relations[*].target`
- every rule's `criteria[*].evaluator.id`, including embedded rules
- every procedure and operation predicate's `evaluator.id` when present
- every procedure action's `operation.id`
- each resolution policy `conflicts[*]` and each present
  `strategy.retain`, `strategy.replace`, `strategy.with`, or `strategy.result`
- each composition manifest `sections[*].declarations[*]` and `policies[*]`

Local norm, criterion, predicate, action-node, transition, state, failure,
fixture, parameter, input, and section identifiers remain governed by their
existing local grammars; they are not declaration references. A schema change
that adds a typed declaration reference must extend this traversal and its
planted invalid-identifier test in the same change.

The successful boundary alone returns an issued, immutable result. The result
retains:

- the exact manifest and lock carriers
- the exact packaged-facet and external-facet carriers
- the exact packaged-source and external-source carriers
- the exact Git metadata carriers
- every constituent and the issued composite facet registry
- byte-owned parsed records and computed revisions
- the resulting declaration registry

A process-local, identity-indexed issuance record
authenticates the result and its nested carriers within the trusted computing
base. The resolver accepts only this issued result. The catalog builder accepts
the same object. Neither consumer accepts paths or a caller-supplied registry.

## Catalog provenance

The persisted declaration catalog moves to index revision 2 when external
acquisition lands. The top-level object preserves the closed revision 1
collections `conflicts`, `contracts`, `declarations`, and `sources`, changes
`index-revision` to `2`, and adds the required `facet-content-revision`. That
field satisfies the exact prefixed lowercase digest grammar and equals the
issued composite registry's transport-independent content revision. The source
table records transport-independent logical provenance:

```json
{
  "namespace": "oikos",
  "path": "declarations/process-core.yaml",
  "sha256": "sha256:HEX"
}
```

Each unversioned declaration row and versioned contract row records:

```json
{
  "namespace": "oikos",
  "path": "declarations/process-core.yaml",
  "document-path": ["rules", 0],
  "line": 12,
  "column": 5
}
```

These objects are closed. `namespace` satisfies the namespace grammar. `path`
satisfies the normalized POSIX file-path grammar. `sha256` satisfies the exact
prefixed lowercase digest grammar. `document-path` is an ordered array whose
items are exact built-in strings or non-negative exact integers; booleans and
subclasses are invalid. `line` and `column` are positive exact integers. The
catalog contains no absolute root, source-root field, transport kind, or
checkout path.

The source table has one row for every packaged or external declaration file
used by the registry and no other row. `(namespace, path)` is unique. Every
`declarations[*].source` and `contracts[*].source` object joins exactly one
source row on that pair and repeats no digest. `(namespace, path,
document-path)` is unique across both collections together. One source file may
own its top-level row and embedded rows at distinct document paths. Every source
row must be referenced by at least one row in either collection.

The revision 2 catalog constructor accepts only an issued acquisition result.
It uses byte-owned positions, sorts source rows lexically by `(namespace,
path)`, and retains the existing canonical declaration-key order for record
rows. Manifest order therefore controls registry diagnostics but not catalog
serialization. For identical facet content revision, namespace, logical
paths, and declaration bytes, `catalog_json_bytes` is byte-identical across
workspace, vendored, and submodule transports. Registry and resolution
equivalence require the same facet content revision and compare typed values;
their internal issuance identities are intentionally process-local and are not
serialized. Catalog revision 1 remains readable during migration but cannot be
used as an external-source authority.

## Verification contract

The implementation gate plants at least one rejection for each manifest, lock,
facet-base, facet-extension, packaged-source, external-source, path, digest,
revision, namespace, owner, duplicate-facet, reference, Git, catalog, and
issuance invariant. The reference matrix contains one invalid identifier in
every class enumerated above. Facet cases cover namespace, identifier, and
owner impersonation. The path matrix covers an already-open relative trusted
root, every symbolic component below it, source-root replacement for all three
transports, a symbolic source root and file, replacement after opening,
file-type substitution, and a metadata change during reading. The Git matrix
covers split indexes, unsupported reference storage, parent and nested config
includes, every rejected redirection, an environment override, a missing or
non-commit object, a changed carrier between reads, index/`HEAD` disagreement,
an object-format mismatch, and distinct valid section names and paths. Catalog
cases substitute the facet content revision and break every source join and
coordinate invariant.
Git byte-binding cases cover a dirty listed declaration, a dirty facet
extension, a non-blob commit-tree path, and worktree `.gitmodules` bytes that
differ from the parent index. Index-stage cases cover three unmerged
`.gitmodules` entries without stage 0, stage 0 plus a nonzero stage, and
unmerged gitlink entries. The stage checks repeat during final transport
verification. The staged-parent-update positive case requires both the gitlink
and `.gitmodules` bytes to match stage-0 parent-index entries.

Positive tests cover all three external transports with the same retained
declaration bytes. They prove equal content revisions, equal registry and
resolution values under the same facet content revision, and byte-identical
catalogs, while acquisition revisions differ where the transport contract
differs. A known-failure test accompanies every checker or validator so the
gate proves that each operation can reject its target class before a clean
result is trusted.

## Failure ownership

An acquisition failure names the source entry and deepest manifest, lock, path,
Git, or declaration field that makes the contract false. A mismatch never
updates the lock implicitly. Lock generation is a separate explicit operation
whose complete diff must be reviewed before the next verified acquisition.

The following failures are distinct:

- invalid manifest, lock, facet-base, or facet-extension syntax and shape
- packaged-source identity, file, or revision mismatch
- duplicate namespace or logical path
- path escape, symbolic link, wrong file type, or observed concurrent mutation
- missing or mismatched Git-submodule proof
- file, content-revision, or acquisition-revision mismatch
- declaration schema or intrinsic semantic failure
- identifier namespace, owner, or reference-grammar mismatch
- combined-registry collision or cross-record contract failure

## Discarded alternatives

- **Consumer aliases or mount prefixes.** Rejected because one declaration
  would acquire several semantic identities and references would depend on the
  consuming repository.
- **Hash as semantic identity.** Rejected because every content edit would
  rename the declaration and invalidate references. Hashes attest revisions.
- **Native-scope precedence for duplicate declarations.** Rejected because
  artifact precedence cannot authorize semantic shadowing inside one registry.
- **Directory discovery or globs.** Rejected because discovery leaves the
  admitted source set dependent on mutable directory contents.
- **Build-time network acquisition.** Rejected from version 1 because it makes
  a deterministic build depend on remote state and expands the supply-chain
  boundary.
- **Path verification followed by path-based parsing.** Rejected because the
  verified file can be replaced between those operations.
- **Acquiring capability configuration under the same gate.** Rejected because
  integrity does not substitute for privilege-change review.
- **Encoding transport data in catalog provenance.** Rejected because moving
  identical declarations between admitted transports would create semantic
  catalog drift.

## Consequences

- External identifiers and policy ownership become source-verifiable before
  combined registry construction.
- A source can move between workspace, vendored, and submodule transport
  without changing semantic identities or content revision.
- A transport change remains reviewable through the separate acquisition
  revision.
- Acquisition requires a new byte-owned declaration-loader boundary and a
  process-local issued result before the Oikos pilot.
- The combined registry always includes the locked packaged Eutaxis contracts
  and uses the one locked facet vocabulary retained by the acquisition result.
- Catalog index revision 2 becomes a coordinated schema and API migration; the
  current index remains a compatibility reader, not an external authority.
- Lock generation, semantic diffing, and rollback tooling remain required
  before conversion of an external source.
