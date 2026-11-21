"""Activate, recover, or roll back a draft release under operator exclusion."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from jsonschema.exceptions import ValidationError

from eutaxis.commands.exceptions import CommandError
from eutaxis.declarations.canonical_json import jcs_bytes
from eutaxis.declarations.exceptions import AcquisitionContractError, ByteCarrierError

from .approve_release_capsule import ExpectedActive, _check_approval_file
from .release_activation_store import (
    Head,
    TargetTransition,
    activation_record,
    consumer_bytes,
    locked_store,
    marker_digest,
    publish,
    publish_once,
    read_head,
    read_record,
    read_release,
    read_stored_release,
    record_path,
    retain_release,
    sequence_paths,
    stage_file,
    sync_directory,
    sync_target,
    target_transition,
    update_target,
    validate_targets,
)
from .verify_release_capsule import _digest


class ActivationError(ValueError):
    """Report an activation or recovery outcome that needs operator attention."""


def _intent(record_digest: str, transition: TargetTransition) -> bytes:
    """Bind the pending marker to the exact transition and target coverage."""
    return jcs_bytes(
        {
            "_schema": "eutaxis:declaration-pending@1",
            "activation-record": record_digest,
            "targets": sorted(transition.targets),
        }
    )


def _remove_pending(path: Path) -> None:
    """Only clear a resolved intent and flush its parent directory."""
    path.unlink()
    sync_directory(path.parent)


def _restore(targets: Path, transition: TargetTransition) -> None:
    """Restore only target states attributable to the interrupted transition."""
    conflicts = []
    for name, selected in sorted(transition.targets.items()):
        baseline = transition.baseline.get(name)
        actual = consumer_bytes(targets, name)
        if actual != baseline:
            if actual != selected:
                conflicts.append(name)
                continue
            update_target(targets, name, selected, baseline)
        sync_target(targets, name)
    if conflicts:
        raise ActivationError(f"Concurrent edits preserved at: {', '.join(conflicts)}")
    for name in transition.targets:
        if consumer_bytes(targets, name) != transition.baseline.get(name):
            raise ActivationError(f"Consumer still differs from baseline: {name}")


def _recover_pending(store: Path, targets: Path, head: Head) -> str:
    """Resolve the retained intent against the verified committed sequence."""
    pending = sequence_paths(store, "pending")
    if not pending:
        return "No pending release"
    if len(pending) != 1:
        raise ActivationError("Release store contains multiple pending records")
    number, path = next(iter(pending.items()))
    intent = read_record(store, "intent", marker_digest(path))
    record_digest = intent.get("activation-record")
    if not isinstance(record_digest, str):
        raise ActivationError("Invalid pending activation digest")
    record = read_record(store, "record", record_digest)
    selected = record.get("selected-release")
    if not isinstance(selected, str):
        raise ActivationError("Invalid pending release digest")
    prior = record.get("expected-active")
    if prior is not None and not isinstance(prior, str):
        raise ActivationError("Invalid pending baseline digest")
    active = None if prior is None else read_stored_release(store, prior)
    release = read_stored_release(store, selected)
    transition = target_transition(active, release)
    validate_targets(set(transition.targets))
    if jcs_bytes(intent) != _intent(record_digest, transition):
        raise ActivationError("Pending intent differs from the selected release")

    if number == head.active.record and record_digest == head.record_digest:
        sync_directory(store)
        result = f"Cleared committed intent for record {number}"
    elif number == head.next_number and jcs_bytes(record) == jcs_bytes(
        activation_record(head, selected)
    ):
        _restore(targets, transition)
        result = f"Restored the baseline for record {number}"
    else:
        raise ActivationError("Pending intent does not belong to the current history")
    _remove_pending(path)
    return result


def recover_release(store: Path, targets: Path) -> str:
    """Restore an interrupted release or clear a committed intent."""
    store, targets = store.absolute(), targets.absolute()
    with locked_store(store, targets):
        return _recover_pending(store, targets, read_head(store))


def release_status(store: Path, targets: Path) -> str:
    """Report the verified active release and any pending sequence."""
    store, targets = store.absolute(), targets.absolute()
    with locked_store(store, targets):
        active = read_head(store).active
        status = (
            "No active release"
            if active.record is None
            else f"Active {active.release} at record {active.record}"
        )
        pending = sequence_paths(store, "pending")
        if pending:
            status += "\nPending records: " + ", ".join(map(str, sorted(pending)))
        return status


def _ready_head(store: Path) -> Head:
    """Reject new transactions while an earlier intent remains unresolved."""
    head = read_head(store)
    if sequence_paths(store, "pending"):
        raise ActivationError("Release store has a pending intent. Run recover first")
    return head


def _check_baseline(targets: Path, transition: TargetTransition) -> None:
    """Require every affected file to match the reviewed baseline."""
    validate_targets(set(transition.targets))
    for name in transition.targets:
        if consumer_bytes(targets, name) != transition.baseline.get(name):
            raise ActivationError(
                f"Consumer differs from the reviewed baseline: {name}"
            )


def activate_release(
    store: Path, targets: Path, bundle: Path, address: str, approval: Path
) -> int:
    """Activate the reviewed bytes and return the committed record number."""
    store, targets = store.absolute(), targets.absolute()
    with locked_store(store, targets) as binding:
        head = _ready_head(store)
        _check_approval_file(approval, bundle, address, head.active)
        release = read_release(bundle, address)
        transition = TargetTransition(release.baseline, release.targets)
        _check_baseline(targets, transition)
        publish_once(store / "target-root", binding)
        retain_release(store, release)
        return _commit(store, targets, head, address, transition)


def rollback_release(
    store: Path, targets: Path, expected: ExpectedActive
) -> tuple[int, str]:
    """Append a transition to the predecessor of the explicitly pinned release."""
    store, targets = store.absolute(), targets.absolute()
    with locked_store(store, targets):
        head = _ready_head(store)
        if head.active != expected:
            raise ActivationError(
                "Rollback expected active state differs from the store"
            )
        if head.active.release is None:
            raise ActivationError("No active release to roll back")
        active = read_stored_release(store, head.active.release)
        address = active.predecessor
        if address is None:
            raise ActivationError("The active release has no predecessor")
        selected = read_stored_release(store, address)
        transition = target_transition(active, selected)
        _check_baseline(targets, transition)
        return _commit(store, targets, head, address, transition), address


def _commit(
    store: Path, targets: Path, head: Head, address: str, transition: TargetTransition
) -> int:
    """Apply a validated transition at the next append-only sequence position."""
    record = jcs_bytes(activation_record(head, address))
    digest = _digest(record)
    publish_once(record_path(store, "record", digest), record)
    intent = _intent(digest, transition)
    intent_digest = _digest(intent)
    publish_once(record_path(store, "intent", intent_digest), intent)
    number = head.next_number
    pending = store / f"pending-{number}"
    marker = store / f"commit-{number}"
    linked = False
    try:
        publish(pending, jcs_bytes(intent_digest))
        for name, selected in sorted(transition.targets.items()):
            update_target(targets, name, transition.baseline.get(name), selected)
        for name, selected in transition.targets.items():
            if consumer_bytes(targets, name) != selected:
                raise ActivationError(
                    f"Consumer differs from the selected release: {name}"
                )

        with stage_file(marker, jcs_bytes(digest)) as temporary:
            os.link(temporary, marker, follow_symlinks=False)
            linked = True
            if marker_digest(marker) != digest:
                raise ActivationError(f"Commit marker differs at record {number}")
            sync_directory(store)
        _remove_pending(pending)
    except BaseException as error:
        if linked or marker.exists():
            raise ActivationError(
                f"Record {number} may have committed. Inspect or recover the store: {error}"
            ) from error
        if pending.exists():
            try:
                _recover_pending(store, targets, head)
            except Exception as recovery_error:
                raise ActivationError(
                    f"Record {number} did not commit. Pending recovery: {recovery_error}"
                ) from error
        raise
    return number


def main(argv: list[str] | None = None) -> int:
    """Run a draft release operation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--targets", required=True, type=Path)
    actions = parser.add_subparsers(dest="action", required=True)
    activate = actions.add_parser("activate", help="Apply a reviewed bundle")
    activate.add_argument("bundle", type=Path)
    activate.add_argument("address")
    activate.add_argument("--approval", required=True, type=Path)
    actions.add_parser("recover", help="Resolve a pending update")
    actions.add_parser("status", help="Check the active release and pending records")
    rollback = actions.add_parser(
        "rollback", help="Restore the active release's predecessor"
    )
    rollback.add_argument("--expect-record", required=True, type=int)
    rollback.add_argument("--expect-active", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "status":
            print(release_status(args.store, args.targets))
        elif args.action == "recover":
            print(recover_release(args.store, args.targets))
        elif args.action == "rollback":
            record, address = rollback_release(
                args.store,
                args.targets,
                ExpectedActive(args.expect_record, args.expect_active),
            )
            print(f"Rolled back to {address} at record {record}")
        else:
            record = activate_release(
                args.store, args.targets, args.bundle, args.address, args.approval
            )
            print(f"Activated {args.address} at record {record}")
    except (
        AcquisitionContractError,
        ByteCarrierError,
        CommandError,
        OSError,
        ValidationError,
        ValueError,
    ) as error:
        parser.exit(1, f"Release operation failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
