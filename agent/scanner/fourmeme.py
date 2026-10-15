"""four.meme scanner — API + on-chain TokenCreate events."""
from __future__ import annotations

import time
from typing import Any

import httpx
from web3 import Web3

from agent.config import Settings
from agent.contracts import TOKEN_MANAGER2, TOKEN_MANAGER2_ABI
from agent.utils.logger import setup_logger

log = setup_logger("scanner.fourmeme")

API_BASE = "https://four.meme/meme-api/v1"


class FourMemeScanner:
    def __init__(self, settings: Settings, w3: Web3 | None = None):
        self.settings = settings
        self.w3 = w3
        self.seen: set[str] = set()
        self._last_block: int | None = None

    async def fetch_new(self) -> list[dict[str, Any]]:
        tokens: list[dict[str, Any]] = []

        # 1) Public API — NEW listings
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                r = await client.post(
                    f"{API_BASE}/public/token/search",
                    json={
                        "type": "NEW",
                        "listType": "NOR",
                        "pageIndex": 1,
                        "pageSize": 30,
                        "status": "PUBLISH",
                        "sort": "DESC",
                    },
                    headers={"Accept": "application/json"},
                )
                if r.status_code == 200:
                    data = r.json()
                    items = data.get("data", {}).get("list") or data.get("data") or []
                    if isinstance(items, dict):
                        items = items.get("list", [])
                    for it in items:
                        addr = (it.get("address") or it.get("tokenAddress") or "").lower()
                        if not addr or addr in self.seen:
                            continue
                        self.seen.add(addr)
                        tokens.append(self._normalize_api(it))
        except Exception as e:
            log.warning("four.meme API error: %s", e)

        # 2) On-chain TokenCreate (more real-time)
        if self.w3:
            try:
                tokens.extend(await self._from_events())
            except Exception as e:
                log.warning("four.meme events error: %s", e)

        if tokens:
            log.info("four.meme new: %d", len(tokens))
        return tokens

    def _normalize_api(self, it: dict) -> dict[str, Any]:
        addr = (it.get("address") or it.get("tokenAddress") or "").lower()
        return {
            "address": Web3.to_checksum_address(addr) if addr.startswith("0x") else addr,
            "symbol": it.get("symbol") or it.get("shortName") or "?",
            "name": it.get("name") or "?",
            "platform": "four.meme",
            "created_at": it.get("launchTime") or it.get("createTime") or int(time.time()),
            "liquidity_usd": float(it.get("liquidity") or it.get("liquidityUsd") or 0),
            "volume_usd": float(it.get("volume24h") or it.get("volume") or it.get("amount") or 0),
            "price_usd": float(it.get("price") or it.get("priceUsd") or 0),
            "holders": int(it.get("holderCount") or it.get("holders") or 0),
            "progress": float(it.get("progress") or it.get("raiseProgress") or 0),
            "lp_burned": bool(it.get("lpBurned") or it.get("liquidityAdded")),
            "deployer": it.get("creator") or it.get("owner") or "",
            "quote": (it.get("raisedToken") or {}).get("symbol") if isinstance(it.get("raisedToken"), dict) else "BNB",
            "raw": it,
        }

    async def _from_events(self) -> list[dict[str, Any]]:
        if not self.w3:
            return []
        contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(TOKEN_MANAGER2),
            abi=TOKEN_MANAGER2_ABI,
        )
        latest = self.w3.eth.block_number
        from_block = self._last_block or max(latest - 50, 0)
        self._last_block = latest

        logs = contract.events.TokenCreate.get_logs(fromBlock=from_block, toBlock=latest)
        out = []
        for ev in logs:
            args = ev["args"]
            addr = args["token"].lower()
            if addr in self.seen:
                continue
            self.seen.add(addr)
            out.append({
                "address": Web3.to_checksum_address(args["token"]),
                "symbol": args.get("symbol") or "?",
                "name": args.get("name") or "?",
                "platform": "four.meme",
                "created_at": int(args.get("launchTime") or time.time()),
                "liquidity_usd": 0,
                "volume_usd": 0,
                "price_usd": 0,
                "holders": 0,
                "progress": 0,
                "lp_burned": False,
                "deployer": args.get("creator", ""),
                "quote": "BNB",
                "request_id": args.get("requestId"),
            })
        return out
