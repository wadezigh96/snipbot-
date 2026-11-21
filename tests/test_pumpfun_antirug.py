from agent.pumpfun.antirug import evaluate_rug_risk
from agent.pumpfun.bubblemap import analyze_holders
from agent.pumpfun.rpc import MintCheck

GOOD_MINT = MintCheck("VERIFIED", "mint", "mint_layout_valid", decimals=6,
                      mint_authority_present=False, freeze_authority_present=False)
GOOD_HOLDERS = analyze_holders([(f"w{i}", 10.0) for i in range(50)], total_supply=1000.0)


def base(**over):
    kw = dict(mint_check=GOOD_MINT, bubblemap=GOOD_HOLDERS, liquidity_usd=20_000.0,
              v_sol_in_curve=30.0, market_cap_usd=50_000.0, sell_simulation_passed=True)
    kw.update(over)
    return evaluate_rug_risk(**kw)


def test_all_gates_pass():
    v = base()
    assert v.passed and v.score >= 70


def test_freeze_authority_rejected():
    mint = MintCheck("VERIFIED", "m", "x", mint_authority_present=False, freeze_authority_present=True)
    assert not base(mint_check=mint).passed


def test_unknown_mint_rejected():
    mint = MintCheck("UNKNOWN", "m", "solana_rpc_not_configured")
    assert not base(mint_check=mint).passed


def test_unknown_holders_rejected():
    from agent.pumpfun.bubblemap import analyze_holders as ah
    assert not base(bubblemap=ah([])).passed


def test_no_sell_simulation_rejected():
    assert not base(sell_simulation_passed=False).passed


def test_no_liquidity_rejected():
    assert not base(liquidity_usd=None, v_sol_in_curve=None).passed


def test_concentrated_holders_rejected():
    from agent.pumpfun.bubblemap import analyze_holders as ah
    bad = ah([("whale", 900.0), ("a", 50.0)], total_supply=1000.0)
    assert not base(bubblemap=bad).passed
