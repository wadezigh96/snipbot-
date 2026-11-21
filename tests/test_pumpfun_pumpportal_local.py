import unittest

from agent.pumpfun.pumpportal_local import build_request


PUBKEY = "11111111111111111111111111111111"
MINT = "So11111111111111111111111111111111111111112"


class PumpPortalLocalRequestTests(unittest.TestCase):
    def build(self, **overrides):
        values = dict(
            public_key=PUBKEY,
            mint=MINT,
            action="buy",
            amount="0.02",
            denominated_in_sol=True,
            slippage_percent=3,
            priority_fee_sol="0.00001",
            pool="auto",
        )
        values.update(overrides)
        return build_request(**values)

    def test_builds_buy_request_without_secret(self):
        result = self.build()
        self.assertEqual(result["action"], "buy")
        self.assertEqual(result["amount"], "0.02")
        self.assertEqual(result["denominatedInSol"], "true")
        self.assertEqual(result["slippage"], 3)
        self.assertNotIn("privateKey", result)

    def test_builds_sell_request_in_token_units(self):
        result = self.build(action="sell", amount="100", denominated_in_sol=False)
        self.assertEqual(result["action"], "sell")
        self.assertEqual(result["denominatedInSol"], "false")

    def test_rejects_bad_public_key_or_mint(self):
        with self.assertRaisesRegex(ValueError, "invalid_public_key"):
            self.build(public_key="not-a-key")
        with self.assertRaisesRegex(ValueError, "invalid_mint"):
            self.build(mint="bad")

    def test_rejects_unknown_action(self):
        with self.assertRaisesRegex(ValueError, "invalid_action"):
            self.build(action="transfer")

    def test_rejects_slippage_outside_conservative_range(self):
        for value in (0, 6, True, 3.0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.build(slippage_percent=value)

    def test_rejects_excessive_priority_fee(self):
        with self.assertRaisesRegex(ValueError, "priority_fee_above_safe_cap"):
            self.build(priority_fee_sol="0.002")

    def test_rejects_nan_and_zero_amount(self):
        for value in ("NaN", "Infinity", "0", "-1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.build(amount=value)

    def test_rejects_unsupported_pool(self):
        with self.assertRaisesRegex(ValueError, "unsupported_pool"):
            self.build(pool="unknown-pool")

    def test_rejects_non_boolean_denomination(self):
        with self.assertRaisesRegex(ValueError, "denominated_in_sol_must_be_boolean"):
            self.build(denominated_in_sol="true")


if __name__ == "__main__":
    unittest.main()
