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
            with self.assertRaises(ValueError):
                store.list_recent(True)


if __name__ == "__main__":
    unittest.main()
