import pytest

from agent.pumpfun.paper import LadderTracker

T0 = 1_000_000.0


def test_stop_loss_sells_everything():
    t = LadderTracker(entry_price=1.0, opened_at=T0)
    action, frac = t.update(0.5, now=T0 + 60)
    assert action == "stop_loss" and frac == 1.0 and t.closed


def test_full_ladder_to_moonbag_and_trailing_stop():
    t = LadderTracker(entry_price=1.0, opened_at=T0)
    a, f = t.update(2.0, now=T0 + 60)
    assert a.startswith("tp1") and f == pytest.approx(0.40)
    assert t.stop_price == 1.0  # break-even armed
    a, f = t.update(5.0, now=T0 + 120)
    assert a.startswith("tp2") and f == pytest.approx(0.25)
    a, f = t.update(10.0, now=T0 + 180)
    assert a.startswith("tp3") and f == pytest.approx(0.20)
    assert t.moonbag and t.remaining_fraction == pytest.approx(0.15)
    # Moonbag rides: +50% more is still a hold.
    a, f = t.update(15.0, now=T0 + 240)
    assert a == "hold" and f == 0.0
    # -50% from the 15.0 peak triggers the trailing stop.
    a, f = t.update(7.4, now=T0 + 300)
    assert a == "moonbag_trailing_stop" and f == pytest.approx(0.15) and t.closed


def test_time_stop_before_moonbag():
    t = LadderTracker(entry_price=1.0, opened_at=T0)
    a, f = t.update(1.2, now=T0 + 7 * 3600)
    assert a == "time_stop" and f == 1.0


def test_breakeven_stop_after_tp1():
    t = LadderTracker(entry_price=1.0, opened_at=T0)
    t.update(2.5, now=T0 + 60)
    a, f = t.update(0.99, now=T0 + 120)
    assert a == "stop_loss" and f == pytest.approx(0.60)
