from agent.pumpfun.antirug import RugVerdict
from agent.pumpfun.llm_sniper import final_decision, parse_sniper_json

PASS = RugVerdict(True, 90, ("all_antirug_gates_passed",))
FAIL = RugVerdict(False, 10, ("freeze_authority_active",))


def test_parse_valid():
    assert parse_sniper_json('{"decision":"APPROVE_PAPER","score":85,"reason":"clean"}') == (
        "APPROVE_PAPER", 85, "clean")


def test_parse_malformed_fails_closed():
    assert parse_sniper_json("buy it now")[0] == "WATCH"
    assert parse_sniper_json('{"decision":"BUY_LIVE","score":99,"reason":"x"}')[0] == "WATCH"
    assert parse_sniper_json('{"decision":"APPROVE_PAPER","score":101,"reason":"x"}')[0] == "WATCH"


def test_llm_cannot_override_antirug_failure():
    d = final_decision(FAIL, ("APPROVE_PAPER", 99, "great"))
    assert d.status == "REJECTED"


def test_approve_needs_score_threshold():
    assert final_decision(PASS, ("APPROVE_PAPER", 85, "ok")).status == "PAPER_BUY_CANDIDATE"
    assert final_decision(PASS, ("APPROVE_PAPER", 50, "meh")).status == "WATCH_ONLY"
    assert final_decision(PASS, ("WATCH", 90, "wait")).status == "WATCH_ONLY"
    assert final_decision(PASS, ("REJECT", 90, "no")).status == "REJECTED"
