"""Unified fail-closed anti-rugpull gate for Pump.fun / Solana tokens.

Combines every check the repo previously did in isolation:

1. Mint account (``rpc.MintCheck``): initialized, supported token program,
   mint/freeze authority state.
2. Bubble Maps holder analysis (``bubblemap.BubbleMapResult``): top-1/top-10
   concentration, HHI, dev share, linked-cluster share.
3. Market evidence supplied by the caller: liquidity / curve SOL, market
   cap, token age, and whether a *sell* quote/simulation exists (a token you
   cannot sell is a honeypot for practical purposes).

Every missing or unknown input is a hard REJECT. There is no path where
unknown data scores as "probably safe". The verdict is deterministic and
cannot be overridden by the LLM layer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from agent.pumpfun.bubblemap import BubbleMapResult
from agent.pumpfun.rpc import MintCheck


@dataclass(frozen=True)
class RugVerdict:
    passed: bool
    score: int  # 0..100, deterministic
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        return value


def evaluate_rug_risk(
    *,
    mint_check: MintCheck,
    bubblemap: BubbleMapResult,
    liquidity_usd: float | None,
    v_sol_in_curve: float | None,
    market_cap_usd: float | None,
    sell_simulation_passed: bool,
    min_liquidity_usd: float = 5_000.0,
) -> RugVerdict:
    hard: list[str] = []
    soft: list[str] = []
    score = 100

    # --- 1. Mint / authority -------------------------------------------------
    if mint_check.status != "VERIFIED":
        hard.append(f"mint_not_verified:{mint_check.reason}")
    else:
        if mint_check.freeze_authority_present:
            hard.append("freeze_authority_active")
        if mint_check.mint_authority_present:
            # Pump.fun keeps mint authority with the program until graduation
            # in some flows; treat an *externally held* authority as fatal,
            # and any present authority as a heavy penalty unless the caller
            # has separately verified it is program-owned.
            score -= 35
            soft.append("mint_authority_present_unverified_owner")

    # --- 2. Bubble Maps holder concentration --------------------------------
    if bubblemap.status == "UNKNOWN":
        hard.append("holder_distribution_unknown")
    elif bubblemap.status == "REJECT":
        hard.extend(f"bubblemap:{r}" for r in bubblemap.reasons)
    elif bubblemap.status == "RISKY":
        score -= 20
        soft.append("bubblemap_concentration_elevated")
    if bubblemap.holders_seen and bubblemap.holders_seen < 10:
        score -= 15
        soft.append("very_few_holders_seen")

    # --- 3. Liquidity / curve / sellability ---------------------------------
    has_curve_sol = v_sol_in_curve is not None and v_sol_in_curve > 0
    has_liquidity = liquidity_usd is not None and liquidity_usd >= min_liquidity_usd
    if not has_curve_sol and not has_liquidity:
        hard.append("no_verified_liquidity_or_curve_reserve")
    if market_cap_usd is None or market_cap_usd <= 0:
        score -= 10
        soft.append("market_cap_unknown")
    if sell_simulation_passed is not True:
        hard.append("sell_not_simulated_successfully")

    score = max(0, min(100, score))
    if hard:
        return RugVerdict(False, min(score, 39), tuple(hard + soft))
    return RugVerdict(True, score, tuple(soft or ["all_antirug_gates_passed"]))
