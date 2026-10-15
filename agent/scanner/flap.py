"""Flap new token scanner (skeleton)."""
from __future__ import annotations

from typing import Any

from agent.config import Settings
from agent.utils.logger import setup_logger

log = setup_logger("scanner.flap")


class FlapScanner:
    """
    Skeleton scanner for Flap.

    Real implementation:
    - Index Portal TokenCreated events (0xe2cE6ab80874Fa9Fa2aAE65D277Dd6B8e65C9De0)
    - Atau pakai shrine.trade / docs.flap.sh websocket
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.seen: set[str] = set()

    async def fetch_new(self) -> list[dict[str, Any]]:
        log.debug("Flap scan cycle (skeleton — no real data yet)")
        return []
