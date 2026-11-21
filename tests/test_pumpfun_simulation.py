import asyncio
import unittest

from agent.pumpfun.simulation import (SimulationResult, classify_sell_simulation,
                                      parse_simulation, parse_token_balance,
                                      simulate_transaction)


class SimulationTests(unittest.TestCase):
    def test_parse_pass_and_fail(self):
        ok = parse_simulation({"result": {"value": {"err": None, "logs": []}}})
        self.assertTrue(ok.passed)
        bad = parse_simulation({"result": {"value": {"err": {"InstructionError": [0, "Custom"]}}}})
        self.assertFalse(bad.passed)
        self.assertTrue(bad.err)
        self.assertFalse(parse_simulation({"error": {"code": -1}}).passed)
        self.assertFalse(parse_simulation("nonsense").passed)

    def test_sell_classification_balance_case_and_program_error(self):
        balance_only = SimulationResult(False, "simulation_failed", err="insufficient funds for transaction")
        self.assertTrue(classify_sell_simulation(balance_only).passed)
        program_error = SimulationResult(False, "simulation_failed", err="ProgramFailedToComplete")
        self.assertFalse(classify_sell_simulation(program_error).passed)
        passed = SimulationResult(True, "simulation_passed")
        self.assertTrue(classify_sell_simulation(passed).passed)

    def test_simulate_without_rpc_fails_closed(self):
        result = asyncio.run(simulate_transaction(b"abc", rpc_url=""))
        self.assertFalse(result.passed)

    def test_simulate_with_fake_post(self):
        async def fake_post(url, payload):
            self.assertEqual(payload["method"], "simulateTransaction")
            return {"result": {"value": {"err": None}}}

        result = asyncio.run(simulate_transaction(b"abc", rpc_url="https://rpc.example", post=fake_post))
        self.assertTrue(result.passed)

    def test_parse_token_balance(self):
        body = {"result": {"value": [
            {"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmount": 12.5}}}}}},
            {"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmount": 2.5}}}}}},
            {"account": {"data": {"parsed": {"info": {}}}}},
        ]}}
        self.assertEqual(parse_token_balance(body), 15.0)
        self.assertEqual(parse_token_balance({"result": {"value": []}}), 0.0)
        self.assertIsNone(parse_token_balance({"error": {}}))
        self.assertIsNone(parse_token_balance(None))


if __name__ == "__main__":
    unittest.main()
