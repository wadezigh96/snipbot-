import unittest

from agent.pumpfun.risk import RiskPolicy


class RiskPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = RiskPolicy()

    def check(self, **overrides):
        args = dict(
            position_usd=1.0,
            open_positions=0,
            daily_realized_loss_usd=0.0,
            available_sol_usd=10.0,
            estimated_network_fee_usd=0.05,
            data_is_fresh=True,
            quote_is_valid=True,
            simulation_passed=True,
        )
        args.update(overrides)
        return self.policy.check_buy(**args)

    def test_all_checks_pass(self):
        self.assertTrue(self.check().allowed)

    def test_rejects_position_above_one_dollar(self):
        self.assertEqual(self.check(position_usd=1.01).reason, "position_limit_exceeded")

    def test_rejects_when_two_positions_are_open(self):
        self.assertEqual(self.check(open_positions=2).reason, "open_position_limit_reached")

    def test_rejects_daily_loss_cap(self):
        self.assertEqual(self.check(daily_realized_loss_usd=1.0).reason, "daily_loss_limit_reached")

    def test_rejects_stale_data(self):
        self.assertEqual(self.check(data_is_fresh=False).reason, "market_data_stale_or_unknown")

    def test_rejects_bad_quote(self):
        self.assertEqual(self.check(quote_is_valid=False).reason, "quote_missing_or_invalid")

    def test_rejects_failed_simulation(self):
        self.assertEqual(self.check(simulation_passed=False).reason, "transaction_simulation_not_passed")

    def test_rejects_when_sol_reserve_would_be_breached(self):
        self.assertEqual(
            self.check(available_sol_usd=2.0, estimated_network_fee_usd=0.1).reason,
            "sol_fee_reserve_would_be_breached",
        )

    def test_rejects_nan(self):
        self.assertEqual(self.check(position_usd=float("nan")).reason, "non_finite_numeric_input")


if __name__ == "__main__":
    unittest.main()
