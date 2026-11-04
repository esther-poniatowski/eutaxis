"""Parse the closed Git metadata formats admitted by external acquisition."""

from __future__ import annotations

import hashlib
import posixpath
import re
from dataclasses import dataclass
from typing import NamedTuple, NoReturn

from .acquisition_paths import AcquisitionPathError, normalized_relative_path
from .exceptions import AcquisitionContractError

_INDEX_EXTENSIONS = frozenset({b"TREE", b"REUC", b"UNTR", b"EOIE", b"IEOT"})
_OBJECT_FORMATS = {
    "sha1": (20, re.compile(r"[0-9a-f]{40}\Z")),
    "sha256": (32, re.compile(r"[0-9a-f]{64}\Z")),
}
_REGULAR_MODES = frozenset({0o100644, 0o100755})


class GitIndexEntry(NamedTuple):
    """Retain one exact entry from an authenticated Git index."""

    mode: int
    object_id: str
    stage: int
    path: bytes


@dataclass(frozen=True)
class ParsedGitIndex:
    """Retain authenticated entries and the admitted extension sequence."""

    version: int
    entries: tuple[GitIndexEntry, ...]
    extensions: tuple[bytes, ...]


class GitConfigEntry(NamedTuple):
    """Retain one key and value emitted by the code-owned config parser."""

    key: str
    value: str


class GitRepositoryConfig(NamedTuple):
    """Retain the repository properties used by closed local queries."""

    object_format: str
    reference_storage: str


class GitModulesRegistration(NamedTuple):
    """Retain one named submodule path from exact `.gitmodules` bytes."""

    name: str
    path: str


class GitReferenceValue(NamedTuple):
    """Retain either one object identifier or one symbolic reference."""

    kind: str
    value: str


class GitTreeEntry(NamedTuple):
    """Retain one exact `ls-tree -z` record."""

    mode: int
    object_type: str
    object_id: str
    path: str


