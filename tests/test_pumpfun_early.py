import unittest

from agent.pumpfun.bubblemap import analyze_holders
from agent.pumpfun.early import evaluate_early_entry
from agent.pumpfun.rpc import MintCheck

MINT = "So11111111111111111111111111111111111111112"
GOOD_MINT = MintCheck("VERIFIED", MINT, "ok", mint_authority_present=False, freeze_authority_present=False)
GOOD = analyze_holders([(f"w{i}", 10.0) for i in range(50)], total_supply=1000.0)
EVENT = {"event_type": "new_token", "v_sol_in_curve": 10.0, "initial_buy": 1.0}


class EarlyEntryTests(unittest.TestCase):
    def test_clean_early_token_passes(self):
        self.assertTrue(evaluate_early_entry(dict(EVENT), mint_check=GOOD_MINT, bubblemap=GOOD).passed)

    def test_past_early_window_rejected(self):
        v = evaluate_early_entry({**EVENT, "v_sol_in_curve": 60.0}, mint_check=GOOD_MINT, bubblemap=GOOD)
        self.assertFalse(v.passed)
        self.assertIn("past_early_window", v.reasons)

    def test_bundled_dev_initial_buy_rejected(self):
        v = evaluate_early_entry({**EVENT, "initial_buy": 12.0}, mint_check=GOOD_MINT, bubblemap=GOOD)
        self.assertFalse(v.passed)
        self.assertTrue(any("initial_buy" in r for r in v.reasons))

    def test_concentrated_holders_rejected(self):
        bundled = analyze_holders([("devwallet", 400.0)] + [(f"w{i}", 10.0) for i in range(20)],
                                  total_supply=1000.0)
        self.assertFalse(evaluate_early_entry(dict(EVENT), mint_check=GOOD_MINT, bubblemap=bundled).passed)

    def test_migration_event_is_not_early(self):
        v = evaluate_early_entry({**EVENT, "event_type": "migration"}, mint_check=GOOD_MINT, bubblemap=GOOD)
        self.assertFalse(v.passed)

    def test_unknown_curve_rejected(self):
        v = evaluate_early_entry({"event_type": "new_token", "initial_buy": 0.5},
                                 mint_check=GOOD_MINT, bubblemap=GOOD)
        self.assertFalse(v.passed)


if __name__ == "__main__":
    unittest.main()
