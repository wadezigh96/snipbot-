"""Read-only PumpFun monitor with bounded reconnects and optional Telegram alerts."""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from agent.pumpfun.control_store import MonitorControl, run_control_loop\nfrom agent.pumpfun.llm_advisor import advise_event
from agent.pumpfun.scanner import build_data_ws_url, stream_events
from agent.pumpfun.rpc import verify_mint
from agent.pumpfun.store import ObservationStore
from agent.pumpfun.telegram import format_event_alert, send_telegram_message


def backoff_seconds(attempt: int, *, base: float = 2.0, maximum: float = 60.0) -> float:
    """Exponential retry delay capped to avoid hammering a failing provider."""
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise ValueError("attempt must be a positive integer")
    if base <= 0 or maximum <= 0:
        raise ValueError("backoff bounds must be positive")
    return min(base * (2 ** min(attempt - 1, 10)), maximum)


def validate_telegram_config(environ: dict[str, str] | None = None) -> None:
    """Fail fast when only one half of the Telegram credential pair is configured."""
    values = os.environ if environ is None else environ
    token = values.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = values.get("TELEGRAM_CHAT_ID", "").strip()
    if bool(token) != bool(chat_id):
        raise ValueError("Configure both Telegram secret variables or leave both empty")


def _health(status: str, *, reason: str | None = None, attempt: int | None = None) -> None:
    item: dict[str, Any] = {"type": "health", "status": status, "observed_at": time.time()}
    if reason:
        item["reason"] = reason
    if attempt is not None:
        item["retry_attempt"] = attempt
    print(json.dumps(item, ensure_ascii=False, separators=(",", ":")), flush=True)


async def main() -> None:
    forever_raw = os.environ.get("PUMPFUN_RUN_FOREVER", "false").strip().lower()
    if forever_raw not in {"1", "true", "yes", "0", "false", "no"}:
        raise ValueError("PUMPFUN_RUN_FOREVER must be true or false")
    run_forever = forever_raw in {"1", "true", "yes"}
    default_seconds = "3600" if run_forever else "60"
    seconds = float(os.environ.get("PUMPFUN_SCAN_SECONDS", default_seconds))
    if not 0 < seconds <= 3600:
        raise ValueError("PUMPFUN_SCAN_SECONDS must be > 0 and <= 3600")

    # Validate required scanner and optional Telegram configuration before retrying.
    # The credential-bearing URL stays in memory and is never logged.
    validate_telegram_config()
    control_raw = os.environ.get("PUMPFUN_CONTROL_ENABLED", "false").strip().lower()
    if control_raw not in {"1", "true", "yes", "0", "false", "no"}:
        raise ValueError("PUMPFUN_CONTROL_ENABLED must be true or false")
    control = MonitorControl(enabled=control_raw in {"1", "true", "yes"})
    control_stop = asyncio.Event()
    control_task = asyncio.create_task(run_control_loop(control, control_stop))
    websocket_url = build_data_ws_url()
    db_path = os.environ.get("PUMPFUN_DB_PATH", "data/pumpfun_monitor.sqlite3")
    deadline = None if run_forever else time.monotonic() + seconds
    consecutive_failures = 0
    outage = False

    async def status_callback(status: str) -> None:
        nonlocal outage, consecutive_failures
        if status == "connected":
            consecutive_failures = 0
            _health("connected")
            if outage:
                result = await send_telegram_message(
                    "PumpFun FOMO Radar: data connection recovered. Monitoring remains read-only; execution is DISABLED."
                )
                _health("recovery_notification", reason=result)
                outage = False
        elif status == "disconnected":
            _health("disconnected", reason="websocket_closed")
            if not outage:
                outage = True
                result = await send_telegram_message(
                    "PumpFun FOMO Radar: data connection lost. Reconnecting with bounded backoff; execution remains DISABLED."
                )
                _health("outage_notification", reason=result)

    with ObservationStore(db_path) as store:
        while deadline is None or time.monotonic() < deadline:
            remaining = seconds if deadline is None else deadline - time.monotonic()
            if remaining <= 0:
                break
            window = min(3600.0, max(0.1, remaining))
            try:
                async for event in stream_events(
                    seconds=window,
                    websocket_url=websocket_url,
                    on_status=status_callback,
                ):
                    if control.enabled and not control.running:
                        continue
                    raw = event.to_dict()
                    decision = await advise_event(raw)
                    mint_check = await verify_mint(raw["mint"])
                    advisor = {
                        "status": decision.status,
                        "score": decision.score,
                        "reason": decision.reason,
                        "model": decision.model,
                    }
                    raw["mint_check"] = mint_check.to_dict()
                    is_new = store.record(raw, advisor, observed_at=event.observed_at)
                    if not is_new:
                        continue
                    notification = await send_telegram_message(
                        format_event_alert(raw, mint_check.to_dict(), advisor)
                    )
                    output = {
                        "event": raw,
                        "mint_check": mint_check.to_dict(),
                        "llm_advisor": advisor,
                        "execution": "DISABLED",
                        "persistent_store": "SAVED",
                        "telegram_notification": notification,
                    }
                    print(json.dumps(output, ensure_ascii=False, separators=(",", ":")), flush=True)
                consecutive_failures = 0
                if not run_forever:
                    break
            except asyncio.CancelledError:
                raise
            except Exception:
                consecutive_failures += 1
                if not outage:
                    outage = True
                    result = await send_telegram_message(
                        "PumpFun FOMO Radar: data connection unavailable. Reconnecting with bounded backoff; execution remains DISABLED."
                    )
                    _health("outage_notification", reason=result)
                _health(
                    "reconnecting",
                    reason="connection_or_stream_error",
                    attempt=consecutive_failures,
                )
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                else:
                    remaining = seconds
                await asyncio.sleep(min(backoff_seconds(consecutive_failures), max(0.0, remaining)))


if __name__ == "__main__":
    asyncio.run(main())
