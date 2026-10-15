"""
Fully autonomous entry point.

Loop:
1. Scan new listings (four.meme + Flap)
2. Apply anti-rug filters
3. Score & rank
4. Execute buy if criteria met (respect risk limits)
5. Manage open positions (TP / SL / trailing / rug signal)
"""
from __future__ import annotations

import asyncio
import json
import signal
import sys
from pathlib import Path

from agent.config import get_settings
from agent.utils.logger import setup_logger

log = setup_logger("snipbot")
STATE_FILE = Path(__file__).resolve().parent.parent / "agent_state.json"
RUNNING = True


def handle_sig(sig, frame):
    global RUNNING
    log.info("Shutdown signal received...")
    RUNNING = False


async def run_loop() -> None:
    settings = get_settings()
    log.info("SnipBot BNB starting — fully autonomous")
    log.info("Network: %s | Max trade: %.1f%% | Volume window: $%.0f–$%.0f",
             settings.network,
             settings.max_trade_pct * 100,
             settings.min_volume_usd,
             settings.max_volume_usd)

    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())
        log.info("Loaded agent_id=%s wallet=%s", state.get("agent_id"), state.get("wallet"))
    else:
        log.warning("agent_state.json belum ada — jalankan python -m agent.register dulu")

    # Lazy import biar register tetap ringan
    from agent.scanner.fourmeme import FourMemeScanner
    from agent.scanner.flap import FlapScanner
    from agent.filters.antirug import AntiRugFilter
    from agent.portfolio.manager import PortfolioManager
    from agent.execution.trader import Trader

    four = FourMemeScanner(settings)
    flap = FlapScanner(settings)
    antirug = AntiRugFilter(settings)
    portfolio = PortfolioManager(settings)
    trader = Trader(settings)

    while RUNNING:
        try:
            # 1. Scan
            new_tokens = []
            new_tokens.extend(await four.fetch_new())
            new_tokens.extend(await flap.fetch_new())

            if new_tokens:
                log.info("Found %d new candidates", len(new_tokens))

            # 2. Filter + score
            candidates = []
            for t in new_tokens:
                score, reasons = await antirug.evaluate(t)
                if score >= 60:  # threshold sementara
                    t["score"] = score
                    t["reasons"] = reasons
                    candidates.append(t)

            candidates.sort(key=lambda x: x["score"], reverse=True)

            # 3. Execute (respect risk)
            for t in candidates[:3]:  # top 3 per cycle
                if not portfolio.can_open_position(t):
                    continue
                size = portfolio.position_size(t)
                if size <= 0:
                    continue
                log.info("SNIPE %s score=%s size=%.4f | %s",
                         t.get("symbol"), t["score"], size, t.get("address"))
                tx = await trader.buy(t, size)
                if tx:
                    portfolio.open_position(t, size, tx)

            # 4. Manage open positions
            await portfolio.manage_open(trader)

        except Exception as e:
            log.exception("Loop error: %s", e)

        await asyncio.sleep(8)  # cycle interval

    log.info("Agent stopped cleanly")


def main() -> None:
    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)
    try:
        asyncio.run(run_loop())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
