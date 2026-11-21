import asyncio

from agent.pumpfun.simulation import (SimulationResult, classify_sell_simulation,
                                      parse_simulation, simulate_transaction)


def test_parse_pass_and_fail():
    ok = parse_simulation({"result": {"value": {"err": None, "logs": []}}})
    assert ok.passed
    bad = parse_simulation({"result": {"value": {"err": {"InstructionError": [0, "Custom"]}}}})
    assert not bad.passed and bad.err
    assert not parse_simulation({"error": {"code": -1}}).passed
    assert not parse_simulation("nonsense").passed


def test_sell_classification_balance_case_and_program_error():
    balance_only = SimulationResult(False, "simulation_failed", err="insufficient funds for transaction")
    assert classify_sell_simulation(balance_only).passed
    program_error = SimulationResult(False, "simulation_failed", err="ProgramFailedToComplete")
    assert not classify_sell_simulation(program_error).passed
    passed = SimulationResult(True, "simulation_passed")
    assert classify_sell_simulation(passed).passed


def test_simulate_without_rpc_fails_closed():
    result = asyncio.run(simulate_transaction(b"abc", rpc_url=""))
    assert not result.passed


def test_simulate_with_fake_post():
    async def fake_post(url, payload):
        assert payload["method"] == "simulateTransaction"
        return {"result": {"value": {"err": None}}}

    result = asyncio.run(simulate_transaction(b"abc", rpc_url="https://rpc.example", post=fake_post))
    assert result.passed


def test_parse_token_balance():
    from agent.pumpfun.simulation import parse_token_balance
    body = {"result": {"value": [
        {"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmount": 12.5}}}}}},
        {"account": {"data": {"parsed": {"info": {"tokenAmount": {"uiAmount": 2.5}}}}}},
        {"account": {"data": {"parsed": {"info": {}}}}},
    ]}}
    assert parse_token_balance(body) == 15.0
    assert parse_token_balance({"result": {"value": []}}) == 0.0
    assert parse_token_balance({"error": {}}) is None
    assert parse_token_balance(None) is None
