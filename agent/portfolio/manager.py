"""Portfolio manager with real balance & risk limits."""
from __future__ import annotations

from typing import Any

from web3 import Web3

from agent.config import Settings
from agent.utils.logger import setup_logger

log = setup_logger("portfolio")


class PortfolioManager:
    def __init__(self, settings: Settings, w3: Web3 | None = None, address: str | None = None):
        self.s = settings
        self.w3 = w3
        self.address = address
        self.positions: dict[str, dict] = {}

    def wallet_bnb(self) -> float:
        if not self.w3 or not self.address:
            return 0.0
        bal = self.w3.eth.get_balance(Web3.to_checksum_address(self.address))
        return float(self.w3.from_wei(bal, "ether"))

    def can_open_position(self, token: dict[str, Any]) -> bool:
        addr = token.get("address", "").lower()
        if addr in self.positions:
            return False
        # exposure check
        open_value = sum(p.get("size_bnb", 0) for p in self.positions.values())
        bal = self.wallet_bnb()
        if bal <= 0:
            return False
        if (open_value / bal) >= self.s.max_total_exposure:
            log.info("Max exposure reached (%.1f%%)", self.s.max_total_exposure * 100)
            return False
        return True

    def position_size(self, token: dict[str, Any]) -> float:
        bal = self.wallet_bnb()
        if bal <= 0.01:
            return 0.0
        size = bal * self.s.max_trade_pct
        # leave some gas
        size = min(size, bal - 0.005)
        return round(max(size, 0), 6)

    def open_position(self, token: dict[str, Any], size: float, tx: str) -> None:
        addr = token["address"].lower()
        self.positions[addr] = {
            "token": token,
            "size_bnb": size,
            "entry_tx": tx,
            "status": "open",
            "opened_at": __import__("time").time(),
        }
        log.info("OPEN %s size=%.4f BNB tx=%s", token.get("symbol"), size, tx[:16])

    async def manage_open(self, trader) -> None:
        """Basic TP/SL skeleton — extend with price feeds later."""
        for addr, pos in list(self.positions.items()):
            if pos["status"] != "open":
                continue
            # TODO: fetch current price, apply TP 2x / SL -40% / rug re-score
            age = __import__("time").time() - pos["opened_at"]
            if age > 3600 * 6:  # hold max 6h example
                log.info("Position %s aged out — consider exit", pos["token"].get("symbol"))
