"""Deterministic pre-trade risk gate for PumpFun automation.

This module never signs or broadcasts transactions. It only decides whether a
candidate may proceed to the separately implemented quote/simulation/executor.
Missing or invalid evidence fails closed. LLM output cannot override this gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class RiskLimits:
    max_buy_sol: Decimal = Decimal("0.05")
    max_daily_loss_sol: Decimal = Decimal("0.10")
    min_liquidity_sol: Decimal = Decimal("20")
    max_holder_concentration_pct: Decimal = Decimal("20")
    max_creator_holding_pct: Decimal = Decimal("5")
    max_slippage_bps: int = 300
    max_open_positions: int = 2


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    status: str
    reasons: tuple[str, ...]


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return result if result.is_finite() else None


def evaluate_pretrade(
    evidence: dict[str, Any],
    *,
    limits: RiskLimits = RiskLimits(),
    live_enabled: bool = False,
) -> RiskDecision:
    """Validate deterministic evidence before a candidate reaches an executor.

    Required evidence: mint_status, liquidity_sol, holder_concentration_pct,
    creator_holding_pct, sell_quote_ok, simulation_ok, slippage_bps,
    buy_amount_sol, daily_pnl_sol, open_positions, llm_status.

    The LLM may only contribute WATCH/REJECT triage. It is never treated as
    proof of safety. This gate is not a guarantee against rug pulls or losses.
    """
    if not isinstance(evidence, dict):
        return RiskDecision(False, "REJECT", ("evidence_not_object",))

    reasons: list[str] = []
    required = (
        "mint_status", "liquidity_sol", "holder_concentration_pct",
        "creator_holding_pct", "sell_quote_ok", "simulation_ok",
        "slippage_bps", "buy_amount_sol", "daily_pnl_sol",
        "open_positions", "llm_status",
    )
    missing = [key for key in required if key not in evidence]
    if missing:
        return RiskDecision(False, "REJECT", tuple(f"missing_{key}" for key in missing))

    # Fail closed on any token program/mint state not fully understood.
    if evidence["mint_status"] != "VERIFIED":
        reasons.append("mint_not_verified")
    # WATCH means only that the LLM did not reject; it does not mean safe.
    if evidence["llm_status"] != "WATCH":
        reasons.append("llm_did_not_return_watch")

    liquidity = _decimal(evidence["liquidity_sol"])
    concentration = _decimal(evidence["holder_concentration_pct"])
    creator_holding = _decimal(evidence["creator_holding_pct"])
    buy_amount = _decimal(evidence["buy_amount_sol"])
    daily_pnl = _decimal(evidence["daily_pnl_sol"])
    slippage = evidence["slippage_bps"]
    positions = evidence["open_positions"]

    numeric = {
        "liquidity_sol": liquidity,
        "holder_concentration_pct": concentration,
        "creator_holding_pct": creator_holding,
        "buy_amount_sol": buy_amount,
        "daily_pnl_sol": daily_pnl,
    }
    for key, value in numeric.items():
        if value is None:
            reasons.append(f"invalid_{key}")

    if liquidity is not None and liquidity < limits.min_liquidity_sol:
        reasons.append("liquidity_below_minimum")
    if concentration is not None and not Decimal("0") <= concentration <= Decimal("100"):
        reasons.append("holder_concentration_out_of_range")
    elif concentration is not None and concentration > limits.max_holder_concentration_pct:
        reasons.append("holder_concentration_too_high")
    if creator_holding is not None and not Decimal("0") <= creator_holding <= Decimal("100"):
        reasons.append("creator_holding_out_of_range")
    elif creator_holding is not None and creator_holding > limits.max_creator_holding_pct:
        reasons.append("creator_holding_too_high")
    if buy_amount is not None and (buy_amount <= 0 or buy_amount > limits.max_buy_sol):
        reasons.append("buy_amount_out_of_limits")
    if daily_pnl is not None and daily_pnl <= -limits.max_daily_loss_sol:
        reasons.append("daily_loss_limit_reached")
    if isinstance(slippage, bool) or not isinstance(slippage, int) or slippage < 0:
        reasons.append("invalid_slippage_bps")
    elif slippage > limits.max_slippage_bps:
        reasons.append("slippage_above_limit")
    if isinstance(positions, bool) or not isinstance(positions, int) or positions < 0:
        reasons.append("invalid_open_positions")
    elif positions >= limits.max_open_positions:
        reasons.append("max_open_positions_reached")
    if evidence["sell_quote_ok"] is not True:
        reasons.append("sell_quote_not_confirmed")
    if evidence["simulation_ok"] is not True:
        reasons.append("transaction_simulation_failed")

    if reasons:
        return RiskDecision(False, "REJECT", tuple(reasons))
    if not live_enabled:
        return RiskDecision(True, "PAPER_ONLY", ("pretrade_checks_passed_live_execution_disabled",))
    return RiskDecision(True, "READY_FOR_EXECUTOR", ("pretrade_checks_passed",))
