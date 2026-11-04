"""Exercise the closed raw formats used by private Git transport proof."""

from __future__ import annotations

import hashlib
import struct

import pytest

from eutaxis.declarations._git_formats import (
    GitConfigEntry,
    gitmodules_registrations,
    parse_git_config_output,
    parse_git_index,
    parse_git_reference,
    parse_ls_tree_record,
    parse_packed_refs,
    regular_blob_modes,
    require_index_entry,
    resolve_git_pointer,
    validate_git_repository_config,
)
from eutaxis.declarations.exceptions import AcquisitionContractError


def _index(
    entries: tuple[tuple[int, str, int, bytes], ...],
    *,
    extensions: tuple[tuple[bytes, bytes], ...] = (),
    version: int = 2,
) -> bytes:
    body = bytearray(
        b"DIRC" + version.to_bytes(4, "big") + len(entries).to_bytes(4, "big")
    )
    previous = b""
    for mode, object_id, stage, path in entries:
        fixed = bytearray(40)
        fixed[24:28] = mode.to_bytes(4, "big")
        flags = (stage << 12) | min(len(path), 0xFFF)
        record = fixed + bytes.fromhex(object_id) + flags.to_bytes(2, "big")
        if version == 4:
            common = 0
            for left, right in zip(previous, path):
                if left != right:
                    break
                common += 1
            record += _varint(len(previous) - common) + path[common:] + b"\0"
        else:
            record += path + b"\0"
            record += b"\0" * ((-len(record)) % 8)
        body += record
        previous = path
    for signature, payload in extensions:
        body += signature + len(payload).to_bytes(4, "big") + payload
    return bytes(body) + hashlib.sha1(body).digest()


def _varint(value: int) -> bytes:
    result = bytearray([value & 0x7F])
    while value >= 0x80:
        value = (value >> 7) - 1
        result.append(0x80 | (value & 0x7F))
    result.reverse()
    return bytes(result)


def test_index_parser_authenticates_v2_entries_and_closed_extensions() -> None:
    source = _index(
        (
            (0o100644, "1" * 40, 0, b".gitmodules"),
            (0o160000, "2" * 40, 0, b"vendor/library"),
        ),
        extensions=((b"TREE", b"tree-cache"),),
    )

    parsed = parse_git_index(source, object_format="sha1", location="$.index")

    assert parsed.version == 2
    assert parsed.extensions == (b"TREE",)
    assert (
        require_index_entry(
            parsed,
            path=".gitmodules",
            admitted_modes=regular_blob_modes(),
            location="$.index.gitmodules",
        ).object_id
        == "1" * 40
    )
    assert (
        require_index_entry(
            parsed,
            path="vendor/library",
            admitted_modes=frozenset({0o160000}),
            location="$.index.gitlink",
        ).object_id
        == "2" * 40
    )


def test_index_parser_decodes_v4_prefix_compression() -> None:
    parsed = parse_git_index(
        _index(
            (
                (0o100644, "1" * 40, 0, b"rules/alpha.yaml"),
                (0o100644, "2" * 40, 0, b"rules/beta.yaml"),
            ),
            version=4,
        ),
        object_format="sha1",
        location="$.index",
    )

    assert tuple(entry.path for entry in parsed.entries) == (
        b"rules/alpha.yaml",
        b"rules/beta.yaml",
    )


@pytest.mark.parametrize(
    "mutation, message",
    (
        (lambda value: value[:-1] + bytes([value[-1] ^ 1]), "checksum"),
        (
            lambda _value: _index(
                ((0o100644, "1" * 40, 0, b"rule.yaml"),),
                extensions=((b"link", b"split"),),
            ),
            "unsupported",
        ),
        (
            lambda _value: _index(
                ((0o100644, "1" * 40, 0, b"rule.yaml"),),
                extensions=((b"sdir", b"sparse"),),
            ),
            "unsupported",
        ),
        (
            lambda _value: _index(
                ((0o100644, "1" * 40, 0, b"rule.yaml"),),
                extensions=((b"FSMN", b"monitor"),),
            ),
            "unsupported",
        ),
        (
            lambda _value: _index(
                ((0o100644, "1" * 40, 0, b"rule.yaml"),),
                extensions=((b"ZZZZ", b"unknown"),),
            ),
            "unsupported",
        ),
        (
            lambda _value: _index(
                (
                    (0o100644, "1" * 40, 0, b"rule.yaml"),
                    (0o100644, "2" * 40, 2, b"rule.yaml"),
                )
            ),
            "stage-zero",
        ),
    ),
)
def test_index_parser_rejects_checksum_extensions_and_conflict_stages(
    mutation: object, message: str
) -> None:
    baseline = _index(((0o100644, "1" * 40, 0, b"rule.yaml"),))
    source = mutation(baseline)  # type: ignore[operator]

    with pytest.raises(AcquisitionContractError, match=message):
        parsed = parse_git_index(source, object_format="sha1", location="$.index")
        require_index_entry(
            parsed,
            path="rule.yaml",
            admitted_modes=regular_blob_modes(),
            location="$.index.rule",
        )


