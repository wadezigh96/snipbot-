import pytest

from agent.pumpfun.paper import MicroPlan, PaperEngine, target_math

T0 = 1_000_000.0


def test_micro_plan_defaults_and_target_math():
    plan = MicroPlan()
    plan.validate()
    math = target_math(plan)
    assert math["multiple_needed"] == 300.0
    # Even winning every trade, 20 trades in a row must average ~+33% each.
    assert math["win_return_needed_per_trade_20"] == pytest.approx(0.33, abs=0.01)


def test_open_deducts_principal_and_fees():
    e = PaperEngine()
    p = e.open("mintA", 1.0, now=T0)
    assert p is not None
    assert e.cash_usd == pytest.approx(5.0 - 1.0 - 0.03)


def test_stop_loss_closes_and_loses_less_than_principal():
    e = PaperEngine()
    p = e.open("mintA", 1.0, now=T0)
    action = e.update(p, 0.50, now=T0 + 60)
    assert action == "stop_loss" and p.closed
    assert e.cash_usd < 5.0 and e.cash_usd > 3.5


def test_tp_ladder_sells_in_stages_and_locks_profit():
    e = PaperEngine()
    p = e.open("mintA", 1.0, now=T0)
    assert e.update(p, 2.0, now=T0 + 60) == "tp1_sell_50pct_breakeven_stop"
    assert p.remaining_fraction == 0.5
    # After TP1 the stop is break-even: dropping to entry closes the rest.
    assert e.update(p, 1.0, now=T0 + 120) == "stop_loss"
    assert p.closed
    assert e.cash_usd > 5.0  # TP1 profit survived


def test_time_stop():
    e = PaperEngine()
    p = e.open("mintA", 1.0, now=T0)
    assert e.update(p, 1.1, now=T0 + 7 * 3600) == "time_stop"
    assert p.closed


def test_max_open_positions_and_equity():
    e = PaperEngine()
    for i in range(3):
        assert e.open(f"m{i}", 1.0, now=T0) is not None
    assert e.open("m4", 1.0, now=T0) is None
    assert e.equity_usd({}) > 0
