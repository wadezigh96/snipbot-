"""Read-only Pump.fun event scanner.

Uses PumpPortal's documented third-party data WebSocket. This module only
normalizes and scores observed events; it does not quote, sign, or trade.
All event fields are untrusted and may be missing, delayed, or malformed.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any, AsyncIterator, Callable
import inspect
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


PUMPPORTAL_DATA_WS = "wss://pumpportal.fun/api/data"
_BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


@dataclass(frozen=True)
class PumpEvent:
    mint: str
    event_type: str
    observed_at: float
    name: str | None
    symbol: str | None
    trader: str | None
    pool: str | None
    market_cap_sol: float | None
    v_sol_in_curve: float | None
    v_tokens_in_curve: float | None
    initial_buy: float | None
    score: int
    decision: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        return value


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        return None
    return number


def normalize_event(payload: Any, *, observed_at: float | None = None) -> PumpEvent | None:
    """Normalize a websocket event without trusting provider data."""
    if not isinstance(payload, dict):
        return None
    if observed_at is None:
        timestamp = time.time()
    else:
        timestamp = _number(observed_at)
        if timestamp is None:
            return None

    mint = payload.get("mint")
    if not isinstance(mint, str) or not _BASE58_RE.fullmatch(mint):
        return None

    raw_type = payload.get("txType") or payload.get("event") or "new_token"
    event_type = str(raw_type).strip().lower()
    if event_type not in {"create", "new_token", "migration", "migrate"}:
        return None
    event_type = "migration" if event_type in {"migration", "migrate"} else "new_token"

    name = payload.get("name")
    symbol = payload.get("symbol")
    trader = payload.get("traderPublicKey")
    pool = payload.get("pool") or payload.get("bondingCurveKey")
    name = name[:100] if isinstance(name, str) and name.strip() else None
    symbol = symbol[:32] if isinstance(symbol, str) and symbol.strip() else None
    trader = trader if isinstance(trader, str) and _BASE58_RE.fullmatch(trader) else None
    pool = pool if isinstance(pool, str) and _BASE58_RE.fullmatch(pool) else None

    market_cap = _number(payload.get("marketCapSol"))
    v_sol = _number(payload.get("vSolInBondingCurve"))
    v_tokens = _number(payload.get("vTokensInBondingCurve"))
    initial_buy = _number(payload.get("initialBuy"))
    score, reasons = score_event(
        event_type=event_type,
        market_cap_sol=market_cap,
        v_sol_in_curve=v_sol,
        v_tokens_in_curve=v_tokens,
        initial_buy=initial_buy,
        name=name,
        symbol=symbol,
    )
    return PumpEvent(
        mint=mint,
        event_type=event_type,
        observed_at=timestamp,
        name=name,
        symbol=symbol,
        trader=trader,
        pool=pool,
        market_cap_sol=market_cap,
        v_sol_in_curve=v_sol,
        v_tokens_in_curve=v_tokens,
        initial_buy=initial_buy,
        score=score,
        decision="WATCH_ONLY",
        reasons=tuple(reasons),
    )


def score_event(
    *,
    event_type: str,
    market_cap_sol: float | None,
    v_sol_in_curve: float | None,
    v_tokens_in_curve: float | None,
    initial_buy: float | None,
    name: str | None,
    symbol: str | None,
) -> tuple[int, list[str]]:
    """A transparent triage score, not a buy recommendation or safety verdict."""
    score = 0
    reasons: list[str] = []
    if event_type == "migration":
        score += 15
        reasons.append("migration_event_observed")
    else:
        reasons.append("new_token_event_observed")

    if v_sol_in_curve is not None and v_sol_in_curve > 0:
        score += 20
        reasons.append("positive_virtual_sol_reserve")
    else:
        reasons.append("missing_or_zero_virtual_sol_reserve")

    if v_tokens_in_curve is not None and v_tokens_in_curve > 0:
        score += 10
        reasons.append("positive_virtual_token_reserve")
    else:
        reasons.append("missing_or_zero_virtual_token_reserve")

    if market_cap_sol is not None and market_cap_sol > 0:
        score += 10
        reasons.append("market_cap_field_present")
    else:
        reasons.append("missing_market_cap")

    if initial_buy is not None and initial_buy > 0:
        score += 5
        reasons.append("initial_buy_field_present")

    if not name or not symbol:
        reasons.append("metadata_incomplete")

    reasons.append("not_a_trade_signal_missing_liquidity_holder_and_authority_checks")
    return min(score, 100), reasons


def build_data_ws_url(api_key: str | None = None) -> str:
    """Build the provider URL from a secret supplied only at runtime."""
    secret = api_key if api_key is not None else os.environ.get("PUMPPORTAL_API_KEY")
    if not isinstance(secret, str) or not secret.strip():
        raise RuntimeError("Set PUMPPORTAL_API_KEY in the local environment; never commit the real key.")
    parts = urlsplit(PUMPPORTAL_DATA_WS)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["api-key"] = secret.strip()
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


async def _report_status(
    callback: Callable[[str], Any] | None,
    status: str,
) -> None:
    if callback is None:
        return
    try:
        result = callback(status)
        if inspect.isawaitable(result):
            await result
    except Exception:
        # Observability must never break the read-only scanner.
        return


async def stream_events(
    *,
    seconds: float = 60,
    websocket_url: str | None = None,
    on_status: Callable[[str], Any] | None = None,
) -> AsyncIterator[PumpEvent]:
    """Yield events for one bounded WebSocket session.

    A closed/error WebSocket raises a generic RuntimeError so the caller can
    reconnect with backoff. Provider exception details are intentionally hidden.
    """
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0 or seconds > 3600:
        raise ValueError("seconds must be > 0 and <= 3600")

    try:
        import aiohttp
    except ImportError as exc:
        raise RuntimeError("Install project requirements first: pip install -r requirements.txt") from exc

    resolved_websocket_url = websocket_url or build_data_ws_url()
    seen: set[tuple[str, str]] = set()
    deadline = time.monotonic() + seconds
    timeout = aiohttp.ClientTimeout(total=None, connect=10, sock_read=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.ws_connect(resolved_websocket_url, heartbeat=20) as ws:
            await _report_status(on_status, "connected")
            await ws.send_json({"method": "subscribeNewToken"})
            await ws.send_json({"method": "subscribeMigration"})
            while time.monotonic() < deadline:
                remaining = max(0.1, min(5.0, deadline - time.monotonic()))
                try:
                    message = await asyncio.wait_for(ws.receive(), timeout=remaining)
                except asyncio.TimeoutError:
                    continue
                if message.type == aiohttp.WSMsgType.TEXT:
                    try:
                        payload = json.loads(message.data)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    event = normalize_event(payload)
                    if event is None:
                        continue
                    key = (event.mint, event.event_type)
                    if key in seen:
                        continue
                    seen.add(key)
                    yield event
                elif message.type in {
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.ERROR,
                }:
                    await _report_status(on_status, "disconnected")
                    raise RuntimeError("pumpportal_websocket_closed")


async def main() -> None:
    seconds = float(os.environ.get("PUMPFUN_SCAN_SECONDS", "60"))
    try:
        async for event in stream_events(seconds=seconds):
            print(json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":")))
    except RuntimeError as exc:
        message = str(exc)
        if message.startswith("Set PUMPPORTAL_API_KEY"):
            print(message, file=sys.stderr)
        else:
            print(
                "Scanner stopped; connection/runtime details suppressed to protect credentials.",
                file=sys.stderr,
            )
        raise SystemExit(1) from None
    except Exception:
        print(
            "Scanner stopped; connection/runtime details suppressed to protect credentials.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    asyncio.run(main())
