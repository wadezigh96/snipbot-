"""Best-effort Telegram notifications for the read-only PumpFun monitor.

Secrets are read only from runtime environment variables and never included in
return values, logs, or exception messages.
"""
from __future__ import annotations

import os
import re
from typing import Any


def _clean(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return "unknown"
    value = re.sub(r"[\x00-\x1f\x7f]+", " ", value)
    value = " ".join(value.split())
    return value[:limit] or "unknown"


def format_event_alert(
    event: dict[str, Any],
    mint_check: dict[str, Any],
    advisor: dict[str, Any],
) -> str:
    """Create a plain-text Telegram alert from untrusted, bounded fields."""
    mint = _clean(event.get("mint"), 64)
    name = _clean(event.get("name"), 100)
    symbol = _clean(event.get("symbol"), 32)
    event_type = _clean(event.get("event_type"), 24)
    score = event.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        score = "unknown"
    else:
        score = str(score)
    mint_status = _clean(mint_check.get("status"), 16)
    mint_reason = _clean(mint_check.get("reason"), 100)
    advisor_status = _clean(advisor.get("status"), 16)
    return (
        "PumpFun FOMO Radar — WATCH ONLY\n"
        f"Token: {name} ({symbol})\n"
        f"Event: {event_type}\n"
        f"Mint: {mint}\n"
        f"Triage score: {score} (not a buy signal)\n"
        f"Mint check: {mint_status} — {mint_reason}\n"
        f"Advisor: {advisor_status}\n"
        "Execution: DISABLED"
    )[:3500]


async def send_telegram_message(message: str) -> str:
    """Return sent, disabled, or failed; never expose provider response details."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return "disabled"
    if not isinstance(message, str) or not message.strip():
        return "failed"
    try:
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=8, connect=4)
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url,
                json={"chat_id": chat_id, "text": message[:3500], "disable_web_page_preview": True},
            ) as response:
                if response.status != 200:
                    return "failed"
                payload = await response.json(content_type=None)
                if isinstance(payload, dict) and payload.get("ok") is True:
                    return "sent"
                return "failed"
    except Exception:
        return "failed"
