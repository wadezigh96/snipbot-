"""four.meme new token scanner (skeleton)."""
from __future__ import annotations

from typing import Any

from agent.config import Settings
from agent.utils.logger import setup_logger

log = setup_logger("scanner.fourmeme")


class FourMemeScanner:
    """
    Skeleton scanner for four.meme.

    Real implementation options:
    - Poll four.meme public API (POST /public/token/search type=NEW)
    - Subscribe Bitquery / Codex websocket for TokenCreated
    - Index TokenManager2 events on-chain
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.seen: set[str] = set()

    async def fetch_new(self) -> list[dict[str, Any]]:
        # TODO: implement real fetch
        # Contoh shape yang diharapkan:
        # {
        #   "address": "0x...",
        #   "symbol": "PEPE",
        #   "name": "Pepe",
        #   "platform": "four.meme",
        #   "created_at": 1729...,
        #   "liquidity_usd": 4200,
        #   "volume_usd": 9500,
        #   "price_usd": 0.000012,
        #   "holders": 87,
        #   "lp_burned": True,
        #   "deployer": "0x...",
        # }
        log.debug("four.meme scan cycle (skeleton — no real data yet)")
        return []
