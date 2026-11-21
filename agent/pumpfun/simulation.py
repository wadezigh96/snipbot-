"""Solana transaction simulation + broadcast via JSON-RPC.

Simulation is the missing sell-side evidence for the anti-rug gate: a token
whose sell transaction cannot even be simulated is treated as unsellable.

Sell-simulation nuance: before a buy, the wallet holds none of the token, so
a sell simulation normally fails with an insufficient-balance error. That
specific failure still proves the sell route/program path exists, so
``classify_sell_simulation`` accepts it — and only it — as route evidence.
Any program error, invalid account, or unknown failure rejects.

Broadcast (``send_transaction``) exists here as a primitive; it is only
reached through ``executor.py`` behind its double live gate.
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

PostFn = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class SimulationResult:
    passed: bool
    reason: str
    err: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "reason": self.reason, "err": self.err}


def _rpc_url(rpc_url: str | None) -> str | None:
    endpoint = (rpc_url or os.environ.get("SOLANA_RPC_URL", "")).strip()
    return endpoint if endpoint.startswith("https://") else None


async def _default_post(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=15, connect=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as response:
            if response.status != 200:
                raise RuntimeError(f"rpc_http_status_{response.status}")
            body = await response.json(content_type=None)
    if not isinstance(body, dict):
        raise RuntimeError("rpc_response_not_object")
    return body


def parse_simulation(body: Any) -> SimulationResult:
    if not isinstance(body, dict) or body.get("error") is not None:
        return SimulationResult(False, "rpc_error_or_invalid_response")
    result = body.get("result")
    value = result.get("value") if isinstance(result, dict) else None
    if not isinstance(value, dict) or "err" not in value:
        return SimulationResult(False, "simulation_response_invalid")
    err = value.get("err")
    if err is None:
        return SimulationResult(True, "simulation_passed")
    return SimulationResult(False, "simulation_failed", err=str(err)[:300])


async def simulate_transaction(
    tx_bytes: bytes, *, rpc_url: str | None = None, post: PostFn | None = None,
) -> SimulationResult:
    endpoint = _rpc_url(rpc_url)
    if endpoint is None:
        return SimulationResult(False, "solana_rpc_not_configured_or_not_https")
    if not tx_bytes:
        return SimulationResult(False, "empty_transaction")
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "simulateTransaction",
        "params": [
            base64.b64encode(tx_bytes).decode("ascii"),
            {"sigVerify": False, "replaceRecentBlockhash": True,
             "commitment": "confirmed", "encoding": "base64"},
        ],
    }
    try:
        body = await (post or _default_post)(endpoint, payload)
    except Exception:
        return SimulationResult(False, "simulation_request_failed")
    return parse_simulation(body)


def classify_sell_simulation(result: SimulationResult) -> SimulationResult:
    """Decide whether a pre-buy sell simulation proves a sell route exists."""
    if result.passed:
        return SimulationResult(True, "sell_simulation_passed")
    err = (result.err or "").lower()
    if "insufficient" in err and ("fund" in err or "balance" in err or "0x1" in err):
        return SimulationResult(True, "sell_route_exists_wallet_holds_none_yet")
    return SimulationResult(False, f"sell_route_not_proven:{result.reason}")


async def send_transaction(
    tx_bytes: bytes, *, rpc_url: str | None = None, post: PostFn | None = None,
) -> str:
    """Broadcast a signed transaction; returns its signature or raises."""
    endpoint = _rpc_url(rpc_url)
    if endpoint is None:
        raise RuntimeError("solana_rpc_not_configured_or_not_https")
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "sendTransaction",
        "params": [
            base64.b64encode(tx_bytes).decode("ascii"),
            {"skipPreflight": False, "preflightCommitment": "confirmed",
             "encoding": "base64", "maxRetries": 3},
        ],
    }
    body = await (post or _default_post)(endpoint, payload)
    if body.get("error") is not None or not isinstance(body.get("result"), str):
        raise RuntimeError("send_transaction_rejected_by_rpc")
    return body["result"]


def parse_token_balance(body: Any) -> float | None:
    """Sum uiAmount over a getTokenAccountsByOwner (jsonParsed) response."""
    if not isinstance(body, dict) or body.get("error") is not None:
        return None
    result = body.get("result")
    accounts = result.get("value") if isinstance(result, dict) else None
    if not isinstance(accounts, list):
        return None
    total = 0.0
    found = False
    for account in accounts:
        try:
            info = account["account"]["data"]["parsed"]["info"]
            amount = info["tokenAmount"]["uiAmount"]
            if isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount >= 0:
                total += float(amount)
                found = True
        except (KeyError, TypeError):
            continue
    return total if found else 0.0


async def fetch_token_balance(
    wallet: str, mint: str, *, rpc_url: str | None = None, post: PostFn | None = None,
) -> float | None:
    """Read-only token balance for a wallet/mint pair; None when unknown."""
    endpoint = _rpc_url(rpc_url)
    if endpoint is None or not wallet or not mint:
        return None
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
        "params": [wallet, {"mint": mint}, {"encoding": "jsonParsed", "commitment": "confirmed"}],
    }
    try:
        body = await (post or _default_post)(endpoint, payload)
    except Exception:
        return None
    return parse_token_balance(body)
