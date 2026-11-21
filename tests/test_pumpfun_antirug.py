import unittest

from agent.pumpfun.antirug import evaluate_rug_risk
from agent.pumpfun.bubblemap import analyze_holders
from agent.pumpfun.rpc import MintCheck

GOOD_MINT = MintCheck("VERIFIED", "mint", "mint_layout_valid", decimals=6,
                      mint_authority_present=False, freeze_authority_present=False)
GOOD_HOLDERS = analyze_holders([(f"w{i}", 10.0) for i in range(50)], total_supply=1000.0)


def base(**over):
    kw = dict(mint_check=GOOD_MINT, bubblemap=GOOD_HOLDERS, liquidity_usd=20_000.0,
              v_sol_in_curve=30.0, market_cap_usd=50_000.0, sell_simulation_passed=True)
    kw.update(over)
    return evaluate_rug_risk(**kw)


class AntiRugTests(unittest.TestCase):
    def test_all_gates_pass(self):
        v = base()
        self.assertTrue(v.passed)
        self.assertGreaterEqual(v.score, 70)

    def test_freeze_authority_rejected(self):
        mint = MintCheck("VERIFIED", "m", "x", mint_authority_present=False, freeze_authority_present=True)
        self.assertFalse(base(mint_check=mint).passed)

    def test_unknown_mint_rejected(self):
        mint = MintCheck("UNKNOWN", "m", "solana_rpc_not_configured")
        self.assertFalse(base(mint_check=mint).passed)

    def test_unknown_holders_rejected(self):
        self.assertFalse(base(bubblemap=analyze_holders([])).passed)

    def test_no_sell_simulation_rejected(self):
        self.assertFalse(base(sell_simulation_passed=False).passed)

    def test_no_liquidity_rejected(self):
        self.assertFalse(base(liquidity_usd=None, v_sol_in_curve=None).passed)

    def test_concentrated_holders_rejected(self):
        bad = analyze_holders([("whale", 900.0), ("a", 50.0)], total_supply=1000.0)
        self.assertFalse(base(bubblemap=bad).passed)


if __name__ == "__main__":
    unittest.main()
