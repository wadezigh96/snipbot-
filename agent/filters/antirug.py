"""Anti-rug filter — LP burn → holder/dev → volume."""
from __future__ import annotations

from typing import Any

from web3 import Web3

from agent.config import Settings
from agent.contracts import TOKEN_MANAGER_HELPER3, HELPER3_ABI
from agent.utils.logger import setup_logger

log = setup_logger("filter.antirug")


class AntiRugFilter:
    def __init__(self, settings: Settings, w3: Web3 | None = None):
        self.s = settings
        self.w3 = w3

    async def evaluate(self, token: dict[str, Any]) -> tuple[int, list[str]]:
        score = 40
        reasons: list[str] = []

        # Enrich from on-chain if possible
        if self.w3 and token.get("platform") == "four.meme":
            try:
                await self._enrich_fourmeme(token)
            except Exception as e:
                log.debug("enrich fail %s: %s", token.get("symbol"), e)

        # --- 1. LP / liquidity (highest priority) ---
        liq = float(token.get("liquidity_usd") or 0)
        lp_burned = bool(token.get("lp_burned") or token.get("liquidity_added"))
        progress = float(token.get("progress") or 0)

        if lp_burned or token.get("liquidity_added"):
            score += 22
            reasons.append("lp_burned_or_added")
        elif liq >= self.s.min_liquidity_usd:
            score += 12
            reasons.append("liq_ok")
        elif progress > 0.3:  # already raising
            score += 6
            reasons.append("raising")
        else:
            score -= 18
            reasons.append("liq_low")

        # --- 2. Holder / dev concentration ---
        holders = int(token.get("holders") or 0)
        top10_pct = float(token.get("top10_pct") or 80)
        dev_pct = float(token.get("dev_pct") or 30)

        if holders >= 40 and top10_pct < 30 and dev_pct < 5:
            score += 20
            reasons.append("holders_excellent")
        elif holders >= 20 and top10_pct < 45:
            score += 10
            reasons.append("holders_ok")
        elif holders > 0 and holders < 10:
            score -= 15
            reasons.append("few_holders")
        else:
            # unknown holders — mild penalty
            score -= 5
            reasons.append("holders_unknown")

        # Deployer red flags (simple)
        deployer = (token.get("deployer") or "").lower()
        if deployer and deployer in getattr(self, "_bad_deployers", set()):
            score -= 30
            reasons.append("bad_deployer")

        # --- 3. Volume window ---
        vol = float(token.get("volume_usd") or 0)
        if self.s.min_volume_usd <= vol <= self.s.max_volume_usd:
            score += 16
            reasons.append("volume_sweet")
        elif 0 < vol < self.s.min_volume_usd:
            score -= 8
            reasons.append("volume_low")
        elif vol > self.s.max_volume_usd:
            score -= 4
            reasons.append("volume_hot")
        else:
            # brand new, no volume yet — acceptable for sniper
            score += 2
            reasons.append("fresh")

        score = max(0, min(100, int(score)))
        return score, reasons

    async def _enrich_fourmeme(self, token: dict) -> None:
        if not self.w3:
            return
        helper = self.w3.eth.contract(
            address=Web3.to_checksum_address(TOKEN_MANAGER_HELPER3),
            abi=HELPER3_ABI,
        )
        info = helper.functions.getTokenInfo(Web3.to_checksum_address(token["address"])).call()
        # version, tokenManager, quote, lastPrice, tradingFeeRate, minTradingFee,
        # launchTime, offers, maxOffers, funds, maxFunds, liquidityAdded
        token["liquidity_added"] = bool(info[11])
        token["lp_burned"] = bool(info[11])  # after migrate LP is locked/burned typically
        if info[9] and info[10]:  # funds / maxFunds
            token["progress"] = float(info[9]) / float(info[10]) if info[10] else 0
        token["onchain_price"] = info[3]
        token["offers"] = info[7]
