"""Portfolio manager — position sizing & risk."""
from __future__ import annotations

from typing import Any

from agent.config import Settings
from agent.utils.logger import setup_logger

log = setup_logger("portfolio")


class PortfolioManager:
    def __init__(self, settings: Settings):
        self.s = settings
        self.positions: dict[str, dict] = {}  # address -> position

    def can_open_position(self, token: dict[str, Any]) -> bool:
        addr = token.get("address", "").lower()
        if addr in self.positions:
            return False
        # TODO: cek total exposure vs max_total_exposure
        return True

    def position_size(self, token: dict[str, Any]) -> float:
        """Return size in quote (BNB or USDT). Skeleton pakai fixed % dari dummy balance."""
        # TODO: baca balance real dari wallet
        dummy_balance = 1.0  # 1 BNB placeholder
        size = dummy_balance * self.s.max_trade_pct
        return round(size, 6)

    def open_position(self, token: dict[str, Any], size: float, tx: str) -> None:
        addr = token["address"].lower()
        self.positions[addr] = {
            "token": token,
            "size": size,
            "entry_tx": tx,
            "status": "open",
        }
        log.info("Position opened %s size=%.4f tx=%s", token.get("symbol"), size, tx)

    async def manage_open(self, trader) -> None:
        """Check TP / SL / rug signal. Skeleton only."""
        for addr, pos in list(self.positions.items()):
            if pos["status"] != "open":
                continue
            # TODO: price check, TP/SL, anti-rug re-eval
            pass
