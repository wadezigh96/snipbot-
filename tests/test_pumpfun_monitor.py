import unittest

from agent.pumpfun.run_agent import backoff_seconds


class MonitorBackoffTests(unittest.TestCase):
    def test_exponential_backoff_is_capped(self):
        self.assertEqual(backoff_seconds(1), 2)
        self.assertEqual(backoff_seconds(2), 4)
        self.assertEqual(backoff_seconds(3), 8)
        self.assertEqual(backoff_seconds(20), 60)

    def test_rejects_invalid_attempt(self):
        for value in (0, -1, True, 1.5, "2"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    backoff_seconds(value)

    def test_rejects_invalid_bounds(self):
        with self.assertRaises(ValueError):
            backoff_seconds(1, base=0)
        with self.assertRaises(ValueError):
            backoff_seconds(1, maximum=0)


if __name__ == "__main__":
    unittest.main()
