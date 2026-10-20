"""Fail-closed polling client for the shared Telegram monitor-control state."""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass

import aiohttp

STATE_KEY = "pumpfun:control:monitor_state"
HEARTBEAT_KEY = "pumpfun:control:worker_heartbeat"


@dataclass
class MonitorControl:
    """In-memory mirror of durable desired state; starts paused by design."""
    enabled: bool
    running: bool = False
    last_error: str | None = None


class ControlStoreError(RuntimeError):
    pass


async def _command(command: list[str]) -> object:
    url = os.environ.get("CONTROL_STORE_URL", "").strip()
    token = os.environ.get("CONTROL_STORE_TOKEN", "").strip()
    if not url or not token or not url.startswith("https://"):
        raise ControlStoreError("control_store_unconfigured")
    timeout = aiohttp.ClientTimeout(total=4, connect=2)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                url,
                json=command,
                headers={"Authorization": f"Bearer {token}"},
            ) as response:
                if response.status != 200:
                    raise ControlStoreError("control_store_unavailable")
                payload = await response.json(content_type=None)
                if not isinstance(payload, dict) or payload.get("error"):
                    raise ControlStoreError("control_store_unavailable")
                return payload.get("result")
    except ControlStoreError:
        raise
    except Exception as exc:
        # Do not propagate provider errors/URLs, which may contain credentials.
        raise ControlStoreError("control_store_unavailable") from None


async def control_tick(state: MonitorControl) -> None:
    """Read desired state and refresh a short-lived heartbeat; fail closed."""
    if not state.enabled:
        state.running = True
        state.last_error = None
        return
    try:
        desired = await _command(["GET", STATE_KEY])
        if desired not in ("paused", "running"):
            state.running = False
            state.last_error = "control_state_missing_or_invalid"
        else:
            state.running = desired == "running"
            state.last_error = None
        result = await _command(["SET", HEARTBEAT_KEY, str(int(time.time())), "EX", "120"])
        if result != "OK":
            state.running = False
            state.last_error = "heartbeat_write_failed"
    except ControlStoreError:
        state.running = False
        state.last_error = "control_store_unavailable"


async def run_control_loop(state: MonitorControl, stop: asyncio.Event, interval: float = 15.0) -> None:
    """Poll shared state and publish heartbeat; failures always pause processing."""
    while not stop.is_set():
        await control_tick(state)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
