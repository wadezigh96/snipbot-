"""Fail-closed pre-trade limits for PumpFun FOMO Radar.

This module does not sign, build, or broadcast transactions. Dollar amounts are
estimates supplied by a caller and must be backed by fresh market/RPC data.
Persistent accounting and transaction reconciliation are required before live use.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class RiskPolicy:
    bankroll_usd: float = 10.0
    max_position_usd: float = 1.0
    max_open_positions: int = 2
    daily_loss_limit_usd: float = 1.0
    sol_reserve_usd: float = 1.50

    def check_buy(
        self,
        *,
        position_usd: float,
        open_positions: int,
        open_exposure_usd: float,
        daily_realized_loss_usd: float,
        available_sol_usd: float,
        estimated_network_fee_usd: float,
        data_is_fresh: bool,
        quote_is_valid: bool,
        simulation_passed: bool,
    ) -> RiskDecision:
        """Return a decision; unknown, malformed, or unsafe values fail closed."""
        gates = (data_is_fresh, quote_is_valid, simulation_passed)
        if any(type(value) is not bool for value in gates):
            return RiskDecision(False, "invalid_boolean_gate")

        numbers = (
            position_usd,
            open_exposure_usd,
            daily_realized_loss_usd,
            available_sol_usd,
            estimated_network_fee_usd,
        )
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in numbers):
            return RiskDecision(False, "invalid_numeric_input")
        if any(not math.isfinite(v) for v in numbers):
            return RiskDecision(False, "non_finite_numeric_input")
        if isinstance(open_positions, bool) or not isinstance(open_positions, int) or open_positions < 0:
            return RiskDecision(False, "invalid_open_position_count")
        if open_exposure_usd < 0:
            return RiskDecision(False, "invalid_open_exposure")
        if position_usd <= 0:
            return RiskDecision(False, "position_must_be_positive")
        if position_usd > self.max_position_usd:
            return RiskDecision(False, "position_limit_exceeded")
        if open_positions >= self.max_open_positions:
            return RiskDecision(False, "open_position_limit_reached")
        if open_exposure_usd + position_usd > self.bankroll_usd:
            return RiskDecision(False, "total_exposure_limit_exceeded")
        if daily_realized_loss_usd < 0:
            return RiskDecision(False, "loss_input_must_be_nonnegative")
        if daily_realized_loss_usd >= self.daily_loss_limit_usd:
            return RiskDecision(False, "daily_loss_limit_reached")
        if available_sol_usd <= 0 or estimated_network_fee_usd < 0:
            return RiskDecision(False, "invalid_fee_or_sol_balance")
        if available_sol_usd - position_usd - estimated_network_fee_usd < self.sol_reserve_usd:
            return RiskDecision(False, "sol_fee_reserve_would_be_breached")
        if position_usd > self.bankroll_usd:
            return RiskDecision(False, "bankroll_limit_exceeded")
        if not data_is_fresh:
            return RiskDecision(False, "market_data_stale_or_unknown")
        if not quote_is_valid:
            return RiskDecision(False, "quote_missing_or_invalid")
        if not simulation_passed:
            return RiskDecision(False, "transaction_simulation_not_passed")
        return RiskDecision(True, "risk_checks_passed")
