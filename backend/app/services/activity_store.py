"""Unified Activity History.

Records one lightweight metadata event per completed agent operation across
Knowledge, Automation, and Performance. Events describe *that* something ran and
how it ended -- never the agent's output. No answers, no drafted email bodies,
no chart data, no filesystem paths.

This is deliberately a local MVP backed by a JSON file, not a database. The
store is a small class rather than an abstraction layer so it can be swapped
for persistent storage later without touching the callers, which depend only on
:func:`record_activity` and :func:`list_activities`.

Write concurrency is handled with a process-local lock plus an atomic
write-to-temp-then-replace. That is sufficient for a single-process local
deployment and avoids pulling in external infrastructure.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Cap on retained records. The file is append-mostly and read by a dashboard,
#: so an unbounded file would grow without limit on a long-running process.
MAX_RECORDS = 500

_write_lock = threading.Lock()


def default_history_path() -> Path:
    """Return the default activity history file path.

    Returns:
        An absolute path under the backend directory, resolved from this file
        so it does not depend on the process working directory.
    """
    backend_root = Path(__file__).resolve().parents[2]

    return backend_root / "activity_history" / "data" / "activity_history.json"


class ActivityStore:
    """JSON-file backed store for activity records.

    Attributes:
        path: The history file. Its parent directory is created on first write.
    """

    def __init__(self, path: Path | None = None) -> None:
        """Initialize the store.

        Args:
            path: History file path. Defaults to
                :func:`default_history_path`.
        """
        self.path = Path(path) if path else default_history_path()

    def read(self) -> list[dict[str, Any]]:
        """Read all records.

        A missing file is an empty history, not an error. A corrupt file is
        also treated as empty rather than breaking the endpoint, and is logged.

        Returns:
            Stored records, oldest first, as stored on disk.
        """
        try:
            if not self.path.is_file():
                return []

            raw = self.path.read_text(encoding="utf-8")

            if not raw.strip():
                return []

            parsed = json.loads(raw)

            if not isinstance(parsed, list):
                logger.warning("activity_history_not_a_list path=%s", self.path.name)

                return []

            return [r for r in parsed if isinstance(r, dict)]

        except json.JSONDecodeError:
            logger.warning("activity_history_corrupt path=%s", self.path.name)

            return []

        except OSError:
            logger.warning("activity_history_unreadable path=%s", self.path.name)

            return []

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        """Append one record and persist the file.

        The write is atomic: the new content goes to a temporary file in the
        same directory and is then moved over the target, so a reader never
        observes a half-written file.

        Args:
            record: The record to store.

        Returns:
            The stored record, including its assigned id.
        """
        with _write_lock:
            records = self.read()

            records.append(record)

            if len(records) > MAX_RECORDS:
                records = records[-MAX_RECORDS:]

            self._write(records)

        return record

    def _write(self, records: list[dict[str, Any]]) -> None:
        """Write records atomically.

        Args:
            records: The full set of records to persist.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = self.path.with_suffix(".json.tmp")

        temp_path.write_text(
            json.dumps(records, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        os.replace(temp_path, self.path)


_store: ActivityStore | None = None

#: Human-readable summary per (agent, operation). Kept here rather than at
#: each call site so the wording for an operation is defined once, and so a
#: caller cannot accidentally record an agent's output in a description.
_OPERATION_DESCRIPTIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("knowledge", "query"): (
        "Answered a knowledge question",
        "Knowledge question failed",
    ),
    ("knowledge", "ingest_document"): (
        "Ingested document",
        "Document ingestion failed",
    ),
    ("automation", "draft_action"): (
        "Drafted automation action",
        "Automation action draft failed",
    ),
    ("performance", "load_dataset"): (
        "Described dataset",
        "Dataset description failed",
    ),
    ("performance", "compute_kpis"): (
        "Calculated performance KPIs",
        "KPI calculation failed",
    ),
    ("performance", "compare_periods"): (
        "Compared reporting periods",
        "Period comparison failed",
    ),
    ("performance", "analyze"): (
        "Ran performance analysis",
        "Performance analysis failed",
    ),
    ("performance", "visualize"): (
        "Generated visualizations",
        "Visualization generation failed",
    ),
}

_FALLBACK_DESCRIPTIONS: dict[str, str] = {
    "completed": "Completed {operation}",
    "failed": "{operation} failed",
}


def describe_operation(agent: str, operation: str, status: str) -> str:
    """Return the summary wording for one operation outcome.

    The count in "Generated N visualizations" is the only value derived from a
    result, and it is an integer count, never content.

    Args:
        agent: Agent identifier.
        operation: Operation name.
        status: ``completed`` or ``failed``.

    Returns:
        A short human-readable description.
    """
    pair = _OPERATION_DESCRIPTIONS.get((agent, operation))

    if pair is not None:
        return pair[0] if status == "completed" else pair[1]

    template = _FALLBACK_DESCRIPTIONS.get(
        status,
        _FALLBACK_DESCRIPTIONS["completed"],
    )

    return template.format(operation=operation)


def get_store() -> ActivityStore:
    """Return the process-wide activity store.

    Returns:
        The shared store.
    """
    global _store

    if _store is None:
        _store = ActivityStore()

    return _store


def set_store(store: ActivityStore) -> None:
    """Install a store, typically a temporary one for tests.

    Args:
        store: The store to use for subsequent reads and writes.
    """
    global _store

    _store = store


def reset_store() -> None:
    """Restore the default store."""
    global _store

    _store = None


def record_activity(
    agent: str,
    operation: str,
    description: str,
    status: str,
    user_id: str | None = None,
    organization_id: str | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    """Record one completed agent operation.

    Callers pass metadata only. Nothing derived from an agent's output belongs
    here: an answer, a drafted body, or a chart count that would leak content is
    deliberately left out by the callers.

    Recording never raises. History is observability, so a write failure is
    logged and swallowed rather than allowed to fail the agent operation that
    triggered it.

    Args:
        agent: Agent identifier, e.g. ``knowledge``.
        operation: Operation name, e.g. ``query``.
        description: Short human-readable summary.
        status: ``completed`` or ``failed``.
        user_id: The user who performed the operation.
        organization_id: The organisation the operation was performed in.
        duration_ms: Optional elapsed time in milliseconds.

    Returns:
        The stored record, or an unsaved record if persistence failed.
    """
    record: dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "agent": agent,
        "operation": operation,
        "description": description,
        "status": status,
        "user_id": user_id,
        "organization_id": organization_id,
        "timestamp": datetime.now().astimezone().isoformat(),
    }

    if duration_ms is not None:
        record["duration_ms"] = duration_ms

    try:
        return get_store().append(record)

    except Exception:
        logger.exception(
            "activity_history_write_failed agent=%s operation=%s",
            agent,
            operation,
        )

        return record


def list_activities(
    limit: int = 100,
    user_id: str | None = None,
    organization_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return stored records, newest first.

    Args:
        limit: Maximum number of records to return.
        user_id: If provided, only return records for this user.
        organization_id: If provided, only return records for this organisation.

    Returns:
        Records ordered newest to oldest, filtered by user and/or organisation
        when specified.
    """
    records = get_store().read()

    # Filter by user_id and/or organization_id when specified
    if user_id is not None or organization_id is not None:
        records = [
            r
            for r in records
            if (user_id is None or r.get("user_id") == user_id)
            and (organization_id is None or r.get("organization_id") == organization_id)
        ]

    return list(reversed(records))[:limit]


def record_operation(
    agent: str,
    operation: str,
    status: str,
    duration_ms: int | None = None,
    description: str | None = None,
    user_id: str | None = None,
    organization_id: str | None = None,
) -> dict[str, Any]:
    """Record one agent operation using the canonical wording for it.

    Args:
        agent: Agent identifier.
        operation: Operation name.
        status: ``completed`` or ``failed``.
        duration_ms: Optional elapsed time in milliseconds.
        description: Override for the canonical wording. Used only where a
            count is genuinely useful, e.g. "Generated 39 visualizations".
        user_id: The user who performed the operation.
        organization_id: The organisation the operation was performed in.

    Returns:
        The stored record.
    """
    return record_activity(
        agent=agent,
        operation=operation,
        description=description or describe_operation(agent, operation, status),
        status=status,
        user_id=user_id,
        organization_id=organization_id,
        duration_ms=duration_ms,
    )
