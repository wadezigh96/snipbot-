import math
import tempfile
import unittest
from pathlib import Path

from agent.pumpfun.store import ObservationStore


class ObservationStoreTests(unittest.TestCase):
    def test_persists_and_deduplicates_across_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "monitor.sqlite3")
            event = {"mint": "mint123", "event_type": "new_token", "score": 10}
            advisor = {"status": "WATCH_ONLY", "score": 0}
            with ObservationStore(path) as store:
                self.assertTrue(store.record(event, advisor, observed_at=100))
                self.assertFalse(store.record(event, advisor, observed_at=101))
            with ObservationStore(path) as store:
                rows = store.list_recent()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["observations_count"], 2)
                self.assertEqual(rows[0]["first_seen_at"], 100)
                self.assertEqual(rows[0]["last_seen_at"], 101)

    def test_out_of_order_event_does_not_move_last_seen_backwards(self):
        with ObservationStore(":memory:") as store:
            event = {"mint": "mint123", "event_type": "new_token"}
            self.assertTrue(store.record(event, {}, observed_at=100))
            self.assertFalse(store.record(event, {}, observed_at=90))
            row = store.list_recent()[0]
            self.assertEqual(row["first_seen_at"], 100)
            self.assertEqual(row["last_seen_at"], 100)
            self.assertEqual(row["observations_count"], 2)

    def test_rejects_nonfinite_negative_and_malformed_timestamps(self):
        with ObservationStore(":memory:") as store:
            event = {"mint": "mint123", "event_type": "new_token"}
            for value in (float("nan"), float("inf"), float("-inf"), -1, True, "100"):
                with self.subTest(value=value):
                    with self.assertRaises(ValueError):
                        store.record(event, {}, observed_at=value)

    def test_rejects_non_object_event_and_advisor(self):
        with ObservationStore(":memory:") as store:
            with self.assertRaises(ValueError):
                store.record([], {})
            with self.assertRaises(ValueError):
                store.record({"mint": "mint123", "event_type": "new_token"}, [])

    def test_creation_and_migration_are_separate_events(self):
        with ObservationStore(":memory:") as store:
            self.assertTrue(store.record({"mint": "mint123", "event_type": "new_token"}, {}, observed_at=1))
            self.assertTrue(store.record({"mint": "mint123", "event_type": "migration"}, {}, observed_at=2))
            self.assertEqual(len(store.list_recent()), 2)

    def test_rejects_invalid_event(self):
        with ObservationStore(":memory:") as store:
            with self.assertRaises(ValueError):
                store.record({"event_type": "new_token"}, {})

    def test_rejects_invalid_limit(self):
        with ObservationStore(":memory:") as store:
            for limit in (True, 0, 1001, 1.5, "10"):
                with self.subTest(limit=limit):
                    with self.assertRaises(ValueError):
                        store.list_recent(limit)


if __name__ == "__main__":
    unittest.main()
