"""Persistent, fail-closed trade lifecycle ledger.

This module records lifecycle state only. It does not create, sign, simulate,
submit, or broadcast transactions and is deliberately not wired into the monitor.
"""
from __future__ import annotations

import math
import os
import sqlite3
import time
from pathlib import Path
from typing import Any


STATES = frozenset({
    "PREPARED", "SIMULATED", "SUBMITTED", "CONFIRMED", "FAILED", "UNKNOWN"
})
_TRANSITIONS = {
    "PREPARED": frozenset({"SIMULATED", "FAILED"}),
    "SIMULATED": frozenset({"SUBMITTED", "FAILED"}),
    "SUBMITTED": frozenset({"CONFIRMED", "FAILED", "UNKNOWN"}),
    # UNKNOWN can only be resolved by authoritative reconciliation. It must
    # never be reset to PREPARED, because that could duplicate a live order.
    "UNKNOWN": frozenset({"CONFIRMED", "FAILED"}),
    "CONFIRMED": frozenset(),
    "FAILED": frozenset(),
}


class LedgerError(Exception):
    """Base class for ledger validation and lifecycle errors."""


class DuplicateOrderError(LedgerError):
    """An order ID was reused with different order details."""


class InvalidTransitionError(LedgerError):
    """A requested state change is unsafe or not allowed."""


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _timestamp(value: float | None) -> float:
    if value is None:
        return time.time()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("timestamp must be a finite non-negative number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError("timestamp must be a finite non-negative number")
    return result


class TradeLedger:
    """SQLite lifecycle ledger with unique order IDs and transaction signatures."""

    def __init__(self, path: str | os.PathLike[str] = "data/pumpfun_trades.sqlite3"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, timeout=10.0)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout=10000")
        if self.path != ":memory:":
            self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS trade_orders (
                client_order_id TEXT PRIMARY KEY,
                mint TEXT NOT NULL,
                side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
                amount REAL NOT NULL CHECK (amount > 0),
                state TEXT NOT NULL CHECK (
                    state IN ('PREPARED', 'SIMULATED', 'SUBMITTED',
                              'CONFIRMED', 'FAILED', 'UNKNOWN')
                ),
                tx_signature TEXT UNIQUE,
                evidence TEXT,
                error TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                version INTEGER NOT NULL DEFAULT 0
            )
        """)
        self._db.commit()

    def create_order(
        self, client_order_id: str, mint: str, side: str, amount: float,
        *, created_at: float | None = None,
    ) -> dict[str, Any]:
        order_id = _nonempty(client_order_id, "client_order_id")
        token_mint = _nonempty(mint, "mint")
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise ValueError("amount must be a finite positive number")
        quantity = float(amount)
        if not math.isfinite(quantity) or quantity <= 0:
            raise ValueError("amount must be a finite positive number")
        now = _timestamp(created_at)

        with self._db:
            row = self._db.execute(
                "SELECT * FROM trade_orders WHERE client_order_id=?", (order_id,)
            ).fetchone()
            if row is not None:
                same = (
                    row["mint"] == token_mint and row["side"] == side
                    and row["amount"] == quantity
                )
                if not same:
                    raise DuplicateOrderError(
                        "client_order_id already exists with different order details"
                    )
                return dict(row)
            self._db.execute(
                """INSERT INTO trade_orders
                   (client_order_id, mint, side, amount, state, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'PREPARED', ?, ?)""",
                (order_id, token_mint, side, quantity, now, now),
            )
            row = self._db.execute(
                "SELECT * FROM trade_orders WHERE client_order_id=?", (order_id,)
            ).fetchone()
            return dict(row)

    def transition(
        self, client_order_id: str, new_state: str, *,
        tx_signature: str | None = None,
        evidence: str | None = None,
        error: str | None = None,
        updated_at: float | None = None,
    ) -> dict[str, Any]:
        order_id = _nonempty(client_order_id, "client_order_id")
        if new_state not in STATES:
            raise ValueError("new_state is not a supported ledger state")
        now = _timestamp(updated_at)
        if tx_signature is not None:
            tx_signature = _nonempty(tx_signature, "tx_signature")
        if evidence is not None:
            evidence = _nonempty(evidence, "evidence")
        if error is not None:
            error = _nonempty(error, "error")

        with self._db:
            row = self._db.execute(
                "SELECT * FROM trade_orders WHERE client_order_id=?", (order_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown client_order_id: {order_id}")

            current = row["state"]
            # A retry of the same state update is idempotent; never overwrite
            # the original signature/evidence as part of that retry.
            if current == new_state:
                if tx_signature is not None and tx_signature != row["tx_signature"]:
                    raise InvalidTransitionError("cannot change a recorded transaction signature")
                if evidence is not None and evidence != row["evidence"]:
                    raise InvalidTransitionError("cannot replace recorded evidence")
                return dict(row)

            if new_state not in _TRANSITIONS[current]:
                raise InvalidTransitionError(f"transition {current} -> {new_state} is not allowed")

            if new_state == "SUBMITTED" and not tx_signature:
                raise InvalidTransitionError("SUBMITTED requires a transaction signature")
            if current in ("SUBMITTED", "UNKNOWN") and new_state in ("CONFIRMED", "FAILED"):
                if not evidence:
                    raise InvalidTransitionError(
                        f"{new_state} from {current} requires authoritative reconciliation evidence"
                    )
            if new_state == "UNKNOWN" and not evidence:
                raise InvalidTransitionError("UNKNOWN requires a reason/evidence")
            if new_state == "FAILED" and not error and not evidence:
                raise InvalidTransitionError("FAILED requires an error or evidence")

            signature = row["tx_signature"]
            if tx_signature is not None:
                if signature is not None and signature != tx_signature:
                    raise InvalidTransitionError("cannot replace a recorded transaction signature")
                signature = tx_signature
            if new_state in ("SUBMITTED", "UNKNOWN", "CONFIRMED") and not signature:
                raise InvalidTransitionError(f"{new_state} requires a recorded transaction signature")

            self._db.execute(
                """UPDATE trade_orders
                   SET state=?, tx_signature=?, evidence=COALESCE(?, evidence),
                       error=COALESCE(?, error), updated_at=?, version=version+1
                   WHERE client_order_id=? AND state=?""",
                (new_state, signature, evidence, error, now, order_id, current),
            )
            updated = self._db.execute(
                "SELECT * FROM trade_orders WHERE client_order_id=?", (order_id,)
            ).fetchone()
            if updated is None or updated["state"] != new_state:
                raise InvalidTransitionError("concurrent state change detected; re-read before retrying")
            return dict(updated)

    def get_order(self, client_order_id: str) -> dict[str, Any] | None:
        order_id = _nonempty(client_order_id, "client_order_id")
        row = self._db.execute(
            "SELECT * FROM trade_orders WHERE client_order_id=?", (order_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def list_orders(self, limit: int = 100) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit must be an integer from 1 to 1000")
        rows = self._db.execute(
            "SELECT * FROM trade_orders ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "TradeLedger":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
