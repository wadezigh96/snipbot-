"""Paper-trading engine + micro-bankroll plan ($5 preset).

Why paper first: with a $5 bankroll, live fees and one rug erase the account
before any strategy can be evaluated. This engine simulates entries/exits
with realistic costs so the $5 -> target path can be measured honestly
before a single real transaction exists.

Exit ladder (fractions of the *original* position):
- stop loss at -45%
- TP1 at +100% (2x): sell 50%, move stop to break-even
- TP2 at +400% (5x): sell 25% of original
- TP3 at +900% (10x): sell whatever remains
- time stop: close whatever remains after ``max_hold_hours``

Costs modelled per swap: 1% trade fee + $0.02 network/priority estimate.
Accounting is plain cash: opening deducts principal + cost from cash,
selling adds proceeds - cost back to cash. All amounts USD.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

SWAP_FEE_PCT = 0.01
NETWORK_FEE_USD = 0.02


@dataclass(frozen=True)
class MicroPlan:
    bankroll_usd: float = 5.0
    position_usd: float = 1.0
    max_open_positions: int = 3
    daily_loss_limit_usd: float = 1.50
    fee_reserve_usd: float = 0.75
    target_usd: float = 1500.0

    def validate(self) -> None:
        if self.bankroll_usd <= 0 or self.position_usd <= 0:
            raise ValueError("bankroll and position must be positive")
        if self.position_usd > self.bankroll_usd - self.fee_reserve_usd:
            raise ValueError("position leaves no fee reserve")
        if self.max_open_positions * self.position_usd > self.bankroll_usd:
            raise ValueError("max open positions exceed bankroll")


def target_math(plan: MicroPlan) -> dict[str, float]:
    """The honest arithmetic behind a $5 -> $1,500 target (300x).

    Per-trade compounded return needed at several trade counts, assuming
    *every* trade wins — which real trading never does. The target is a
    moonshot to measure against, not a forecast.
    """
    multiple = plan.target_usd / plan.bankroll_usd
    out: dict[str, float] = {"multiple_needed": multiple}
    for trades in (10, 20, 50, 100):
        out[f"win_return_needed_per_trade_{trades}"] = multiple ** (1.0 / trades) - 1.0
    return out


@dataclass
class PaperPosition:
    mint: str
    entry_price: float
    amount_usd: float
    opened_at: float
    remaining_fraction: float = 1.0
    stop_price: float = 0.0
    tp_stage: int = 0
    closed: bool = False

    def __post_init__(self) -> None:
        self.stop_price = self.entry_price * 0.55  # -45%


@dataclass
class PaperEngine:
    plan: MicroPlan = field(default_factory=MicroPlan)
    max_hold_hours: float = 6.0
    positions: list[PaperPosition] = field(default_factory=list)
    cash_usd: float = field(init=False)

    def __post_init__(self) -> None:
        self.plan.validate()
        self.cash_usd = self.plan.bankroll_usd

    @staticmethod
    def _cost(gross_usd: float) -> float:
        return gross_usd * SWAP_FEE_PCT + NETWORK_FEE_USD

    def open(self, mint: str, price: float, *, now: float) -> PaperPosition | None:
        open_positions = [p for p in self.positions if not p.closed]
        if len(open_positions) >= self.plan.max_open_positions:
            return None
        total_cost = self.plan.position_usd + self._cost(self.plan.position_usd)
        if total_cost > self.cash_usd - 0.0 or self.cash_usd - total_cost < 0:
            return None
        # Keep the fee reserve untouched for future exits.
        if self.cash_usd - total_cost < self.plan.fee_reserve_usd and open_positions:
            return None
        if price <= 0 or not math.isfinite(price):
            return None
        self.cash_usd -= total_cost
        position = PaperPosition(mint=mint, entry_price=price,
                                 amount_usd=self.plan.position_usd, opened_at=now)
        self.positions.append(position)
        return position

    def _sell(self, position: PaperPosition, price: float, fraction: float) -> None:
        fraction = min(fraction, position.remaining_fraction)
        if fraction <= 0:
            return
        gross = position.amount_usd * fraction * (price / position.entry_price)
        self.cash_usd += gross - self._cost(gross)
        position.remaining_fraction -= fraction
        if position.remaining_fraction <= 1e-9:
            position.remaining_fraction = 0.0
            position.closed = True

    def update(self, position: PaperPosition, price: float, *, now: float) -> str:
        """Advance one position with a fresh price; returns an action label."""
        if position.closed or price <= 0 or not math.isfinite(price):
            return "hold"
        age_hours = (now - position.opened_at) / 3600.0
        if price <= position.stop_price:
            self._sell(position, price, position.remaining_fraction)
            return "stop_loss"
        multiple = price / position.entry_price
        if position.tp_stage == 0 and multiple >= 2.0:
            self._sell(position, price, 0.50)
            position.tp_stage = 1
            position.stop_price = position.entry_price  # break-even stop
            return "tp1_sell_50pct_breakeven_stop"
        if position.tp_stage == 1 and multiple >= 5.0:
            self._sell(position, price, 0.25)
            position.tp_stage = 2
            return "tp2_sell_25pct"
        if position.tp_stage == 2 and multiple >= 10.0:
            self._sell(position, price, position.remaining_fraction)
            return "tp3_sell_rest"
        if age_hours >= self.max_hold_hours:
            self._sell(position, price, position.remaining_fraction)
            return "time_stop"
        return "hold"

    def equity_usd(self, prices: dict[str, float]) -> float:
        total = self.cash_usd
        for p in self.positions:
            if not p.closed and p.remaining_fraction > 0:
                price = prices.get(p.mint, p.entry_price)
                total += p.amount_usd * p.remaining_fraction * (price / p.entry_price)
        return round(total, 6)
