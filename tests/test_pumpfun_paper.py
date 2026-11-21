import unittest

from agent.pumpfun.paper import MicroPlan, PaperEngine, target_math

T0 = 1_000_000.0
PLAN = MicroPlan()


class PaperEngineTests(unittest.TestCase):
    def test_micro_plan_defaults_and_target_math(self):
        PLAN.validate()
        math = target_math(PLAN)
        self.assertEqual(math["multiple_needed"], 300.0)
        self.assertAlmostEqual(math["win_return_needed_per_trade_20"], 0.33, delta=0.01)

    def test_open_deducts_principal_and_fees(self):
        e = PaperEngine()
        p = e.open("mintA", 1.0, now=T0)
        self.assertIsNotNone(p)
        self.assertAlmostEqual(e.cash_usd, 5.0 - 1.0 - 0.03)

    def test_stop_loss_closes_and_loses_less_than_principal(self):
        e = PaperEngine()
        p = e.open("mintA", 1.0, now=T0)
        action = e.update(p, 0.50, now=T0 + 60)
        self.assertEqual(action, "stop_loss")
        self.assertTrue(p.closed)
        self.assertLess(e.cash_usd, 5.0)
        self.assertGreater(e.cash_usd, 3.5)

    def test_tp_ladder_sells_in_stages_and_locks_profit(self):
        e = PaperEngine()
        p = e.open("mintA", 1.0, now=T0)
        self.assertEqual(e.update(p, 2.0, now=T0 + 60), "tp1_sell_50pct_breakeven_stop")
        self.assertEqual(p.remaining_fraction, 0.5)
        self.assertEqual(e.update(p, 1.0, now=T0 + 120), "stop_loss")
        self.assertTrue(p.closed)
        self.assertGreater(e.cash_usd, 5.0)

    def test_time_stop(self):
        e = PaperEngine()
        p = e.open("mintA", 1.0, now=T0)
        self.assertEqual(e.update(p, 1.1, now=T0 + 7 * 3600), "time_stop")
        self.assertTrue(p.closed)

    def test_max_open_positions_and_equity(self):
        e = PaperEngine()
        for i in range(3):
            self.assertIsNotNone(e.open(f"m{i}", 1.0, now=T0))
        self.assertIsNone(e.open("m4", 1.0, now=T0))
        self.assertGreater(e.equity_usd({}), 0)


if __name__ == "__main__":
    unittest.main()
