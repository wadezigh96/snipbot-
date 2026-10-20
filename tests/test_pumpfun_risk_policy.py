import unittest
from copy import deepcopy

from agent.pumpfun.risk_policy import RiskLimits, evaluate_pretrade


BASE = {
    "mint_status": "VERIFIED",
    "liquidity_sol": "25",
    "holder_concentration_pct": "12",
    "creator_holding_pct": "2",
    "sell_quote_ok": True,
    "simulation_ok": True,
    "slippage_bps": 150,
    "buy_amount_sol": "0.02",
    "daily_pnl_sol": "0",
    "open_positions": 0,
    "llm_status": "WATCH",
}


class PumpFunRiskPolicyTests(unittest.TestCase):
    def test_passes_only_to_paper_mode_by_default(self):
        result = evaluate_pretrade(BASE)
        self.assertTrue(result.allowed)
        self.assertEqual(result.status, "PAPER_ONLY")

    def test_live_enabled_only_marks_ready_for_separate_executor(self):
        result = evaluate_pretrade(BASE, live_enabled=True)
        self.assertTrue(result.allowed)
        self.assertEqual(result.status, "READY_FOR_EXECUTOR")

    def test_missing_evidence_fails_closed(self):
        evidence = deepcopy(BASE)
        del evidence["sell_quote_ok"]
        result = evaluate_pretrade(evidence, live_enabled=True)
        self.assertFalse(result.allowed)
        self.assertIn("missing_sell_quote_ok", result.reasons)

    def test_unknown_mint_rejected(self):
        evidence = deepcopy(BASE)
        evidence["mint_status"] = "UNKNOWN"
        result = evaluate_pretrade(evidence, live_enabled=True)
        self.assertFalse(result.allowed)
        self.assertIn("mint_not_verified", result.reasons)

    def test_rejected_llm_cannot_be_overridden(self):
        evidence = deepcopy(BASE)
        evidence["llm_status"] = "REJECT"
        self.assertFalse(evaluate_pretrade(evidence, live_enabled=True).allowed)

    def test_liquidity_and_concentration_limits(self):
        evidence = deepcopy(BASE)
        evidence["liquidity_sol"] = "1"
        evidence["holder_concentration_pct"] = "90"
        result = evaluate_pretrade(evidence, live_enabled=True)
        self.assertIn("liquidity_below_minimum", result.reasons)
        self.assertIn("holder_concentration_too_high", result.reasons)

    def test_daily_loss_stops_new_buys(self):
        evidence = deepcopy(BASE)
        evidence["daily_pnl_sol"] = "-0.10"
        self.assertIn("daily_loss_limit_reached", evaluate_pretrade(evidence).reasons)

    def test_sell_quote_and_simulation_required(self):
        evidence = deepcopy(BASE)
        evidence["sell_quote_ok"] = False
        evidence["simulation_ok"] = False
        result = evaluate_pretrade(evidence)
        self.assertIn("sell_quote_not_confirmed", result.reasons)
        self.assertIn("transaction_simulation_failed", result.reasons)

    def test_bad_numeric_values_fail_closed(self):
        evidence = deepcopy(BASE)
        evidence["buy_amount_sol"] = "NaN"
        evidence["slippage_bps"] = True
        result = evaluate_pretrade(evidence)
        self.assertIn("invalid_buy_amount_sol", result.reasons)
        self.assertIn("invalid_slippage_bps", result.reasons)

    def test_position_limit_stops_new_buys(self):
        evidence = deepcopy(BASE)
        evidence["open_positions"] = 2
        self.assertIn("max_open_positions_reached", evaluate_pretrade(evidence).reasons)

    def test_custom_limits_are_supported(self):
        limits = RiskLimits(max_buy_sol=__import__("decimal").Decimal("0.01"))
        self.assertIn(
            "buy_amount_out_of_limits",
            evaluate_pretrade(BASE, limits=limits).reasons,
        )


if __name__ == "__main__":
    unittest.main()
