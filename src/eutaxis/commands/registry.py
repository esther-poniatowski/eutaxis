"""Persistent record of installed commands.

The registry is a JSON file at ``<state_dir>/installed-commands.json``.
It is the source of truth for ``uninstall`` and ``diff`` and survives
across CLI invocations.

Robustness: writes are atomic (``os.replace`` from a sibling ``.tmp``
file) and serialised under a POSIX advisory file lock so concurrent
``eutaxis commands install`` invocations cannot lose each other's
records. A corrupted registry surfaces as ``RegistryCorruptedError``
with the path; the user can remove the file to rebuild from scratch.
"""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .exceptions import CommandError
from .models import InstallRecord


class RegistryCorruptedError(CommandError):
    """Raised when the on-disk registry cannot be decoded as JSON."""


class Registry:
    """State for installed commands.

    Each public mutating operation acquires an advisory file lock on a
    sibling ``.lock`` file before reading, mutating, and writing the
    JSON state. Writes go to a sibling ``.tmp`` and are committed with
    ``os.replace`` so a crash between truncate and write cannot leave a
    half-written file.
    """

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.path = state_dir / "installed-commands.json"
        self.lock_path = state_dir / "installed-commands.lock"
        self.deployment_lock_path = state_dir / "skill-deployment.lock"
        self._pending_records: list[InstallRecord] | None = None

    def load(self) -> list[InstallRecord]:
        """Return all install records currently on disk."""
        if self._pending_records is not None:
            return list(self._pending_records)
        if not self.path.is_file():
            return []
        raw_text = self.path.read_text(encoding="utf-8")
        if not raw_text.strip():
            return []
        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise RegistryCorruptedError(
                f"Registry at {self.path} is corrupted: {exc}. "
                "Remove the file to rebuild from on-disk artifacts."
            ) from exc
        if not isinstance(raw, list):
            raise RegistryCorruptedError(
                f"Registry at {self.path} must be a JSON list, got {type(raw).__name__}."
            )
        return [
            InstallRecord(
                name=row["name"],
                adapter=row["adapter"],
                scope=row["scope"],
                path=Path(row["path"]),
                content_hash=row["content_hash"],
                installed_at=row["installed_at"],
            )
            for row in raw
        ]

    def upsert(self, record: InstallRecord) -> None:
        """Insert or replace the record for the same deployment target."""
        if self._pending_records is not None:
            self._pending_records[:] = self._upserted(self._pending_records, record)
            return
        with self._locked():
            self._write(self._upserted(self.load(), record))

    def remove(
        self,
        *,
        name: str,
        adapter: str,
        scope: str,
        path: Path | None = None,
    ) -> InstallRecord | None:
        """Drop the matching record and return it, if any."""
        _require_project_path(scope, path)
        if self._pending_records is not None:
            kept, removed = self._removed(
                self._pending_records,
                name=name,
                adapter=adapter,
                scope=scope,
                path=path,
            )
            self._pending_records[:] = kept
            return removed
        with self._locked():
            kept, removed = self._removed(
                self.load(),
                name=name,
                adapter=adapter,
                scope=scope,
                path=path,
            )
            self._write(kept)
            return removed

    @contextmanager
    def transaction(self, *, externally_locked: bool = False) -> Iterator[None]:
        """Commit all registry mutations together or discard all of them.

        ``externally_locked`` is reserved for a transaction coordinator that
        already holds :attr:`lock_path` continuously. Ordinary callers must
        use the default so registry reads and writes remain serialized.
        """
        if self._pending_records is not None:
            raise RuntimeError("Registry transaction is already active")
        lock = nullcontext() if externally_locked else self._locked()
        with lock:
            records = self.load()
            self._pending_records = records
            try:
                yield
                self._write(records)
            finally:
                self._pending_records = None

    @contextmanager
    def deployment_locked(self) -> Iterator[None]:
        """Serialize every filesystem and registry mutation of Skills."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            self.deployment_lock_path,
            os.O_RDWR | os.O_CREAT,
            0o644,
        )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    @contextmanager
    def mutation_locked(self) -> Iterator[None]:
        """Hold the deployment and registry locks in canonical order."""
        with self.deployment_locked():
            with self._locked():
                yield

    def find(
        self,
        *,
        name: str,
        adapter: str,
        scope: str,
        path: Path | None = None,
    ) -> InstallRecord | None:
        """Return the matching record, if any."""
        _require_project_path(scope, path)
        for row in self.load():
            if (
                row.name == name
                and row.adapter == adapter
                and row.scope == scope
                and (scope != "project" or path is None or row.path == path)
            ):
                return row
        return None

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(
            self.lock_path,
            os.O_RDWR | os.O_CREAT,
            0o644,
        )
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _write(self, records: list[InstallRecord]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "name": row.name,
                "adapter": row.adapter,
                "scope": row.scope,
                "path": str(row.path),
                "content_hash": row.content_hash,
                "installed_at": row.installed_at,
            }
            for row in records
        ]
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, self.path)

    @staticmethod
    def _upserted(
        records: list[InstallRecord], record: InstallRecord
    ) -> list[InstallRecord]:
        kept = [
            row
            for row in records
            if not (
                row.name == record.name
                and row.adapter == record.adapter
                and row.scope == record.scope
                and (record.scope != "project" or row.path == record.path)
            )
        ]
        kept.append(record)
        return kept

    @staticmethod
    def _removed(
        records: list[InstallRecord],
        *,
        name: str,
        adapter: str,
        scope: str,
        path: Path | None,
    ) -> tuple[list[InstallRecord], InstallRecord | None]:
        kept: list[InstallRecord] = []
        removed: InstallRecord | None = None
        for row in records:
            if (
                row.name == name
                and row.adapter == adapter
                and row.scope == scope
                and (scope != "project" or path is None or row.path == path)
            ):
                removed = row
                continue
            kept.append(row)
        return kept, removed


def utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _require_project_path(scope: str, path: Path | None) -> None:
    if scope == "project" and path is None:
        raise CommandError("Project-scope registry operations require a path.")


def default_state_dir(home: Path | None = None) -> Path:
    """Return the default user-level state directory."""
    return (home or Path.home()) / ".eutaxis" / "state"
