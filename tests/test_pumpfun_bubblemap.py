from agent.pumpfun.bubblemap import analyze_holders, analyze_holder_dicts


def test_dispersed_holders_ok():
    holders = [(f"w{i}", 10.0) for i in range(50)]
    r = analyze_holders(holders, total_supply=1000.0)
    assert r.status == "OK"
    assert r.top1_pct == 1.0
    assert r.top10_pct == 10.0


def test_top1_whale_rejected():
    holders = [("whale", 500.0)] + [(f"w{i}", 10.0) for i in range(20)]
    r = analyze_holders(holders, total_supply=1000.0)
    assert r.status == "REJECT"
    assert r.top1_pct == 50.0


def test_linked_cluster_rejected_even_if_wallets_look_small():
    wallets = [f"c{i}" for i in range(8)]
    holders = [(w, 50.0) for w in wallets] + [(f"w{i}", 10.0) for i in range(20)]
    r = analyze_holders(holders, total_supply=1000.0, clusters=[wallets])
    assert r.status == "REJECT"
    assert r.largest_cluster_pct == 40.0


def test_dev_share_rejected():
    holders = [("dev", 150.0)] + [(f"w{i}", 10.0) for i in range(30)]
    r = analyze_holders(holders, total_supply=1000.0, dev_wallet="dev")
    assert r.status == "REJECT"
    assert r.dev_pct == 15.0


def test_no_data_is_unknown_never_safe():
    r = analyze_holders([])
    assert r.status == "UNKNOWN"


def test_evm_holder_dicts_adapter():
    holders = [{"address": f"0x{i:040x}", "balance": 10.0} for i in range(50)]
    r = analyze_holder_dicts(holders, total_supply=1000.0)
    assert r.status == "OK"
    assert r.holders_seen == 50


def test_bonding_curve_account_excluded():
    # Curve holds 850 of 1000 supply by design; real holders are dispersed.
    holders = [("curve", 850.0)] + [(f"w{i}", 3.0) for i in range(50)]
    r = analyze_holders(holders, total_supply=1000.0, exclude_owners={"curve"})
    assert r.status == "OK"
    assert r.top1_pct == 2.0  # 3 / (1000-850)
    without = analyze_holders(holders, total_supply=1000.0)
    assert without.status == "REJECT"  # curve alone would look like a whale
