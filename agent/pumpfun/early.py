"""Early-entry filter: catch tokens at creation, before the crowd.

The trade-off is explicit: the earliest entries have the largest upside
(a >1000% move is only reachable from a tiny starting curve) and the
highest rug rate. This filter therefore adds *stricter* conditions on top
of the anti-rug gate, aimed at the two dev behaviours the owner asked to
screen out:

- **Bundling (the "Bubble Maps" trick)**: the dev quietly buys a large
  share at launch through their own wallet(s). Proxies measurable at
  creation: curve-excluded top-1/top-10 holder share, and the creator's
  initial buy size relative to the curve.
- **Rugging**: handled by the anti-rug gate (authority, sell route) plus
  the exit ladder — no filter can prove a dev will not rug later.

Fail-closed: anything unknown or outside the early window rejects.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from agent.pumpfun.bubblemap import BubbleMapResult
from agent.pumpfun.rpc import MintCheck

# Pump.fun bonding curve holds ~85 SOL of virtual reserves at graduation;
# "early" here means the first stretch of that curve.
EARLY_MIN_CURVE_SOL = 0.5
EARLY_MAX_CURVE_SOL = 35.0
MAX_INITIAL_BUY_SOL = 3.0   # creator's first buy; bigger = bundled/insider feel
MAX_TOP1_PCT = 15.0         # curve-excluded
MAX_TOP10_PCT = 50.0        # curve-excluded


@dataclass(frozen=True)
class EarlyVerdict:
    passed: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        return value


def evaluate_early_entry(
    event: dict[str, Any],
    *,
    mint_check: MintCheck,
    bubblemap: BubbleMapResult,
) -> EarlyVerdict:
    reasons: list[str] = []

    if event.get("event_type") != "new_token":
        reasons.append("not_a_creation_event")
    if mint_check.status != "VERIFIED":
        reasons.append("mint_not_verified")
    elif mint_check.freeze_authority_present:
        reasons.append("freeze_authority_active")

    v_sol = event.get("v_sol_in_curve")
    if not isinstance(v_sol, (int, float)) or isinstance(v_sol, bool):
        reasons.append("curve_reserve_unknown")
    elif v_sol < EARLY_MIN_CURVE_SOL:
        reasons.append("curve_reserve_too_small")
    elif v_sol > EARLY_MAX_CURVE_SOL:
        reasons.append("past_early_window")

    initial_buy = event.get("initial_buy")
    if initial_buy is not None:
        if not isinstance(initial_buy, (int, float)) or isinstance(initial_buy, bool):
            reasons.append("initial_buy_unknown")
        elif initial_buy > MAX_INITIAL_BUY_SOL:
            reasons.append(f"creator_initial_buy_{initial_buy:.2f}sol_over_{MAX_INITIAL_BUY_SOL:.0f}")

    # Bundling proxies from the curve-excluded holder map.
    if bubblemap.status in {"UNKNOWN", "REJECT"}:
        reasons.append(f"bubblemap_{bubblemap.status.lower()}")
    if bubblemap.top1_pct is None or bubblemap.top10_pct is None:
        reasons.append("holder_distribution_unknown")
    else:
        if bubblemap.top1_pct > MAX_TOP1_PCT:
            reasons.append(f"top1_{bubblemap.top1_pct:.1f}pct_over_{MAX_TOP1_PCT:.0f}")
        if bubblemap.top10_pct > MAX_TOP10_PCT:
            reasons.append(f"top10_{bubblemap.top10_pct:.1f}pct_over_{MAX_TOP10_PCT:.0f}")
    if bubblemap.largest_cluster_pct is not None and bubblemap.largest_cluster_pct > 15.0:
        reasons.append(f"linked_cluster_{bubblemap.largest_cluster_pct:.1f}pct")

    if reasons:
        return EarlyVerdict(False, tuple(reasons))
    return EarlyVerdict(True, ("early_window_clean_no_bundle_signals",))
