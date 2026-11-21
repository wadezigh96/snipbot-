import unittest

from agent.pumpfun.paper import MicroPlan, goal_progress, next_position_usd

PLAN = MicroPlan()


class GoalTrackerTests(unittest.TestCase):
    def test_goal_progress_at_start(self):
        g = goal_progress(PLAN, 5.0)
        self.assertEqual(g["remaining_multiple"], 300.0)
        self.assertAlmostEqual(g["pct_of_target"], 0.3333, delta=0.001)
        self.assertEqual(g["milestones_reached"], [])
        self.assertEqual(g["next_milestone_usd"], 10.0)
        self.assertTrue(g["bankroll_alive"])

    def test_goal_progress_milestones(self):
        g = goal_progress(PLAN, 260.0)
        self.assertEqual(g["milestones_reached"], [10.0, 25.0, 50.0, 100.0, 250.0])
        self.assertEqual(g["next_milestone_usd"], 500.0)
        done = goal_progress(PLAN, 1500.0)
        self.assertEqual(done["remaining_usd"], 0.0)
        self.assertIsNone(done["next_milestone_usd"])

    def test_compounding_position_size(self):
        self.assertEqual(next_position_usd(PLAN, 5.0), 1.0)
        self.assertEqual(next_position_usd(PLAN, 50.0), 10.0)
        self.assertEqual(next_position_usd(PLAN, 500.0), 25.0)
        self.assertEqual(next_position_usd(PLAN, 0.50), 0.0)


if __name__ == "__main__":
    unittest.main()
