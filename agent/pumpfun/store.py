"""Persistent SQLite observation store for read-only PumpFun monitoring."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any


class ObservationStore:
    """Durably deduplicate observed mint/event pairs across process restarts."""

    def __init__(self, path: str | os.PathLike[str] = "data/pumpfun_monitor.sqlite3"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS observations (
                mint TEXT NOT NULL,
                event_type TEXT NOT NULL,
                first_seen_at REAL NOT NULL,
                last_seen_at REAL NOT NULL,
                observations_count INTEGER NOT NULL DEFAULT 1,
                event_json TEXT NOT NULL,
                advisor_json TEXT NOT NULL,
                PRIMARY KEY (mint, event_type)
            )
            """
        )
        self._db.commit()

    def record(
        self,
        event: dict[str, Any],
        advisor: dict[str, Any],
        *,
        observed_at: float | None = None,
    ) -> bool:
        """Store/update an event; return True only the first time this pair appears."""
        mint = event.get("mint")
        event_type = event.get("event_type")
        if not isinstance(mint, str) or not mint or not isinstance(event_type, str) or not event_type:
            raise ValueError("event must contain non-empty mint and event_type")
        now = float(observed_at if observed_at is not None else time.time())
        if now < 0:
            raise ValueError("observed_at must be non-negative")
        event_json = json.dumps(event, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        advisor_json = json.dumps(advisor, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        cursor = self._db.execute(
            """
            INSERT INTO observations (
                mint, event_type, first_seen_at, last_seen_at,
                observations_count, event_json, advisor_json
            ) VALUES (?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(mint, event_type) DO UPDATE SET
                last_seen_at = excluded.last_seen_at,
                observations_count = observations.observations_count + 1,
                event_json = excluded.event_json,
                advisor_json = excluded.advisor_json
            """,
            (mint, event_type, now, now, event_json, advisor_json),
        )
        self._db.commit()
        return cursor.rowcount == 1 and self._was_inserted(mint, event_type, now)

    def _was_inserted(self, mint: str, event_type: str, now: float) -> bool:
        row = self._db.execute(
            "SELECT first_seen_at, observations_count FROM observations WHERE mint=? AND event_type=?",
            (mint, event_type),
        ).fetchone()
        return bool(row and row[0] == now and row[1] == 1)

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit must be an integer from 1 to 1000")
        rows = self._db.execute(
            """
            SELECT mint, event_type, first_seen_at, last_seen_at,
                   observations_count, event_json, advisor_json
            FROM observations ORDER BY last_seen_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "mint": row[0],
                "event_type": row[1],
                "first_seen_at": row[2],
                "last_seen_at": row[3],
                "observations_count": row[4],
                "event": json.loads(row[5]),
                "advisor": json.loads(row[6]),
            }
            for row in rows
        ]

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "ObservationStore":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