def test_config_parser_and_repository_profile_accept_closed_local_state() -> None:
    entries = parse_git_config_output(
        b"core.repositoryformatversion\n0\0"
        b"core.bare\nfalse\0"
        b"core.worktree\n../../../../vendor/library\0",
        location="$.config",
    )

    result = validate_git_repository_config(
        entries,
        expected_worktree="vendor/library",
        git_directory=".git/modules/vendor/library",
        location="$.config",
    )

    assert result.object_format == "sha1"
    assert result.reference_storage == "files"


@pytest.mark.parametrize(
    "entry",
    (
        GitConfigEntry("include.path", "/tmp/hostile"),
        GitConfigEntry("core.hooksPath", "/tmp/hooks"),
        GitConfigEntry("core.fsmonitor", "/tmp/watch"),
        GitConfigEntry("extensions.partialClone", "origin"),
        GitConfigEntry("remote.origin.promisor", "true"),
        GitConfigEntry("filter.rules.process", "/tmp/filter"),
    ),
)
def test_repository_profile_rejects_active_or_redirecting_config(
    entry: GitConfigEntry,
) -> None:
    with pytest.raises(AcquisitionContractError, match="forbidden"):
        validate_git_repository_config(
            (entry,),
            expected_worktree=None,
            git_directory=".git",
            location="$.config",
        )


@pytest.mark.parametrize(
    "entry",
    (
        GitConfigEntry("alias.pwn", "!run-command"),
        GitConfigEntry("credential.https://example.invalid.helper", "!helper"),
        GitConfigEntry("submodule.library.update", "!run-command"),
        GitConfigEntry("browser.tool.cmd", "run-command"),
    ),
)
def test_repository_profile_rejects_command_bearing_config_families(
    entry: GitConfigEntry,
) -> None:
    with pytest.raises(AcquisitionContractError, match="forbidden"):
        validate_git_repository_config(
            (entry,),
            expected_worktree=None,
            git_directory=".git",
            location="$.config",
        )


def test_repository_profile_rejects_unclassified_keys_and_noncanonical_worktree() -> (
    None
):
    with pytest.raises(AcquisitionContractError, match="unsupported"):
        validate_git_repository_config(
            (GitConfigEntry("http.proxy", "command.invalid"),),
            expected_worktree=None,
            git_directory=".git",
            location="$.config",
        )
    with pytest.raises(AcquisitionContractError, match="canonical spelling"):
        validate_git_repository_config(
            (GitConfigEntry("core.worktree", "../../../trap/../vendor/library"),),
            expected_worktree="vendor/library",
            git_directory=".git/modules/vendor/library",
            location="$.config",
        )


@pytest.mark.parametrize(
    "entry",
    (
        GitConfigEntry("remote.origin.url", "ext::run-command %S"),
        GitConfigEntry("remote.origin.pushurl", "helper::payload"),
        GitConfigEntry("submodule.library.url", "ext::run-command"),
        GitConfigEntry("remote.origin.url", "hostile://payload"),
        GitConfigEntry("submodule.library.url", "HOSTILE://payload"),
    ),
)
def test_repository_profile_rejects_external_helper_remote_urls(
    entry: GitConfigEntry,
) -> None:
    with pytest.raises(AcquisitionContractError, match="external-helper"):
        validate_git_repository_config(
            (entry,),
            expected_worktree=None,
            git_directory=".git",
            location="$.config",
        )


def test_gitmodules_parser_retains_names_and_paths_but_rejects_commands() -> None:
    registrations = gitmodules_registrations(
        (
            GitConfigEntry("submodule.vendor/library.path", "vendor/library"),
            GitConfigEntry("submodule.vendor/library.url", "../library"),
        ),
        location="$.gitmodules",
    )

    assert registrations == (("vendor/library", "vendor/library"),)
    with pytest.raises(AcquisitionContractError, match="external update"):
        gitmodules_registrations(
            (
                GitConfigEntry("submodule.vendor/library.path", "vendor/library"),
                GitConfigEntry("submodule.vendor/library.update", "!run-command"),
            ),
            location="$.gitmodules",
        )
    with pytest.raises(AcquisitionContractError, match="external-helper"):
        gitmodules_registrations(
            (
                GitConfigEntry("submodule.vendor/library.path", "vendor/library"),
                GitConfigEntry("submodule.vendor/library.url", "ext::run-command"),
            ),
            location="$.gitmodules",
        )


