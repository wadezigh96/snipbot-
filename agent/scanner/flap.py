"""Flap scanner — Portal TokenCreated events."""
from __future__ import annotations

import time
from typing import Any

from web3 import Web3

from agent.config import Settings
from agent.contracts import FLAP_PORTAL, FLAP_PORTAL_ABI
from agent.utils.logger import setup_logger

log = setup_logger("scanner.flap")


class FlapScanner:
    def __init__(self, settings: Settings, w3: Web3 | None = None):
        self.settings = settings
        self.w3 = w3
        self.seen: set[str] = set()
        self._last_block: int | None = None

    async def fetch_new(self) -> list[dict[str, Any]]:
        if not self.w3:
            log.debug("Flap: no web3, skip")
            return []

        try:
            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(FLAP_PORTAL),
                abi=FLAP_PORTAL_ABI,
            )
            latest = self.w3.eth.block_number
            from_block = self._last_block or max(latest - 80, 0)
            self._last_block = latest

            # TokenCreated event
            event_abi = next(e for e in FLAP_PORTAL_ABI if e.get("name") == "TokenCreated")
            logs = self.w3.eth.get_logs({
                "address": Web3.to_checksum_address(FLAP_PORTAL),
                "fromBlock": from_block,
                "toBlock": latest,
                "topics": [self.w3.keccak(text="TokenCreated(uint256,address,uint256,address,string,string,string)")],
            })

            out = []
            for log_entry in logs:
                try:
                    decoded = contract.events.TokenCreated().process_log(log_entry)
                    args = decoded["args"]
                    addr = args["token"].lower()
                    if addr in self.seen:
                        continue
                    self.seen.add(addr)
                    out.append({
                        "address": Web3.to_checksum_address(args["token"]),
                        "symbol": args.get("symbol") or "?",
                        "name": args.get("name") or "?",
                        "platform": "flap",
                        "created_at": int(args.get("ts") or time.time()),
                        "liquidity_usd": 0,
                        "volume_usd": 0,
                        "price_usd": 0,
                        "holders": 0,
                        "progress": 0,
                        "lp_burned": False,
                        "deployer": args.get("creator", ""),
                        "quote": "BNB",
                        "meta": args.get("meta"),
                    })
                except Exception:
                    continue

            if out:
                log.info("Flap new: %d", len(out))
            return out
        except Exception as e:
            log.warning("Flap events error: %s", e)
            return []
