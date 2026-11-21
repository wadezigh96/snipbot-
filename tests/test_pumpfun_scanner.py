import asyncio
import sys
import types
import unittest
from unittest.mock import patch

from agent.pumpfun.scanner import build_data_ws_url, normalize_event, score_event, stream_events


MINT = "So11111111111111111111111111111111111111112"
TRADER = "11111111111111111111111111111111"


class PumpFunScannerTests(unittest.TestCase):
    def test_builds_encoded_websocket_url(self):
        url = build_data_ws_url("example-secret/key")
        self.assertTrue(url.startswith("wss://pumpportal.fun/api/data?"))
        self.assertIn("api-key=example-secret%2Fkey", url)

    def test_missing_api_key_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, "PUMPPORTAL_API_KEY"):
            build_data_ws_url("")

    def test_normalizes_valid_new_token_event_as_watch_only(self):
        event = normalize_event({
            "txType": "create",
            "mint": MINT,
            "name": "Test Token",
            "symbol": "TEST",
            "traderPublicKey": TRADER,
            "bondingCurveKey": TRADER,
            "marketCapSol": 12.5,
            "vSolInBondingCurve": 20,
            "vTokensInBondingCurve": 1000,
            "initialBuy": 2,
        }, observed_at=123.0)
        self.assertIsNotNone(event)
        self.assertEqual(event.mint, MINT)
        self.assertEqual(event.event_type, "new_token")
        self.assertEqual(event.observed_at, 123.0)
        self.assertEqual(event.decision, "WATCH_ONLY")
        self.assertGreater(event.score, 0)
        self.assertIn("not_a_trade_signal_missing_liquidity_holder_and_authority_checks", event.reasons)

    def test_rejects_malformed_observation_timestamps(self):
        for timestamp in (True, False, "123", float("nan"), float("inf"), float("-inf"), -1, None):
            if timestamp is None:
                continue
            with self.subTest(timestamp=timestamp):
                self.assertIsNone(normalize_event({"txType": "create", "mint": MINT}, observed_at=timestamp))

    def test_normalizes_migration_event(self):
        event = normalize_event({"txType": "migration", "mint": MINT}, observed_at=5)
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, "migration")
        self.assertEqual(event.decision, "WATCH_ONLY")

    def test_rejects_invalid_mint(self):
        self.assertIsNone(normalize_event({"txType": "create", "mint": "not-a-mint"}))

    def test_ignores_trade_noise(self):
        self.assertIsNone(normalize_event({"txType": "buy", "mint": MINT}))

    def test_rejects_non_object_payload(self):
        self.assertIsNone(normalize_event(["bad", "payload"]))

    def test_nonfinite_numbers_are_ignored(self):
        event = normalize_event({
            "txType": "create",
            "mint": MINT,
            "marketCapSol": float("nan"),
            "vSolInBondingCurve": float("inf"),
        })
        self.assertIsNotNone(event)
        self.assertIsNone(event.market_cap_sol)
        self.assertIsNone(event.v_sol_in_curve)

    def test_missing_risk_data_never_becomes_buy_recommendation(self):
        score, reasons = score_event(
            event_type="new_token",
            market_cap_sol=None,
            v_sol_in_curve=None,
            v_tokens_in_curve=None,
            initial_buy=None,
            name=None,
            symbol=None,
        )
        self.assertEqual(score, 0)
        self.assertTrue(any("not_a_trade_signal" in reason for reason in reasons))


    def test_websocket_close_reports_health_and_raises_for_reconnect(self):
        class FakeWebSocket:
            def __init__(self):
                self.sent = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def send_json(self, value):
                self.sent.append(value)

            async def receive(self):
                return types.SimpleNamespace(type="CLOSED")

        class FakeSession:
            def __init__(self, **kwargs):
                self.websocket = FakeWebSocket()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            def ws_connect(self, *args, **kwargs):
                return self.websocket

        fake_aiohttp = types.SimpleNamespace(
            ClientTimeout=lambda **kwargs: object(),
            ClientSession=FakeSession,
            WSMsgType=types.SimpleNamespace(TEXT="TEXT", CLOSED="CLOSED", CLOSE="CLOSE", ERROR="ERROR"),
        )
        statuses = []

        async def run():
            with patch.dict(sys.modules, {"aiohttp": fake_aiohttp}):
                async for _event in stream_events(
                    seconds=1,
                    websocket_url="wss://example.invalid/data",
                    on_status=statuses.append,
                ):
                    pass

        with self.assertRaisesRegex(RuntimeError, "pumpportal_websocket_closed"):
            asyncio.run(run())
        self.assertEqual(statuses, ["connected", "disconnected"])


if __name__ == "__main__":
    unittest.main()
