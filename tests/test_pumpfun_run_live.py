import asyncio
import os
import unittest
from unittest.mock import patch

from agent.pumpfun.bubblemap import analyze_holders
from agent.pumpfun.executor import ExecutionResult
from agent.pumpfun.llm_sniper import SniperDecision, final_decision
from agent.pumpfun.paper import MicroPlan, PaperEngine
from agent.pumpfun.rpc import MintCheck
from agent.pumpfun.run_live import (RunnerContext, RunnerDeps, dexscreener_price_usd,
                                    parse_mode, poll_live_positions, poll_paper_positions,
                                    process_event, run)
from agent.pumpfun.simulation import SimulationResult

MINT = "So11111111111111111111111111111111111111112"
GOOD_MINT = MintCheck("VERIFIED", MINT, "mint_layout_valid", mint_authority_present=False,
                      freeze_authority_present=False)
GOOD_HOLDERS = analyze_holders([(f"w{i}", 10.0) for i in range(50)], total_supply=1000.0)
EVENT = {"mint": MINT, "symbol": "TEST", "event_type": "new_token",
         "market_cap_sol": 100.0, "v_sol_in_curve": 30.0}


async def _coro(value):
    return value


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


class FakeExecutor:
    def __init__(self):
        self.calls = []

    async def buy(self, **kwargs):
        self.calls.append(kwargs)
        return ExecutionResult("SUBMITTED", "ok", signature="sig123")


class FakeLiveExecutor(FakeExecutor):
    def __init__(self):
        super().__init__()
        self.sells = []

    async def sell(self, **kwargs):
        self.sells.append(kwargs)
        return ExecutionResult("SUBMITTED", "ok", signature="sellsig")


class RunLiveTests(unittest.TestCase):
    def test_parse_mode(self):
        self.assertEqual(parse_mode({}), "paper")
        self.assertEqual(parse_mode({"SNIPER_MODE": "live"}), "live")
        with self.assertRaises(ValueError):
            parse_mode({"SNIPER_MODE": "yolo"})

    def test_dexscreener_price_picks_highest_liquidity_pair(self):
        payload = {"pairs": [
            {"priceUsd": "0.001", "liquidity": {"usd": 100}},
            {"priceUsd": "0.002", "liquidity": {"usd": 5000}},
            {"priceUsd": "bad", "liquidity": {"usd": 99999}},
        ]}
        self.assertEqual(dexscreener_price_usd(payload), 0.002)
        self.assertIsNone(dexscreener_price_usd({"pairs": []}))
        self.assertIsNone(dexscreener_price_usd(None))

    def test_paper_candidate_opens_position(self):
        ctx = make_ctx()
        out = asyncio.run(process_event(dict(EVENT), ctx, now=1000.0))
        self.assertEqual(out["sniper_status"], "PAPER_BUY_CANDIDATE")
        self.assertEqual(out["action"], "paper_opened")
        self.assertEqual(len(ctx.paper.positions), 1)

    def test_watch_candidate_does_nothing(self):
        ctx = make_ctx(score_fn=watch)
        out = asyncio.run(process_event(dict(EVENT), ctx, now=1000.0))
        self.assertEqual(out["action"], "none")
        self.assertFalse(ctx.paper.positions)

    def test_freeze_authority_blocks_everything(self):
        async def frozen(mint):
            return MintCheck("VERIFIED", mint, "x", mint_authority_present=False,
                             freeze_authority_present=True)

        ctx = make_ctx()
        ctx.deps.verify_mint_fn = frozen
        out = asyncio.run(process_event(dict(EVENT), ctx, now=1000.0))
        self.assertFalse(out["antirug_passed"])
        self.assertEqual(out["action"], "none")

    def test_live_candidate_submits_via_executor(self):
        executor = FakeExecutor()
        ctx = make_ctx(mode="live", executor=executor,
                       wallet="Wa1111111111111111111111111111111111111111")
        out = asyncio.run(process_event(dict(EVENT), ctx, now=1000.0))
        self.assertEqual(out["action"], "live_submitted")
        self.assertEqual(out["signature"], "sig123")
        self.assertAlmostEqual(executor.calls[0]["amount_sol"], 1.0 / 200.0)
        self.assertEqual(ctx.live_open_positions, 1)

    def test_live_mode_refuses_to_start_without_gate(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("SNIPER_LIVE_ENABLED", "SNIPER_LIVE_CONFIRM")}
        env["SNIPER_MODE"] = "live"
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(asyncio.run(run()), 2)

    def test_poll_paper_positions_exits_on_stop_loss(self):
        ctx = make_ctx()
        asyncio.run(process_event(dict(EVENT), ctx, now=1000.0))
        self.assertEqual(len(ctx.paper.positions), 1)
        ctx.deps.price_fn = lambda mint: _coro(0.001)  # -50% from 0.002 entry
        asyncio.run(poll_paper_positions(ctx, interval_seconds=0, iterations=1))
        self.assertTrue(ctx.paper.positions[0].closed)

    def test_early_mode_blocks_late_curve_token(self):
        ctx = make_ctx()
        ctx.early_mode = True
        late = {**EVENT, "v_sol_in_curve": 60.0}
        out = asyncio.run(process_event(late, ctx, now=1000.0))
        self.assertFalse(out["early_passed"])
        self.assertEqual(out["action"], "none")
        early = {**EVENT, "initial_buy": 1.0}
        out2 = asyncio.run(process_event(early, ctx, now=1000.0))
        self.assertTrue(out2["early_passed"])
        self.assertEqual(out2["action"], "paper_opened")

    def test_live_exit_poll_sells_on_stop_loss(self):
        executor = FakeLiveExecutor()
        ctx = make_ctx(mode="live", executor=executor,
                       wallet="Wa1111111111111111111111111111111111111111")
        out = asyncio.run(process_event(dict(EVENT), ctx, now=1000.0))
        self.assertEqual(out["action"], "live_submitted")
        self.assertEqual(len(ctx.live_positions), 1)
        ctx.deps.token_balance_fn = lambda wallet, mint: _coro(1000.0)
        ctx.deps.price_fn = lambda mint: _coro(0.001)  # entry was 0.002 -> -50%
        asyncio.run(poll_live_positions(ctx, interval_seconds=0, iterations=1))
        self.assertEqual(len(executor.sells), 1)
        self.assertEqual(executor.sells[0]["amount_tokens"], "1000.000000")
        self.assertTrue(ctx.live_positions[0].tracker.closed)


if __name__ == "__main__":
    unittest.main()
