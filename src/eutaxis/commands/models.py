"""Data containers for the commands subsystem.

A "command" is rendered as an **Agent Skill artifact**: a directory whose
canonical entrypoint is ``SKILL.md``, optionally accompanied by
agent-specific sibling files (e.g. ``agents/openai.yaml`` for Codex). The
multi-file artifact model is needed because Codex skills require the
parent directory name to equal the ``name`` field, and Codex carries UI
metadata / invocation policy / tool dependencies in the sibling
``agents/openai.yaml`` file rather than in ``SKILL.md`` frontmatter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ActionSpec:
    """Optional shell-backed action carried by a command source.

    Attributes
    ----------
    kind : str
        Action kind. Only ``"shell"`` is supported in v1.
    template : str
        Templated command string with ``{{ var }}`` placeholders.
    """

    kind: str
    template: str


@dataclass(frozen=True)
class TargetsSpec:
    """Per-source allow/deny list of adapter names.

    An empty ``include`` tuple means "all registered adapters".
    """

    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True)
class AdapterPassthrough:
    """Adapter-specific overrides declared in the source frontmatter.

    The author may inject extra YAML keys into the rendered ``SKILL.md``
    frontmatter (``frontmatter``) and extra sibling files (``files``)
    alongside the entrypoint.

    Attributes
    ----------
    frontmatter : dict[str, object]
        Extra keys merged into the rendered ``SKILL.md`` frontmatter.
        Values are emitted verbatim by the YAML dumper.
    files : dict[str, str]
        Sibling file contents keyed by POSIX-style relative path
        (e.g. ``"agents/openai.yaml"``). Templated against the same
        context as the body.
    """

    frontmatter: dict[str, object] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandSource:
    """Parsed Markdown command source.

    Attributes
    ----------
    name : str
        Slug used for the artifact directory and the invocation symbol.
    description : str
        One-line summary surfaced by ``commands list`` and the agent's
        skill picker.
    regime : str
        Activation regime; only ``"user-invoked"`` is supported in v1.
        Maps to ``disable-model-invocation: true`` on Claude and to
        ``policy.allow_implicit_invocation: false`` on Codex.
    scope_default : str
        Default install scope: ``"user"`` or ``"project"``.
    targets : TargetsSpec
        Adapter allow/deny list.
    action : ActionSpec | None
        Optional shell-backed action.
    argument_hint : str
        Optional ``argument-hint`` value (UX hint, e.g. ``"[--all]"``).
    body : str
        Markdown body, with ``{{ var }}`` placeholders still present.
    adapters : dict[str, AdapterPassthrough]
        Per-adapter frontmatter and sibling files. Keyed by adapter
        name.
    overrides : dict[str, dict]
        Per-adapter overrides for first-class fields (only
        ``action.template`` is honored today).
    source_path : Path
        Path to the source Markdown file on disk.
    layer : str
        Discovery layer: ``"builtin"``, ``"user"``, or ``"project"``.
    """

    name: str
    description: str
    regime: str
    scope_default: str
    targets: TargetsSpec
    action: ActionSpec | None
    body: str
    argument_hint: str = ""
    adapters: dict[str, AdapterPassthrough] = field(default_factory=dict)
    overrides: dict[str, dict] = field(default_factory=dict)
    source_path: Path = Path()
    layer: str = "builtin"


@dataclass(frozen=True)
class ArtifactFile:
    """One file inside a rendered skill artifact directory.

    ``relative_path`` is POSIX-style and relative to the artifact root
    (e.g. ``"SKILL.md"``, ``"agents/openai.yaml"``,
    ``".eutaxis-owned.json"``).
    """

    relative_path: str
    content: str


@dataclass(frozen=True)
class RenderedArtifact:
    """A command source rendered for one adapter as a multi-file artifact.

    Files always include the entrypoint ``SKILL.md`` (whose frontmatter
    carries the ``x-eutaxis-owned`` hash) and the
    ``.eutaxis-owned.json`` sidecar. Adapter-specific siblings (e.g.
    ``agents/openai.yaml``) may also be present.
    """

    name: str
    adapter: str
    files: tuple[ArtifactFile, ...]
    content_hash: str


@dataclass(frozen=True)
class InstallRecord:
    """One row of the install manifest.

    ``path`` is the artifact **directory**, not a single file.
    """

    name: str
    adapter: str
    scope: str
    path: Path
    content_hash: str
    installed_at: str