def test_pointer_reference_packed_refs_and_tree_records_are_exact() -> None:
    assert (
        resolve_git_pointer(
            b"gitdir: ../../.git/modules/vendor/library\n",
            source_root="vendor/library",
            expected_target=".git/modules/vendor/library",
            location="$.pointer",
        )
        == ".git/modules/vendor/library"
    )
    assert parse_git_reference(
        b"ref: refs/heads/main\n", object_format="sha1", location="$.HEAD"
    ) == ("symbolic", "refs/heads/main")
    assert parse_packed_refs(
        b"# pack-refs with: peeled fully-peeled sorted\n"
        + ("a" * 40 + " refs/heads/main\n").encode(),
        object_format="sha1",
        location="$.packed",
    ) == (("refs/heads/main", "a" * 40),)
    assert parse_ls_tree_record(
        ("100644 blob " + "b" * 40 + "\trules/main.yaml\0").encode(),
        object_format="sha1",
        expected_path="rules/main.yaml",
        location="$.tree",
    ) == (0o100644, "blob", "b" * 40, "rules/main.yaml")


def test_packed_refs_rejects_unknown_headers_and_misplaced_peeled_records() -> None:
    with pytest.raises(AcquisitionContractError, match="trait"):
        parse_packed_refs(
            b"# pack-refs with: peeled future-trait \n"
            + ("a" * 40 + " refs/heads/main\n").encode(),
            object_format="sha1",
            location="$.packed",
        )
    with pytest.raises(AcquisitionContractError, match="peeled"):
        parse_packed_refs(
            b"# pack-refs with: peeled \n"
            + ("a" * 40 + " refs/heads/main\n^").encode()
            + ("b" * 40 + "\n").encode(),
            object_format="sha1",
            location="$.packed",
        )
    with pytest.raises(AcquisitionContractError, match="not ordered"):
        parse_packed_refs(
            b"# pack-refs with: sorted \n"
            + ("a" * 40 + " refs/heads/zeta\n").encode()
            + ("b" * 40 + " refs/heads/alpha\n").encode(),
            object_format="sha1",
            location="$.packed",
        )


@pytest.mark.parametrize(
    "reference",
    (
        b"ref: refs/heads/.hidden\n",
        b"ref: refs/heads/main.lock\n",
        b"ref: refs/heads/main@{one}\n",
    ),
)
def test_reference_parser_rejects_git_forbidden_component_forms(
    reference: bytes,
) -> None:
    with pytest.raises(AcquisitionContractError, match="reference name"):
        parse_git_reference(
            reference,
            object_format="sha1",
            location="$.HEAD",
        )


@pytest.mark.parametrize(
    "operation",
    (
        lambda: resolve_git_pointer(
            b"gitdir: /absolute/path\n",
            source_root="vendor/library",
            expected_target=".git/modules/vendor/library",
            location="$.pointer",
        ),
        lambda: resolve_git_pointer(
            b"gitdir: ../../.git/modules/vendor/library\nextra\n",
            source_root="vendor/library",
            expected_target=".git/modules/vendor/library",
            location="$.pointer",
        ),
        lambda: resolve_git_pointer(
            b"gitdir: ../../.git/modules/vendor/other\n",
            source_root="vendor/library",
            expected_target=".git/modules/vendor/library",
            location="$.pointer",
        ),
        lambda: resolve_git_pointer(
            b"gitdir: ../../../../outside\n",
            source_root="vendor/library",
            expected_target=".git/modules/vendor/library",
            location="$.pointer",
        ),
        lambda: resolve_git_pointer(
            b"gitdir: ../../trap/../.git/modules/vendor/library\n",
            source_root="vendor/library",
            expected_target=".git/modules/vendor/library",
            location="$.pointer",
        ),
        lambda: parse_git_reference(
            b"ref: refs/heads/../escape\n",
            object_format="sha1",
            location="$.HEAD",
        ),
        lambda: parse_ls_tree_record(
            ("120000 blob " + "b" * 40 + "\trules/main.yaml\0").encode(),
            object_format="sha1",
            expected_path="rules/other.yaml",
            location="$.tree",
        ),
    ),
)
def test_metadata_parsers_reject_escape_or_mismatched_records(
    operation: object,
) -> None:
    with pytest.raises(AcquisitionContractError):
        operation()  # type: ignore[operator]


def test_index_fixture_header_has_expected_layout() -> None:
    source = _index(((0o100644, "1" * 40, 0, b"rule.yaml"),))
    assert struct.unpack(">4sLL", source[:12]) == (b"DIRC", 2, 1)
