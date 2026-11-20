"""Check draft preparation through its command boundary."""

import json
from pathlib import Path

import pytest

from specs.prepare_release_capsule import main
from specs.verify_release_capsule import verify_bundle
from tests.test_lock_cli import _invoke, _write_workspace

ReleaseFixture = tuple[list[str], Path, Path, Path]


@pytest.fixture
def setup_release(tmp_path: Path) -> ReleaseFixture:
    """Prepare locked workspace bytes, a baseline and one staged output."""
    workspace = tmp_path / "workspace"
    manifest = _write_workspace(workspace)
    result = _invoke(workspace, manifest)
    assert result.exit_code == 0, result.stderr
    lock = workspace / "lock.json"
    lock.write_bytes(result.stdout_bytes)

    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for name in ("compiled.md", "old.md", "ledger.yaml", "distribution.tar"):
        (inputs / name).write_bytes(name.encode())
    plan = inputs / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "outputs": {"host/new.md": "compiled.md"},
                "goldens": {"host/old.md": "old.md", "host/absent.md": None},
                "accountability-ledger": "ledger.yaml",
                "distribution": "distribution.tar",
            }
        )
    )
    bundle = tmp_path / "bundle"
    args = [
        "--workspace",
        str(workspace),
        "--manifest",
        manifest,
        "--lock",
        lock.name,
        "--plan",
        str(plan),
    ]
    return args, plan, bundle, lock


def test_prepare_and_verify(
    setup_release: ReleaseFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    args, plan, bundle, _ = setup_release
    original_plan = plan.read_bytes()
    assert main([*args, "--bundle", str(bundle)]) == 0
    address = capsys.readouterr().out.strip()
    verify_bundle(bundle, address)
    store = bundle / "blobs" / "sha256"
    capsule = json.loads((store / address.removeprefix("sha256:")).read_bytes())
    targets = capsule["managed-targets"]
    assert targets["host/old.md"] is None
    assert targets["host/absent.md"] is None
    assert (
        store / targets["host/new.md"].removeprefix("sha256:")
    ).read_bytes() == b"compiled.md"
    assert plan.read_bytes() == original_plan
    assert main([*args, "--bundle", str(bundle.with_name("repeat"))]) == 0
    assert capsys.readouterr().out.strip() == address
    with pytest.raises(SystemExit) as error:
        main([*args, "--bundle", str(bundle)])
    assert error.value.code == 1
    assert "already exists" in capsys.readouterr().err
    verify_bundle(bundle, address)


@pytest.mark.parametrize(
    ("fault", "diagnostic"),
    [
        ("traversal", "not a normalized relative POSIX path"),
        ("symlink", "compiled.md"),
        ("duplicate", "duplicate JSON object key"),
        ("lock", "Invalid external acquisition"),
    ],
)
def test_prepare_rejects_fault_without_publishing(
    setup_release: ReleaseFixture,
    capsys: pytest.CaptureFixture[str],
    fault: str,
    diagnostic: str,
) -> None:
    args, plan, bundle, lock = setup_release
    values = json.loads(plan.read_bytes())
    if fault == "traversal":
        values["outputs"]["host/new.md"] = "../compiled.md"
        plan.write_text(json.dumps(values))
    elif fault == "symlink":
        compiled = plan.parent / "compiled.md"
        compiled.unlink()
        compiled.symlink_to(plan.parent / "old.md")
    elif fault == "duplicate":
        plan.write_text('{"outputs": {}, "outputs": {}}')
    else:
        lock.write_bytes(b"broken lock")

    with pytest.raises(SystemExit) as error:
        main([*args, "--bundle", str(bundle)])
    assert error.value.code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Preparation failed:" in captured.err
    assert diagnostic in captured.err
    assert not bundle.exists()
    assert not list(bundle.parent.glob(".eutaxis-release-*"))


def test_prepare_successor_chain(
    setup_release: ReleaseFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    args, plan, initial, lock = setup_release
    assert main([*args, "--bundle", str(initial)]) == 0
    initial_address = capsys.readouterr().out.strip()
    assert len(initial_address) == 71
    plan.write_text(
        json.dumps(
            {
                "outputs": {"host/replacement.md": "compiled.md"},
                "distribution": "distribution.tar",
            }
        )
    )
    source = lock.parent / "declarations" / "process-core.yaml"
    old = source.read_text()
    source.write_text(old.replace("reader-facing purpose", "reader-facing goal"))
    result = _invoke(lock.parent, "declarations/acquisition.yaml")
    assert result.exit_code == 0, result.stderr
    lock.write_bytes(result.stdout_bytes)

    successor = initial.with_name("successor")
    successor_args = [
        *args,
        "--bundle",
        str(successor),
        "--predecessor-bundle",
        str(initial),
        "--predecessor",
        initial_address,
    ]
    assert main(successor_args) == 0
    address = capsys.readouterr().out.strip()
    store = successor / "blobs" / "sha256"

    def read(digest: str) -> bytes:
        """Read exact bytes from the successor store."""
        return (store / digest.removeprefix("sha256:")).read_bytes()

    capsule = json.loads(read(address))
    review = json.loads(read(capsule["review-packet"]))
    diff = json.loads(read(review["semantics"]["differences"]))
    assert capsule["predecessor"] == initial_address
    assert capsule["initial-baseline"] is None
    assert capsule["managed-targets"]["host/new.md"] is None
    assert capsule["managed-targets"]["host/old.md"] is None
    assert [(row["id"], row["change"]) for row in diff] == [
        ("oikos/process-core", "modified")
    ]
    assert review["acquisition"]["baseline"] != review["acquisition"]["candidate"]
    verify_bundle(successor, address)
    verify_bundle(successor, initial_address)

    after = initial.with_name("after")
    assert (
        main(
            [
                *args,
                "--bundle",
                str(after),
                "--predecessor-bundle",
                str(successor),
                "--predecessor",
                address,
            ]
        )
        == 0
    )
    after_address = capsys.readouterr().out.strip()
    verify_bundle(after, after_address)
    verify_bundle(after, initial_address)


def test_prepare_rejects_wrong_predecessor(
    setup_release: ReleaseFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    args, plan, initial, _ = setup_release
    assert main([*args, "--bundle", str(initial)]) == 0
    capsys.readouterr()
    plan.write_text(json.dumps({"outputs": {}, "distribution": "distribution.tar"}))
    output = initial.with_name("successor")
    with pytest.raises(SystemExit) as error:
        main(
            [
                *args,
                "--bundle",
                str(output),
                "--predecessor-bundle",
                str(initial),
                "--predecessor",
                "sha256:" + "0" * 64,
            ]
        )
    assert error.value.code == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert "Preparation failed" in captured.err
    assert not output.exists()
