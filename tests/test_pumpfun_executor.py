import asyncio
import unittest

from agent.pumpfun.executor import Executor, LiveConfig
from agent.pumpfun.simulation import SimulationResult
from agent.pumpfun.trade_ledger import TradeLedger

MINT = "So11111111111111111111111111111111111111112"
WALLET = "Wa1111111111111111111111111111111111111111"
OPEN = LiveConfig(True, "live_gate_open")
CLOSED = LiveConfig.from_env({})


async def fake_build(**kwargs):
    return f"tx:{kwargs['action']}".encode()


async def fake_sim_ok(tx):
    return SimulationResult(True, "simulation_passed")


async def fake_sim_fail(tx):
    return SimulationResult(False, "simulation_failed", err="ProgramFailedToComplete")


def fake_sign(tx):
    return b"signed:" + tx


async def fake_send(tx):
    return "5" * 64


def make_executor(sim=fake_sim_ok, ledger=None, config=OPEN):
    return Executor(config, build_tx=fake_build, sign=fake_sign, simulate=sim, send=fake_send, ledger=ledger)


def buy_kwargs(**over):
    kw = dict(client_order_id="ord-1", mint=MINT, amount_sol=0.01, wallet=WALLET,
              rug_passed=True, sniper_status="PAPER_BUY_CANDIDATE", risk_allowed=True)
    kw.update(over)
    return kw


def sell_kwargs(**over):
    kw = dict(client_order_id="sell-1", mint=MINT, amount_tokens="1234.5", wallet=WALLET)
    kw.update(over)
    return kw


class ExecutorBuyTests(unittest.TestCase):
    def test_live_gate_closed_by_default(self):
        ex = make_executor(config=CLOSED)
        result = asyncio.run(ex.buy(**buy_kwargs()))
        self.assertEqual(result.status, "REFUSED")
        self.assertEqual(result.reason, "live_not_enabled")

    def test_confirm_phrase_required(self):
        self.assertFalse(LiveConfig.from_env({"SNIPER_LIVE_ENABLED": "true"}).enabled)
        cfg = LiveConfig.from_env({"SNIPER_LIVE_ENABLED": "true",
                                   "SNIPER_LIVE_CONFIRM": "I_UNDERSTAND_LIVE_TRADING"})
        self.assertTrue(cfg.enabled)

    def test_gates_refuse_in_order(self):
        ex = make_executor()
        self.assertEqual(asyncio.run(ex.buy(**buy_kwargs(rug_passed=False))).reason, "antirug_gate_failed")
        self.assertIn("sniper_status", asyncio.run(ex.buy(**buy_kwargs(sniper_status="WATCH_ONLY"))).reason)
        self.assertEqual(asyncio.run(ex.buy(**buy_kwargs(risk_allowed=False))).reason, "risk_policy_denied")

    def test_simulation_failure_refuses(self):
        ex = make_executor(sim=fake_sim_fail)
        result = asyncio.run(ex.buy(**buy_kwargs()))
        self.assertEqual(result.status, "REFUSED")
        self.assertIn("simulation", result.reason)

    def test_success_path_submits_and_records_ledger(self):
        ledger = TradeLedger(":memory:")
        ex = make_executor(ledger=ledger)
        result = asyncio.run(ex.buy(**buy_kwargs()))
        self.assertEqual(result.status, "SUBMITTED")
        self.assertEqual(result.signature, "5" * 64)
        order = ledger.get_order("ord-1")
        self.assertEqual(order["state"], "SUBMITTED")
        self.assertEqual(order["tx_signature"], "5" * 64)
        ledger.close()


class ExecutorSellTests(unittest.TestCase):
    def test_sell_success_path_and_ledger(self):
        ledger = TradeLedger(":memory:")
        ex = make_executor(ledger=ledger)
        result = asyncio.run(ex.sell(**sell_kwargs()))
        self.assertEqual(result.status, "SUBMITTED")
        order = ledger.get_order("sell-1")
        self.assertEqual(order["side"], "sell")
        self.assertEqual(order["state"], "SUBMITTED")
        ledger.close()

    def test_sell_refused_when_gate_closed_and_bad_amount(self):
        ex = make_executor(config=CLOSED)
        self.assertEqual(asyncio.run(ex.sell(**sell_kwargs())).reason, "live_not_enabled")
        ex2 = make_executor()
        self.assertEqual(asyncio.run(ex2.sell(**sell_kwargs(amount_tokens="0"))).reason,
                         "sell_amount_must_be_positive")
        self.assertEqual(asyncio.run(ex2.sell(**sell_kwargs(amount_tokens="abc"))).reason,
                         "invalid_sell_amount")

    def test_sell_simulation_failure_refuses(self):
        ex = make_executor(sim=fake_sim_fail)
        result = asyncio.run(ex.sell(**sell_kwargs()))
        self.assertEqual(result.status, "REFUSED")
        self.assertIn("sell_simulation_failed", result.reason)


if __name__ == "__main__":
    unittest.main()
