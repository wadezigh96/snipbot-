import unittest

from agent.pumpfun.scanner import normalize_event, score_event


MINT = "So11111111111111111111111111111111111111112"
TRADER = "11111111111111111111111111111111"


class PumpFunScannerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