def parse_git_index(
    source: bytes,
    *,
    object_format: str,
    location: str,
) -> ParsedGitIndex:
    """Authenticate and parse an ordinary version 2, 3, or 4 Git index."""
    hash_size, _pattern = _object_format(object_format, location)
    if len(source) < 12 + hash_size:
        _fail(location, "index is truncated")
    body = source[:-hash_size]
    if hashlib.new(object_format, body).digest() != source[-hash_size:]:
        _fail(location, "index checksum differs")
    if body[:4] != b"DIRC":
        _fail(location, "index signature differs")
    version = int.from_bytes(body[4:8], "big")
    if version not in {2, 3, 4}:
        _fail(location, f"index version {version} is unsupported")
    count = int.from_bytes(body[8:12], "big")
    offset = 12
    previous_path = b""
    entries: list[GitIndexEntry] = []
    for index in range(count):
        entry_location = f"{location}.entries[{index}]"
        entry_start = offset
        fixed_size = 40 + hash_size + 2
        if offset + fixed_size > len(body):
            _fail(entry_location, "entry is truncated")
        mode = int.from_bytes(body[offset + 24 : offset + 28], "big")
        object_id = body[offset + 40 : offset + 40 + hash_size].hex()
        flags = int.from_bytes(
            body[offset + 40 + hash_size : offset + fixed_size], "big"
        )
        offset += fixed_size
        if flags & 0x4000:
            if version < 3 or offset + 2 > len(body):
                _fail(entry_location, "extended flags are malformed")
            extended_flags = int.from_bytes(body[offset : offset + 2], "big")
            if extended_flags & ~0x6000:
                _fail(entry_location, "extended flags are unsupported")
            offset += 2
        if version == 4:
            strip_count, offset = _decode_index_varint(body, offset, entry_location)
            if strip_count > len(previous_path):
                _fail(entry_location, "path prefix compression is invalid")
            terminator = body.find(b"\0", offset)
            if terminator < 0:
                _fail(entry_location, "path is unterminated")
            path = (
                previous_path[: len(previous_path) - strip_count]
                + body[offset:terminator]
            )
            offset = terminator + 1
        else:
            terminator = body.find(b"\0", offset)
            if terminator < 0:
                _fail(entry_location, "path is unterminated")
            path = body[offset:terminator]
            encoded_length = flags & 0x0FFF
            if encoded_length < 0x0FFF and encoded_length != len(path):
                _fail(entry_location, "path length differs from flags")
            entry_size = terminator + 1 - entry_start
            offset = entry_start + ((entry_size + 7) // 8) * 8
            if offset > len(body):
                _fail(entry_location, "entry padding is truncated")
        if not path or b"\0" in path:
            _fail(entry_location, "path is invalid")
        entries.append(GitIndexEntry(mode, object_id, (flags >> 12) & 0x3, path))
        previous_path = path

    extensions: list[bytes] = []
    while offset < len(body):
        if offset + 8 > len(body):
            _fail(location, "index extension header is truncated")
        signature = body[offset : offset + 4]
        size = int.from_bytes(body[offset + 4 : offset + 8], "big")
        offset += 8
        if offset + size > len(body):
            _fail(location, "index extension is truncated")
        if signature not in _INDEX_EXTENSIONS:
            name = signature.decode("ascii", errors="backslashreplace")
            _fail(location, f"index extension {name!r} is unsupported")
        extensions.append(signature)
        offset += size
    return ParsedGitIndex(version, tuple(entries), tuple(extensions))


def parse_git_config_output(
    source: bytes, *, location: str
) -> tuple[GitConfigEntry, ...]:
    """Parse complete NUL-delimited output from the code-owned Git parser."""
    if not source:
        return ()
    if not source.endswith(b"\0"):
        _fail(location, "Git config output is not NUL terminated")
    result: list[GitConfigEntry] = []
    for index, record in enumerate(source[:-1].split(b"\0")):
        key_bytes, separator, value_bytes = record.partition(b"\n")
        if not separator or not key_bytes:
            _fail(f"{location}[{index}]", "Git config record is malformed")
        try:
            key = key_bytes.decode("utf-8")
            value = value_bytes.decode("utf-8")
        except UnicodeDecodeError:
            _fail(f"{location}[{index}]", "Git config record is not UTF-8")
        if "\n" in key or "\r" in key:
            _fail(f"{location}[{index}]", "Git config key is malformed")
        result.append(GitConfigEntry(key, value))
    return tuple(result)


def validate_git_repository_config(
    entries: tuple[GitConfigEntry, ...],
    *,
    expected_worktree: str | None,
    git_directory: str,
    location: str,
) -> GitRepositoryConfig:
    """Reject every repository setting outside the closed offline profile."""
    grouped: dict[str, list[str]] = {}
    for entry in entries:
        key = entry.key.casefold()
        grouped.setdefault(key, []).append(entry.value)
        if _is_forbidden_config_key(key):
            _fail(location + "." + entry.key, "configuration key is forbidden")
        if not _is_admitted_config_key(key):
            _fail(location + "." + entry.key, "configuration key is unsupported")
        _validate_passive_config_value(key, entry.value, location + "." + entry.key)
    for key in (
        "core.repositoryformatversion",
        "core.bare",
        "core.worktree",
        "extensions.objectformat",
        "extensions.refstorage",
    ):
        if len(grouped.get(key, ())) > 1:
            _fail(location + "." + key, "configuration key is repeated")

    version = grouped.get("core.repositoryformatversion", ["0"])[0]
    if version not in {"0", "1"}:
        _fail(location + ".core.repositoryformatversion", "value is unsupported")
    if grouped.get("core.bare", ["false"])[0].casefold() not in {
        "false",
        "no",
        "off",
        "0",
    }:
        _fail(location + ".core.bare", "repository must be non-bare")
    object_format = grouped.get("extensions.objectformat", ["sha1"])[0].casefold()
    _object_format(object_format, location + ".extensions.objectformat")
    reference_storage = grouped.get("extensions.refstorage", ["files"])[0].casefold()
    if reference_storage != "files":
        _fail(location + ".extensions.refstorage", "reference storage must be files")

    worktrees = grouped.get("core.worktree", [])
    if expected_worktree is None:
        if worktrees:
            _fail(location + ".core.worktree", "worktree redirection is unsupported")
    else:
        if len(worktrees) != 1:
            _fail(location + ".core.worktree", "nested worktree must be explicit")
        _require_canonical_git_path(
            git_directory,
            worktrees[0],
            expected_worktree,
            location + ".core.worktree",
        )
    return GitRepositoryConfig(object_format, reference_storage)


def gitmodules_registrations(
    entries: tuple[GitConfigEntry, ...], *, location: str
) -> tuple[GitModulesRegistration, ...]:
    """Extract exact submodule registrations and reject active directives."""
    paths: dict[str, str] = {}
    for entry in entries:
        key = entry.key
        folded = key.casefold()
        if folded.startswith("include.") or folded.startswith("includeif."):
            _fail(location + "." + key, "include directives are forbidden")
        match = re.fullmatch(r"submodule\.(.+)\.([^.]+)", key, flags=re.IGNORECASE)
        if match is None:
            _fail(location + "." + key, "only submodule sections are admitted")
        name, field = match.groups()
        try:
            normalized_name = normalized_relative_path(name, allow_dot=False)
        except AcquisitionPathError as exc:
            _fail(location + "." + key, str(exc))
        field = field.casefold()
        if field == "path":
            if normalized_name in paths:
                _fail(location + "." + key, "submodule path is repeated")
            try:
                paths[normalized_name] = normalized_relative_path(
                    entry.value, allow_dot=False
                )
            except AcquisitionPathError as exc:
                _fail(location + "." + key, str(exc))
        elif field == "update" and entry.value.lstrip().startswith("!"):
            _fail(location + "." + key, "external update commands are forbidden")
        elif field not in {"url", "branch", "update", "shallow", "ignore"}:
            _fail(location + "." + key, "submodule field is unsupported")
        elif field == "url":
            _require_passive_url(entry.value, location + "." + key)
    return tuple(GitModulesRegistration(name, path) for name, path in paths.items())


def resolve_git_pointer(
    source: bytes,
    *,
    source_root: str,
    expected_target: str,
    location: str,
) -> str:
    """Parse one nested `.git` pointer and require its exact normalized target."""
    try:
        text = source.decode("utf-8")
    except UnicodeDecodeError:
        _fail(location, "Git pointer is not UTF-8")
    if not text.endswith("\n") or text.count("\n") != 1 or "\r" in text:
        _fail(location, "Git pointer must contain one LF-terminated line")
    line = text[:-1]
    if not line.startswith("gitdir: "):
        _fail(location, "Git pointer prefix differs")
    return _require_canonical_git_path(
        source_root,
        line[8:],
        expected_target,
        location,
    )


def parse_git_reference(
    source: bytes, *, object_format: str, location: str
) -> GitReferenceValue:
    """Parse one detached object identifier or symbolic reference."""
    try:
        text = source.decode("ascii")
    except UnicodeDecodeError:
        _fail(location, "reference is not ASCII")
    if not text.endswith("\n") or text.count("\n") != 1 or "\r" in text:
        _fail(location, "reference must contain one LF-terminated line")
    value = text[:-1]
    if value.startswith("ref: "):
        reference = value[5:]
        _require_reference_name(reference, location)
        return GitReferenceValue("symbolic", reference)
    _require_object_id(value, object_format, location)
    return GitReferenceValue("object", value)


def parse_packed_refs(
    source: bytes, *, object_format: str, location: str
) -> tuple[tuple[str, str], ...]:
    """Parse a closed ordinary `packed-refs` file."""
    try:
        text = source.decode("ascii")
    except UnicodeDecodeError:
        _fail(location, "packed references are not ASCII")
    if text and not text.endswith("\n"):
        _fail(location, "packed references are not LF terminated")
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    header_traits: frozenset[str] = frozenset()
    peeled_previous = False
    for index, line in enumerate(text.splitlines()):
        line_location = f"{location}[{index}]"
        if not line:
            _fail(line_location, "blank packed-reference records are unsupported")
        if line.startswith("#"):
            if index != 0 or not line.startswith("# pack-refs with: "):
                _fail(line_location, "packed-reference header is unsupported")
            payload = line.removeprefix("# pack-refs with: ")
            if payload.endswith(" "):
                payload = payload[:-1]
            if not payload or "  " in payload:
                _fail(line_location, "packed-reference header is malformed")
            traits = payload.split(" ")
            if (
                not traits
                or len(set(traits)) != len(traits)
                or any(
                    trait not in {"peeled", "fully-peeled", "sorted"}
                    for trait in traits
                )
            ):
                _fail(line_location, "packed-reference header trait is unsupported")
            header_traits = frozenset(traits)
            continue
        if line.startswith("^"):
            _require_object_id(line[1:], object_format, line_location)
            if (
                not result
                or peeled_previous
                or not result[-1][0].startswith("refs/tags/")
                or not ({"peeled", "fully-peeled"} & header_traits)
            ):
                _fail(line_location, "peeled value is unsupported here")
            peeled_previous = True
            continue
        peeled_previous = False
        object_id, separator, reference = line.partition(" ")
        if not separator or " " in reference:
            _fail(line_location, "packed reference record is malformed")
        _require_object_id(object_id, object_format, line_location)
        _require_reference_name(reference, line_location)
        if reference in seen:
            _fail(line_location, "packed reference is repeated")
        seen.add(reference)
        result.append((reference, object_id))
    if "sorted" in header_traits:
        references = tuple(reference.encode("ascii") for reference, _object in result)
        if any(left >= right for left, right in zip(references, references[1:])):
            _fail(location, "packed references declare sorted but are not ordered")
    return tuple(result)


def parse_ls_tree_record(
    source: bytes, *, object_format: str, expected_path: str, location: str
) -> GitTreeEntry:
    """Parse exactly one literal-path `ls-tree -z` record."""
    if not source.endswith(b"\0") or source.count(b"\0") != 1:
        _fail(location, "tree query must return exactly one NUL-terminated record")
    header, separator, path_bytes = source[:-1].partition(b"\t")
    if not separator:
        _fail(location, "tree record has no path separator")
    fields = header.split(b" ")
    if len(fields) != 3:
        _fail(location, "tree record header is malformed")
    try:
        mode_text, object_type, object_id = (field.decode("ascii") for field in fields)
        path = path_bytes.decode("utf-8")
        mode = int(mode_text, 8)
    except (UnicodeDecodeError, ValueError):
        _fail(location, "tree record is malformed")
    _require_object_id(object_id, object_format, location)
    if path != expected_path:
        _fail(location, "tree record path differs")
    return GitTreeEntry(mode, object_type, object_id, path)


def require_index_entry(
    index: ParsedGitIndex,
    *,
    path: str,
    admitted_modes: frozenset[int],
    location: str,
) -> GitIndexEntry:
    """Require one stage-zero entry and no conflict-stage entry at a path."""
    encoded = path.encode("utf-8")
    matches = tuple(entry for entry in index.entries if entry.path == encoded)
    if len(matches) != 1 or matches[0].stage != 0:
        _fail(location, "index must contain exactly one stage-zero entry")
    entry = matches[0]
    if entry.mode not in admitted_modes:
        _fail(location, "index entry mode is unsupported")
    return entry


def regular_blob_modes() -> frozenset[int]:
    """Return the closed set of regular Git blob modes."""
    return _REGULAR_MODES


def _decode_index_varint(source: bytes, offset: int, location: str) -> tuple[int, int]:
    if offset >= len(source):
        _fail(location, "path prefix length is missing")
    value = source[offset] & 0x7F
    byte = source[offset]
    offset += 1
    while byte & 0x80:
        if offset >= len(source):
            _fail(location, "path prefix length is truncated")
        byte = source[offset]
        offset += 1
        value = ((value + 1) << 7) + (byte & 0x7F)
    return value, offset


def _object_format(value: str, location: str) -> tuple[int, re.Pattern[str]]:
    result = _OBJECT_FORMATS.get(value)
    if result is None:
        _fail(location, "object format must be sha1 or sha256")
    return result


def _require_object_id(value: str, object_format: str, location: str) -> None:
    _size, pattern = _object_format(object_format, location)
    if pattern.fullmatch(value) is None:
        _fail(location, "object identifier has the wrong format")


def _require_reference_name(value: str, location: str) -> None:
    if not value.startswith("refs/"):
        _fail(location, "symbolic reference must be below refs/")
    components = value.split("/")
    if (
        value.endswith("/")
        or value.endswith(".")
        or ".." in value
        or "@{" in value
        or "//" in value
        or "\\" in value
        or any(character in value for character in " ~^:?*[")
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or any(
            component.startswith(".") or component.endswith(".lock")
            for component in components
        )
    ):
        _fail(location, "reference name is unsupported")


def _require_canonical_git_path(
    base: str,
    value: str,
    expected: str,
    location: str,
) -> str:
    if not value or value.startswith("/") or "\\" in value or "\0" in value:
        _fail(location, "Git path must be relative POSIX text")
    if any(component in {"", "."} for component in value.split("/")):
        _fail(location, "Git path is not normalized")
    try:
        normalized_base = normalized_relative_path(base, allow_dot=False)
        normalized_expected = normalized_relative_path(expected, allow_dot=False)
    except AcquisitionPathError as exc:
        _fail(location, str(exc))
    canonical = posixpath.relpath(normalized_expected, start=normalized_base)
    if value != canonical:
        _fail(location, "Git path does not use the exact canonical spelling")
    return normalized_expected


def _is_forbidden_config_key(key: str) -> bool:
    exact = {
        "core.alternaterefscommand",
        "core.askpass",
        "core.editor",
        "core.fsmonitor",
        "core.gitproxy",
        "core.hookspath",
        "core.sshcommand",
        "credential.helper",
        "diff.external",
        "extensions.partialclone",
        "gpg.program",
        "interactive.difffilter",
        "sequence.editor",
    }
    if (
        key in exact
        or key.startswith("include.")
        or key.startswith("includeif.")
        or key.startswith("alias.")
        or key.startswith("browser.")
        or key.startswith("pager.")
    ):
        return True
    parts = key.split(".")
    if parts[0] == "credential" and parts[-1] == "helper":
        return True
    if parts[0] == "submodule" and parts[-1] == "update":
        return True
    if parts[0] in {"help", "web"} and parts[-1] == "browser":
        return True
    if parts[0] == "man" and parts[-1] in {"cmd", "path", "viewer"}:
        return True
    if (
        len(parts) >= 3
        and parts[0] in {"difftool", "mergetool"}
        and parts[-1]
        in {
            "cmd",
            "path",
        }
    ):
        return True
    if (
        len(parts) >= 3
        and parts[0] == "filter"
        and parts[-1]
        in {
            "clean",
            "smudge",
            "process",
        }
    ):
        return True
    if (
        len(parts) >= 3
        and parts[0] == "remote"
        and parts[-1]
        in {
            "promisor",
            "partialclonefilter",
            "vcs",
        }
    ):
        return True
    return False


def _is_admitted_config_key(key: str) -> bool:
    if key in {
        "core.repositoryformatversion",
        "core.filemode",
        "core.bare",
        "core.logallrefupdates",
        "core.ignorecase",
        "core.precomposeunicode",
        "core.symlinks",
        "core.worktree",
        "extensions.objectformat",
        "extensions.refstorage",
        "user.name",
        "user.email",
    }:
        return True
    families = (
        r"remote\..+\.(url|pushurl|fetch)",
        r"branch\..+\.(remote|merge)",
        r"submodule\..+\.(url|active)",
    )
    return any(re.fullmatch(pattern, key) is not None for pattern in families)


def _validate_passive_config_value(key: str, value: str, location: str) -> None:
    if re.fullmatch(r"(remote|submodule)\..+\.(url|pushurl)", key) is not None:
        _require_passive_url(value, location)


def _require_passive_url(value: str, location: str) -> None:
    candidate = value.lstrip()
    scheme = re.match(r"([A-Za-z][A-Za-z0-9+.-]*)://", candidate)
    if (
        not value
        or candidate.startswith("!")
        or re.match(r"[A-Za-z0-9][A-Za-z0-9+.-]*::", candidate, flags=re.IGNORECASE)
        is not None
        or (
            scheme is not None
            and scheme.group(1).casefold()
            not in {"file", "git", "http", "https", "ssh"}
        )
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        _fail(location, "external-helper remote URL is forbidden")


def _fail(location: str, message: str) -> NoReturn:
    raise AcquisitionContractError(location, message)
