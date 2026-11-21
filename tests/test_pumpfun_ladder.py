import unittest

from agent.pumpfun.paper import LadderTracker

T0 = 1_000_000.0


class LadderTrackerTests(unittest.TestCase):
    def test_stop_loss_sells_everything(self):
        t = LadderTracker(entry_price=1.0, opened_at=T0)
        action, frac = t.update(0.5, now=T0 + 60)
        self.assertEqual(action, "stop_loss")
        self.assertEqual(frac, 1.0)
        self.assertTrue(t.closed)

    def test_full_ladder_to_moonbag_and_trailing_stop(self):
        t = LadderTracker(entry_price=1.0, opened_at=T0)
        a, f = t.update(2.0, now=T0 + 60)
        self.assertTrue(a.startswith("tp1"))
        self.assertAlmostEqual(f, 0.40)
        self.assertEqual(t.stop_price, 1.0)
        a, f = t.update(5.0, now=T0 + 120)
        self.assertTrue(a.startswith("tp2"))
        self.assertAlmostEqual(f, 0.25)
        a, f = t.update(10.0, now=T0 + 180)
        self.assertTrue(a.startswith("tp3"))
        self.assertAlmostEqual(f, 0.20)
        self.assertTrue(t.moonbag)
        self.assertAlmostEqual(t.remaining_fraction, 0.15)
        a, f = t.update(15.0, now=T0 + 240)
        self.assertEqual((a, f), ("hold", 0.0))
        a, f = t.update(7.4, now=T0 + 300)
        self.assertEqual(a, "moonbag_trailing_stop")
        self.assertAlmostEqual(f, 0.15)
        self.assertTrue(t.closed)

    def test_time_stop_before_moonbag(self):
        t = LadderTracker(entry_price=1.0, opened_at=T0)
        a, f = t.update(1.2, now=T0 + 7 * 3600)
        self.assertEqual((a, f), ("time_stop", 1.0))

    def test_breakeven_stop_after_tp1(self):
        t = LadderTracker(entry_price=1.0, opened_at=T0)
        t.update(2.5, now=T0 + 60)
        a, f = t.update(0.99, now=T0 + 120)
        self.assertEqual(a, "stop_loss")
        self.assertAlmostEqual(f, 0.60)


if __name__ == "__main__":
    unittest.main()
