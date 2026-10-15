"""Buy / sell execution (skeleton)."""
from __future__ import annotations

from typing import Any

from agent.config import Settings
from agent.utils.logger import setup_logger

log = setup_logger("trader")


class Trader:
    def __init__(self, settings: Settings):
        self.s = settings

    async def buy(self, token: dict[str, Any], size: float) -> str | None:
        """
        Execute buy on bonding curve (four.meme / Flap) atau PCS setelah graduate.

        TODO:
        - four.meme → TokenManager2 buy
        - Flap → Portal swapExactInput
        - Support BNB + USDT quote
        """
        log.info("[SIM] BUY %s size=%.4f (not real yet)", token.get("symbol"), size)
        return "0xSIMULATED_TX"

    async def sell(self, token: dict[str, Any], amount: float) -> str | None:
        log.info("[SIM] SELL %s amount=%.4f (not real yet)", token.get("symbol"), amount)
        return "0xSIMULATED_TX"
