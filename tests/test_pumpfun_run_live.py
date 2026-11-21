import asyncio

import pytest

from agent.pumpfun.antirug import RugVerdict
from agent.pumpfun.bubblemap import analyze_holders
from agent.pumpfun.executor import ExecutionResult
from agent.pumpfun.llm_sniper import SniperDecision, final_decision
from agent.pumpfun.paper import MicroPlan, PaperEngine
from agent.pumpfun.rpc import MintCheck
from agent.pumpfun.run_live import (RunnerContext, RunnerDeps, dexscreener_price_usd,
                                    parse_mode, poll_paper_positions, process_event, run)
from agent.pumpfun.simulation import SimulationResult

MINT = "So11111111111111111111111111111111111111112"
GOOD_MINT = MintCheck("VERIFIED", MINT, "mint_layout_valid", mint_authority_present=False,
                      freeze_authority_present=False)
GOOD_HOLDERS = analyze_holders([(f"w{i}", 10.0) for i in range(50)], total_supply=1000.0)
EVENT = {"mint": MINT, "symbol": "TEST", "event_type": "new_token",
         "market_cap_sol": 100.0, "v_sol_in_curve": 30.0}


async def fake_build(**kwargs):
    return b"unsigned-tx"


async def fake_sim_ok(tx):
    return SimulationResult(True, "simulation_passed")


async def approve(event, rug, bubblemap):
    # Emulates the real score_candidate: LLM approval through final_decision,
    # which can never override a failed anti-rug gate.
    return final_decision(rug, ("APPROVE_PAPER", 90, "clean"))


async def watch(event, rug, bubblemap):
    return SniperDecision("WATCH_ONLY", "WATCH", 50, "meh")


def make_ctx(mode="paper", score_fn=approve, executor=None, wallet=None):
    deps = RunnerDeps(
        verify_mint_fn=lambda mint: _coro(GOOD_MINT),
        bubblemap_fn=lambda mint, exclude=None: _coro(GOOD_HOLDERS),
        score_fn=score_fn,
        build_tx_fn=fake_build,
        simulate_fn=fake_sim_ok,
        price_fn=lambda mint: _coro(0.002),
    )
    plan = MicroPlan()
    ctx = RunnerContext(mode=mode, plan=plan, deps=deps, paper=PaperEngine(plan),
                        executor=executor, wallet=wallet)
    ctx.sol_usd = 200.0
    return ctx


async def _coro(value):
    return value


def test_parse_mode():
    assert parse_mode({}) == "paper"
    assert parse_mode({"SNIPER_MODE": "live"}) == "live"
    with pytest.raises(ValueError):
        parse_mode({"SNIPER_MODE": "yolo"})


def test_dexscreener_price_picks_highest_liquidity_pair():
    payload = {"pairs": [
        {"priceUsd": "0.001", "liquidity": {"usd": 100}},
        {"priceUsd": "0.002", "liquidity": {"usd": 5000}},
        {"priceUsd": "bad", "liquidity": {"usd": 99999}},
    ]}
    assert dexscreener_price_usd(payload) == 0.002
    assert dexscreener_price_usd({"pairs": []}) is None
    assert dexscreener_price_usd(None) is None


def test_paper_candidate_opens_position():
    ctx = make_ctx()
    out = asyncio.run(process_event(dict(EVENT), ctx, now=1000.0))
    assert out["sniper_status"] == "PAPER_BUY_CANDIDATE"
    assert out["action"] == "paper_opened"
    assert len(ctx.paper.positions) == 1


def test_watch_candidate_does_nothing():
    ctx = make_ctx(score_fn=watch)
    out = asyncio.run(process_event(dict(EVENT), ctx, now=1000.0))
    assert out["action"] == "none" and not ctx.paper.positions


def test_freeze_authority_blocks_everything():
    async def frozen(mint):
        return MintCheck("VERIFIED", mint, "x", mint_authority_present=False,
                         freeze_authority_present=True)

    ctx = make_ctx()
    ctx.deps.verify_mint_fn = frozen
    out = asyncio.run(process_event(dict(EVENT), ctx, now=1000.0))
    assert out["antirug_passed"] is False and out["action"] == "none"


class FakeExecutor:
    def __init__(self):
        self.calls = []

    async def buy(self, **kwargs):
        self.calls.append(kwargs)
        return ExecutionResult("SUBMITTED", "ok", signature="sig123")


def test_live_candidate_submits_via_executor():
    executor = FakeExecutor()
    ctx = make_ctx(mode="live", executor=executor, wallet="Wa1111111111111111111111111111111111111111")
    out = asyncio.run(process_event(dict(EVENT), ctx, now=1000.0))
    assert out["action"] == "live_submitted" and out["signature"] == "sig123"
    assert executor.calls[0]["amount_sol"] == pytest.approx(1.0 / 200.0)
    assert ctx.live_open_positions == 1


def test_live_mode_refuses_to_start_without_gate(monkeypatch):
    monkeypatch.setenv("SNIPER_MODE", "live")
    monkeypatch.delenv("SNIPER_LIVE_ENABLED", raising=False)
    monkeypatch.delenv("SNIPER_LIVE_CONFIRM", raising=False)
    assert asyncio.run(run()) == 2


def test_poll_paper_positions_exits_on_stop_loss():
    ctx = make_ctx()
    asyncio.run(process_event(dict(EVENT), ctx, now=1000.0))
    assert len(ctx.paper.positions) == 1
    ctx.deps.price_fn = lambda mint: _coro(0.001)  # -50% from 0.002 entry
    asyncio.run(poll_paper_positions(ctx, interval_seconds=0, iterations=1))
    assert ctx.paper.positions[0].closed


def test_early_mode_blocks_late_curve_token():
    ctx = make_ctx()
    ctx.early_mode = True
    late = {**EVENT, "v_sol_in_curve": 60.0}
    out = asyncio.run(process_event(late, ctx, now=1000.0))
    assert out["early_passed"] is False and out["action"] == "none"
    early = {**EVENT, "initial_buy": 1.0}
    out2 = asyncio.run(process_event(early, ctx, now=1000.0))
    assert out2["early_passed"] is True and out2["action"] == "paper_opened"


class FakeLiveExecutor(FakeExecutor):
    def __init__(self):
        super().__init__()
        self.sells = []

    async def sell(self, **kwargs):
        self.sells.append(kwargs)
        return ExecutionResult("SUBMITTED", "ok", signature="sellsig")


def test_live_exit_poll_sells_on_stop_loss():
    executor = FakeLiveExecutor()
    ctx = make_ctx(mode="live", executor=executor, wallet="Wa1111111111111111111111111111111111111111")
    out = asyncio.run(process_event(dict(EVENT), ctx, now=1000.0))
    assert out["action"] == "live_submitted" and len(ctx.live_positions) == 1
    ctx.deps.token_balance_fn = lambda wallet, mint: _coro(1000.0)
    ctx.deps.price_fn = lambda mint: _coro(0.001)  # entry was 0.002 -> -50%
    from agent.pumpfun.run_live import poll_live_positions
    asyncio.run(poll_live_positions(ctx, interval_seconds=0, iterations=1))
    assert len(executor.sells) == 1
    assert executor.sells[0]["amount_tokens"] == "1000.000000"
    assert ctx.live_positions[0].tracker.closed
