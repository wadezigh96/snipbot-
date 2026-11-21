import unittest

from agent.pumpfun.run_agent import backoff_seconds, validate_telegram_config


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

    def test_telegram_config_allows_both_empty(self):
        validate_telegram_config({})

    def test_telegram_config_allows_both_present(self):
        validate_telegram_config({"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "123"})

    def test_telegram_config_rejects_partial_secret_pair(self):
        for values in (
            {"TELEGRAM_BOT_TOKEN": "token"},
            {"TELEGRAM_CHAT_ID": "123"},
            {"TELEGRAM_BOT_TOKEN": "  ", "TELEGRAM_CHAT_ID": "123"},
        ):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    validate_telegram_config(values)


if __name__ == "__main__":
    unittest.main()
