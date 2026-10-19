"""Run PumpFun FOMO Radar in read-only monitor mode."""
from __future__ import annotations

import asyncio
import json
import os

from agent.pumpfun.llm_advisor import advise_event
from agent.pumpfun.scanner import stream_events


async def main() -> None:
    seconds = float(os.environ.get("PUMPFUN_SCAN_SECONDS", "60"))
    async for event in stream_events(seconds=seconds):
        raw = event.to_dict()
        decision = await advise_event(raw)
        output = {
            "event": raw,
            "llm_advisor": {
                "status": decision.status,
                "score": decision.score,
                "reason": decision.reason,
                "model": decision.model,
            },
            "execution": "DISABLED",
        }
        print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    asyncio.run(main())
