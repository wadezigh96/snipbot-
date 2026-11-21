import pytest

from agent.pumpfun.paper import MicroPlan, goal_progress, next_position_usd

PLAN = MicroPlan()


def test_goal_progress_at_start():
    g = goal_progress(PLAN, 5.0)
    assert g["remaining_multiple"] == 300.0
    assert g["pct_of_target"] == pytest.approx(0.3333, abs=0.001)
    assert g["milestones_reached"] == []
    assert g["next_milestone_usd"] == 10.0
    assert g["bankroll_alive"] is True


def test_goal_progress_milestones():
    g = goal_progress(PLAN, 260.0)
    assert g["milestones_reached"] == [10.0, 25.0, 50.0, 100.0, 250.0]
    assert g["next_milestone_usd"] == 500.0
    done = goal_progress(PLAN, 1500.0)
    assert done["remaining_usd"] == 0.0 and done["next_milestone_usd"] is None


def test_compounding_position_size():
    assert next_position_usd(PLAN, 5.0) == 1.0       # base size at start
    assert next_position_usd(PLAN, 50.0) == 10.0     # 20% of equity
    assert next_position_usd(PLAN, 500.0) == 25.0    # capped
    assert next_position_usd(PLAN, 0.50) == 0.0      # below fee reserve: stop
