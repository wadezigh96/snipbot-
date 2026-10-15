"""Anti-rug filter — priority: LP burn → holder/dev → volume."""
from __future__ import annotations

from typing import Any

from agent.config import Settings
from agent.utils.logger import setup_logger

log = setup_logger("filter.antirug")


class AntiRugFilter:
    def __init__(self, settings: Settings):
        self.s = settings

    async def evaluate(self, token: dict[str, Any]) -> tuple[int, list[str]]:
        """
        Return (score 0-100, list of reason tags).
        Priority order sesuai permintaan:
        1. Liquidity / LP burn
        2. Holder / dev concentration (bubblemap style)
        3. Volume window
        """
        score = 40
        reasons: list[str] = []

        # --- 1. LP burn / liquidity ---
        liq = float(token.get("liquidity_usd") or 0)
        lp_burned = bool(token.get("lp_burned"))

        if lp_burned:
            score += 20
            reasons.append("lp_burned")
        elif liq >= self.s.min_liquidity_usd:
            score += 10
            reasons.append("liq_ok")
        else:
            score -= 25
            reasons.append("liq_low")

        # --- 2. Holder / dev concentration ---
        # Placeholder: real version pakai bubblemap / holder API
        top10_pct = float(token.get("top10_pct") or 100)
        dev_pct = float(token.get("dev_pct") or 50)
        holders = int(token.get("holders") or 0)

        if holders >= 50 and top10_pct < 35 and dev_pct < 8:
            score += 18
            reasons.append("holders_healthy")
        elif holders >= 20 and top10_pct < 50:
            score += 8
            reasons.append("holders_ok")
        else:
            score -= 20
            reasons.append("holder_risk")

        # --- 3. Volume window ---
        vol = float(token.get("volume_usd") or 0)
        if self.s.min_volume_usd <= vol <= self.s.max_volume_usd:
            score += 15
            reasons.append("volume_sweet")
        elif vol < self.s.min_volume_usd:
            score -= 10
            reasons.append("volume_low")
        else:
            # terlalu panas, bisa late
            score -= 5
            reasons.append("volume_high")

        score = max(0, min(100, score))
        return score, reasons
