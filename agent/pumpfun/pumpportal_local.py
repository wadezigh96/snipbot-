"""PumpPortal Local Transaction API adapter.

This module requests an unsigned serialized Solana transaction for local signing.
It never reads a private key, signs, simulates, or broadcasts a transaction.
"""
from __future__ import annotations

import os
import re
from decimal import Decimal, InvalidOperation
from typing import Any

_BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
ENDPOINT = "https://pumpportal.fun/api/trade-local"
MAX_RESPONSE_BYTES = 1_000_000


class TradeBuildError(RuntimeError):
    """A trade transaction could not be safely built."""


def build_request(
    *,
    public_key: str,
    mint: str,
    action: str,
    amount: str | int | float,
    denominated_in_sol: bool,
    slippage_percent: int,
    priority_fee_sol: str | int | float,
    pool: str = "auto",
) -> dict[str, Any]:
    """Validate and normalize a Local API request; does not perform a trade."""
    if not isinstance(public_key, str) or not _BASE58_RE.fullmatch(public_key):
        raise ValueError("invalid_public_key")
    if not isinstance(mint, str) or not _BASE58_RE.fullmatch(mint):
        raise ValueError("invalid_mint")
    if action not in {"buy", "sell"}:
        raise ValueError("invalid_action")
    if type(denominated_in_sol) is not bool:
        raise ValueError("denominated_in_sol_must_be_boolean")
    if isinstance(slippage_percent, bool) or not isinstance(slippage_percent, int):
        raise ValueError("invalid_slippage")
    if not 1 <= slippage_percent <= 5:
        raise ValueError("slippage_out_of_safe_range")
    if pool not in {"pump", "raydium", "pump-amm", "launchlab", "raydium-cpmm", "bonk", "auto"}:
        raise ValueError("unsupported_pool")

    def decimal_string(value: Any, field: str, *, allow_zero: bool = False) -> str:
        if isinstance(value, bool) or value is None:
            raise ValueError(f"invalid_{field}")
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError(f"invalid_{field}") from None
        if not parsed.is_finite() or parsed < 0 or (parsed == 0 and not allow_zero):
            raise ValueError(f"invalid_{field}")
        return format(parsed, "f")

    normalized_amount = decimal_string(amount, "amount")
    fee = Decimal(decimal_string(priority_fee_sol, "priority_fee", allow_zero=True))
    if fee > Decimal("0.001"):
        raise ValueError("priority_fee_above_safe_cap")

    return {
        "publicKey": public_key,
        "action": action,
        "mint": mint,
        "amount": normalized_amount,
        "denominatedInSol": "true" if denominated_in_sol else "false",
        "slippage": slippage_percent,
        "priorityFee": format(fee, "f"),
        "pool": pool,
    }


async def build_unsigned_transaction(
    *,
    public_key: str,
    mint: str,
    action: str,
    amount: str | int | float,
    denominated_in_sol: bool,
    slippage_percent: int,
    priority_fee_sol: str | int | float = "0.00001",
    pool: str = "auto",
) -> bytes:
    """Request transaction bytes only. No signing or broadcasting occurs."""
    payload = build_request(
        public_key=public_key,
        mint=mint,
        action=action,
        amount=amount,
        denominated_in_sol=denominated_in_sol,
        slippage_percent=slippage_percent,
        priority_fee_sol=priority_fee_sol,
        pool=pool,
    )
    try:
        import aiohttp
    except ImportError as exc:
        raise TradeBuildError("aiohttp_not_installed") from exc

    timeout = aiohttp.ClientTimeout(total=15, connect=5)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                ENDPOINT,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status != 200:
                    raise TradeBuildError(f"pumpportal_http_status_{response.status}")
                body = await response.read()
                if not body or len(body) > MAX_RESPONSE_BYTES:
                    raise TradeBuildError("transaction_response_size_invalid")
                # Local API returns serialized transaction bytes, not JSON.
                if body.lstrip().startswith((b"{", b"[", b"<")):
                    raise TradeBuildError("unexpected_transaction_response_format")
                return body
    except TradeBuildError:
        raise
    except Exception:
        # Do not leak provider responses, URLs, or environment secrets to logs.
        raise TradeBuildError("pumpportal_request_failed") from None


def local_api_ready() -> bool:
    """Check only whether the explicit local API configuration switch is on."""
    return os.environ.get("PUMPFUN_LOCAL_TX_BUILD_ENABLED", "").strip().lower() in {
        "1", "true", "yes"
    }
