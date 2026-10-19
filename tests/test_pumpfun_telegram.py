import unittest
from unittest.mock import patch

from agent.pumpfun.telegram import format_event_alert, send_telegram_message


class TelegramNotifierTests(unittest.IsolatedAsyncioTestCase):
    def test_alert_is_bounded_and_sanitizes_control_characters(self):
        message = format_event_alert(
            {
                "mint": "MintAddress123",
                "name": "Bad\nToken\x00Name",
                "symbol": "TEST",
                "event_type": "new_token",
                "score": 42,
            },
            {"status": "UNKNOWN", "reason": "rpc unavailable"},
            {"status": "WATCH_ONLY"},
        )
        self.assertIn("Bad Token Name", message)
        self.assertIn("Execution: DISABLED", message)
        self.assertIn("not a buy signal", message)
        self.assertLessEqual(len(message), 3500)
        self.assertNotIn("\x00", message)

    async def test_missing_credentials_disables_notifications(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(await send_telegram_message("test"), "disabled")

    async def test_empty_message_fails_closed(self):
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "123"}):
            self.assertEqual(await send_telegram_message(" "), "failed")


    async def test_successful_send_returns_only_status(self):
        import sys
        import types

        class FakeResponse:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def json(self, content_type=None):
                return {"ok": True}

        class FakeSession:
            def __init__(self, **kwargs):
                self.url = None
                self.payload = None

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            def post(self, url, json):
                self.url = url
                self.payload = json
                return FakeResponse()

        fake_aiohttp = types.SimpleNamespace(
            ClientTimeout=lambda **kwargs: object(),
            ClientSession=FakeSession,
        )
        with patch.dict("os.environ", {
            "TELEGRAM_BOT_TOKEN": "test-secret-token",
            "TELEGRAM_CHAT_ID": "12345",
        }), patch.dict(sys.modules, {"aiohttp": fake_aiohttp}):
            self.assertEqual(await send_telegram_message("safe test alert"), "sent")


if __name__ == "__main__":
    unittest.main()
