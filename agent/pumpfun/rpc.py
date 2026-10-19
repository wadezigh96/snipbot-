"""Read-only Solana mint-account verification via JSON-RPC."""
from __future__ import annotations

import asyncio
import base64
import os
import re
from dataclasses import asdict, dataclass
from typing import Any

TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
_BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


@dataclass(frozen=True)
class MintCheck:
    status: str
    mint: str
    reason: str
    token_program: str | None = None
    decimals: int | None = None
    mint_authority_present: bool | None = None
    freeze_authority_present: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_mint_account(mint: str, account: Any) -> MintCheck:
    """Parse the stable 82-byte SPL mint base layout; never infer holder safety."""
    if not isinstance(mint, str) or not _BASE58_RE.fullmatch(mint):
        return MintCheck("UNKNOWN", str(mint)[:64], "invalid_mint_address")
    if not isinstance(account, dict):
        return MintCheck("UNKNOWN", mint, "mint_account_missing")
    owner = account.get("owner")
    if not isinstance(owner, str):
        return MintCheck("UNKNOWN", mint, "mint_account_owner_invalid")
    if owner not in {TOKEN_PROGRAM, TOKEN_2022_PROGRAM}:
        return MintCheck("REJECT", mint, "account_owner_not_supported_token_program")
    data_field = account.get("data")
    if not isinstance(data_field, list) or len(data_field) < 2 or data_field[1] != "base64":
        return MintCheck("UNKNOWN", mint, "mint_account_encoding_invalid")
    try:
        data = base64.b64decode(data_field[0], validate=True)
    except (ValueError, TypeError):
        return MintCheck("UNKNOWN", mint, "mint_account_base64_invalid")
    if len(data) < 82:
        return MintCheck("REJECT", mint, "mint_account_data_too_short")
    # Token-2022 can append TLV extensions that this base-layout parser does not
    # interpret. Do not label such accounts VERIFIED until extensions are parsed.
    if owner == TOKEN_2022_PROGRAM and len(data) > 82:
        return MintCheck("UNKNOWN", mint, "token_2022_extensions_not_parsed")

    mint_option = int.from_bytes(data[0:4], "little")
    initialized = data[45]
    freeze_option = int.from_bytes(data[46:50], "little")
    if mint_option not in (0, 1) or freeze_option not in (0, 1):
        return MintCheck("REJECT", mint, "mint_authority_option_invalid")
    if initialized != 1:
        return MintCheck("REJECT", mint, "mint_not_initialized")

    flags = []
    if mint_option == 1:
        flags.append("mint_authority_present")
    if freeze_option == 1:
        flags.append("freeze_authority_present")
    reason = "mint_layout_valid"
    if flags:
        reason = "mint_layout_valid_with_authority_flags:" + ",".join(flags)
    return MintCheck(
        "VERIFIED",
        mint,
        reason,
        token_program=owner,
        decimals=data[44],
        mint_authority_present=(mint_option == 1),
        freeze_authority_present=(freeze_option == 1),
    )


async def verify_mint(mint: str, *, rpc_url: str | None = None) -> MintCheck:
    """Fetch a mint account using a read-only Solana RPC call."""
    if not isinstance(mint, str) or not _BASE58_RE.fullmatch(mint):
        return MintCheck("UNKNOWN", str(mint)[:64], "invalid_mint_address")
    endpoint = (rpc_url or os.environ.get("SOLANA_RPC_URL", "")).strip()
    if not endpoint:
        return MintCheck("UNKNOWN", mint, "solana_rpc_not_configured")
    if not endpoint.startswith("https://"):
        return MintCheck("UNKNOWN", mint, "solana_rpc_endpoint_must_use_https")
    try:
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=10, connect=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                endpoint,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getAccountInfo",
                    "params": [mint, {"encoding": "base64", "commitment": "confirmed"}],
                },
            ) as response:
                if response.status != 200:
                    return MintCheck("UNKNOWN", mint, f"solana_rpc_http_status_{response.status}")
                body = await response.json(content_type=None)
        if not isinstance(body, dict) or body.get("error") is not None:
            return MintCheck("UNKNOWN", mint, "solana_rpc_error_or_invalid_response")
        result = body.get("result")
        value = result.get("value") if isinstance(result, dict) else None
        return parse_mint_account(mint, value)
    except Exception:
        return MintCheck("UNKNOWN", mint, "solana_rpc_request_failed")
