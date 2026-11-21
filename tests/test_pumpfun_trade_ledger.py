import tempfile
import unittest
from pathlib import Path

from agent.pumpfun.trade_ledger import (
    DuplicateOrderError,
    InvalidTransitionError,
    TradeLedger,
)


class TradeLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "trades.sqlite3")
        self.ledger = TradeLedger(self.path)
        self.ledger.create_order("order-1", "mint-1", "buy", 0.25, created_at=100)

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def test_starts_prepared_and_same_order_creation_is_idempotent(self):
        first = self.ledger.get_order("order-1")
        again = self.ledger.create_order("order-1", "mint-1", "buy", 0.25, created_at=200)
        self.assertEqual(first, again)
        self.assertEqual(first["state"], "PREPARED")
        self.assertEqual(len(self.ledger.list_orders()), 1)

    def test_reusing_order_id_with_different_details_fails(self):
        with self.assertRaises(DuplicateOrderError):
            self.ledger.create_order("order-1", "other-mint", "buy", 0.25)

    def test_rejects_bad_order_input(self):
        for amount in (0, -1, float("nan"), float("inf"), True, "1"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                self.ledger.create_order("another", "mint-1", "buy", amount)
        with self.assertRaises(ValueError):
            self.ledger.create_order("another", "mint-1", "BUY", 1)

    def test_lifecycle_and_idempotent_state_retry(self):
        self.ledger.transition("order-1", "SIMULATED", evidence="simulation passed", updated_at=101)
        submitted = self.ledger.transition(
            "order-1", "SUBMITTED", tx_signature="signature-1", updated_at=102
        )
        self.assertEqual(submitted["state"], "SUBMITTED")
        self.assertEqual(
            self.ledger.transition("order-1", "SUBMITTED", tx_signature="signature-1"),
            submitted,
        )
        confirmed = self.ledger.transition(
            "order-1", "CONFIRMED",
            evidence="RPC confirmed signature at finalized commitment", updated_at=103,
        )
        self.assertEqual(confirmed["state"], "CONFIRMED")
        self.assertEqual(confirmed["version"], 3)

    def test_unknown_requires_signature_and_evidence_and_cannot_be_reprepared(self):
        self.ledger.transition("order-1", "SIMULATED", evidence="simulation passed")
        self.ledger.transition("order-1", "SUBMITTED", tx_signature="signature-unknown")
        with self.assertRaises(InvalidTransitionError):
            self.ledger.transition("order-1", "UNKNOWN")
        self.ledger.transition(
            "order-1", "UNKNOWN", evidence="submit timed out; outcome not yet reconciled"
        )
        with self.assertRaises(InvalidTransitionError):
            self.ledger.transition("order-1", "PREPARED")
        with self.assertRaises(InvalidTransitionError):
            self.ledger.transition("order-1", "CONFIRMED")
        resolved = self.ledger.transition(
            "order-1", "CONFIRMED", evidence="authoritative finalized transaction lookup"
        )
        self.assertEqual(resolved["state"], "CONFIRMED")

    def test_submitted_failure_requires_authoritative_evidence(self):
        self.ledger.transition("order-1", "SIMULATED", evidence="simulation passed")
        self.ledger.transition("order-1", "SUBMITTED", tx_signature="signature-failed")
        with self.assertRaises(InvalidTransitionError):
            self.ledger.transition("order-1", "FAILED", error="maybe failed")
        failed = self.ledger.transition(
            "order-1", "FAILED", evidence="authoritative transaction status: failed",
            error="transaction failed on chain",
        )
        self.assertEqual(failed["state"], "FAILED")

    def test_duplicate_transaction_signature_is_rejected(self):
        self.ledger.transition("order-1", "SIMULATED", evidence="simulation passed")
        self.ledger.transition("order-1", "SUBMITTED", tx_signature="signature-unique")
        self.ledger.create_order("order-2", "mint-2", "sell", 1)
        self.ledger.transition("order-2", "SIMULATED", evidence="simulation passed")
        with self.assertRaises(Exception):
            self.ledger.transition("order-2", "SUBMITTED", tx_signature="signature-unique")

    def test_terminal_states_cannot_be_changed(self):
        self.ledger.transition("order-1", "FAILED", error="cancelled before submit")
        with self.assertRaises(InvalidTransitionError):
            self.ledger.transition("order-1", "SIMULATED", evidence="retry")

    def test_order_survives_process_restart(self):
        self.ledger.transition("order-1", "SIMULATED", evidence="simulation passed")
        self.ledger.transition("order-1", "SUBMITTED", tx_signature="signature-persisted")
        self.ledger.close()
        self.ledger = TradeLedger(self.path)
        row = self.ledger.get_order("order-1")
        self.assertEqual(row["state"], "SUBMITTED")
        self.assertEqual(row["tx_signature"], "signature-persisted")
        self.assertEqual(row["version"], 2)

    def test_unknown_order_and_invalid_limit(self):
        self.assertIsNone(self.ledger.get_order("not-here"))
        with self.assertRaises(KeyError):
            self.ledger.transition("not-here", "SIMULATED")
        for limit in (True, 0, 1001, "10"):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.ledger.list_orders(limit)


if __name__ == "__main__":
    unittest.main()
