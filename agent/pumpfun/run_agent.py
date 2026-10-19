"""Run PumpFun FOMO Radar in read-only monitor mode."""
from __future__ import annotations

import asyncio
import json
import os

from agent.pumpfun.llm_advisor import advise_event
from agent.pumpfun.scanner import stream_events
from agent.pumpfun.store import ObservationStore


async def main() -> None:
    seconds = float(os.environ.get("PUMPFUN_SCAN_SECONDS", "60"))
    db_path = os.environ.get("PUMPFUN_DB_PATH", "data/pumpfun_monitor.sqlite3")
    with ObservationStore(db_path) as store:
        async for event in stream_events(seconds=seconds):
            raw = event.to_dict()
            decision = await advise_event(raw)
            advisor = {
                "status": decision.status,
                "score": decision.score,
                "reason": decision.reason,
                "model": decision.model,
            }
            is_new = store.record(raw, advisor, observed_at=event.observed_at)
            if not is_new:
                continue
            output = {
                "event": raw,
                "llm_advisor": advisor,
                "execution": "DISABLED",
                "persistent_store": "SAVED",
            }
            print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    asyncio.run(main())
