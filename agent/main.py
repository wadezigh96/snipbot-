"""
Fully autonomous entry point.
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account

load_dotenv()

from agent.config import get_settings
from agent.utils.logger import setup_logger

log = setup_logger("snipbot")
STATE_FILE = Path(__file__).resolve().parent.parent / "agent_state.json"
RUNNING = True


def handle_sig(sig, frame):
    global RUNNING
    log.info("Shutdown signal received...")
    RUNNING = False


def build_w3(settings) -> Web3:
    rpc = settings.rpc_url
    if not rpc:
        rpc = (
            "https://bsc-dataseed.binance.org"
            if settings.is_mainnet
            else "https://data-seed-prebsc-1-s1.bnbchain.org:8545"
        )
    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        raise RuntimeError(f"Cannot connect to RPC: {rpc}")
    return w3


def load_account(settings) -> Account:
    pk = settings.private_key or os.getenv("PRIVATE_KEY")
    if not pk:
        raise RuntimeError("PRIVATE_KEY required in .env for trading")
    if not pk.startswith("0x"):
        pk = "0x" + pk
    return Account.from_key(pk)


async def run_loop() -> None:
    settings = get_settings()
    log.info("SnipBot BNB starting — fully autonomous")
    log.info(
        "Network: %s | Max trade: %.1f%% | Volume: $%.0f–$%.0f",
        settings.network,
        settings.max_trade_pct * 100,
        settings.min_volume_usd,
        settings.max_volume_usd,
    )

    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())
        log.info("agent_id=%s wallet=%s", state.get("agent_id"), state.get("wallet"))
    else:
        log.warning("agent_state.json missing — run python -m agent.register first")

    w3 = build_w3(settings)
    account = load_account(settings)
    log.info("Trader wallet: %s | balance: %.4f BNB",
             account.address, w3.from_wei(w3.eth.get_balance(account.address), "ether"))

    from agent.scanner.fourmeme import FourMemeScanner
    from agent.scanner.flap import FlapScanner
    from agent.filters.antirug import AntiRugFilter
    from agent.portfolio.manager import PortfolioManager
    from agent.execution.trader import Trader

    four = FourMemeScanner(settings, w3)
    flap = FlapScanner(settings, w3)
    antirug = AntiRugFilter(settings, w3)
    portfolio = PortfolioManager(settings, w3, account.address)
    trader = Trader(settings, w3, account)

    while RUNNING:
        try:
            new_tokens = []
            new_tokens.extend(await four.fetch_new())
            new_tokens.extend(await flap.fetch_new())

            if new_tokens:
                log.info("Candidates this cycle: %d", len(new_tokens))

            candidates = []
            for t in new_tokens:
                score, reasons = await antirug.evaluate(t)
                t["score"] = score
                t["reasons"] = reasons
                if score >= 58:
                    candidates.append(t)
                    log.info(
                        "PASS %s score=%d | %s | %s",
                        t.get("symbol"), score, t.get("platform"), ",".join(reasons),
                    )

            candidates.sort(key=lambda x: x["score"], reverse=True)

            for t in candidates[:2]:
                if not portfolio.can_open_position(t):
                    continue
                size = portfolio.position_size(t)
                if size <= 0:
                    continue
                log.info("SNIPE %s score=%s size=%.4f BNB",
                         t.get("symbol"), t["score"], size)
                tx = await trader.buy(t, size)
                if tx:
                    portfolio.open_position(t, size, tx)

            await portfolio.manage_open(trader)

        except Exception as e:
            log.exception("Loop error: %s", e)

        await asyncio.sleep(6)

    log.info("Agent stopped")


def main() -> None:
    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)
    try:
        asyncio.run(run_loop())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
