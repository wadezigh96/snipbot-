"""Bubble Maps-style holder concentration analysis.

Inspired by bubblemaps.io: a token can look widely held while a few linked
wallets (a "cluster" funded from one source, or the dev + bundled snipers)
control most of the supply. This module quantifies that from holder data:

- top-1 / top-10 share of supply
- Herfindahl-Hirschman Index (HHI) of holder shares
- dev-wallet share (when the creator wallet is known)
- linked-cluster share (when wallets are grouped, e.g. by shared funder)

It works for Solana (via read-only RPC ``getTokenLargestAccounts`` +
``getTokenSupply``) and for EVM tokens such as Robinhood Chain / Pons
launches (holder lists supplied by an explorer/launchpad API).

This is analysis only: it never signs or trades. Missing data fails closed
to UNKNOWN, never to "safe".
"""
from __future__ import annotations

import math
import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence

_BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_EVM_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

# Hard concentration limits used by the anti-rug gate.
TOP1_REJECT_PCT = 20.0
TOP10_REJECT_PCT = 60.0
CLUSTER_REJECT_PCT = 30.0
DEV_REJECT_PCT = 10.0


@dataclass(frozen=True)
class BubbleMapResult:
    status: str  # OK | RISKY | REJECT | UNKNOWN
    holders_seen: int
    top1_pct: float | None
    top10_pct: float | None
    hhi: float | None  # 0..10000, >2500 = highly concentrated
    dev_pct: float | None
    largest_cluster_pct: float | None
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        return value


def _clean_amounts(amounts: Iterable[Any]) -> list[float]:
    out: list[float] = []
    for value in amounts:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        number = float(value)
        if math.isfinite(number) and number > 0:
            out.append(number)
    return out


def analyze_holders(
    holders: Sequence[tuple[str, float]],
    *,
    total_supply: float | None = None,
    dev_wallet: str | None = None,
    clusters: Sequence[Sequence[str]] | None = None,
    exclude_owners: set[str] | None = None,
) -> BubbleMapResult:
    """Analyze ``(owner, amount)`` pairs. Amounts must share one unit.

    ``total_supply`` defaults to the sum of the supplied holders (correct for
    Solana's largest-accounts view only as a lower bound; pass the real
    supply when available). ``clusters`` groups wallet addresses believed to
    be linked (same funder / same entity); the largest group's combined
    share is reported.
    """
    excluded = exclude_owners or set()
    cleaned: list[tuple[str, float]] = []
    excluded_total = 0.0
    for owner, amount in holders:
        if not isinstance(owner, str) or not owner.strip():
            continue
        values = _clean_amounts([amount])
        if not values:
            continue
        if owner.strip() in excluded:
            # e.g. the bonding-curve account: it holds most of a new token's
            # supply by design and is not a "whale holder". Its amount is
            # subtracted from the supply denominator below.
            excluded_total += values[0]
            continue
        cleaned.append((owner.strip(), values[0]))
    if not cleaned:
        return BubbleMapResult("UNKNOWN", 0, None, None, None, None, None,
                               ("no_holder_data",))

    supply = total_supply if total_supply and total_supply > 0 else sum(a for _, a in cleaned)
    if excluded_total and total_supply:
        supply = total_supply - excluded_total
    if not supply or supply <= 0:
        return BubbleMapResult("UNKNOWN", len(cleaned), None, None, None, None, None,
                               ("total_supply_unknown",))

    shares = sorted((a / supply * 100.0 for _, a in cleaned), reverse=True)
    top1 = shares[0]
    top10 = sum(shares[:10])
    # HHI over observed holders; unobserved remainder is treated as dispersed,
    # so this is a lower bound on true concentration.
    hhi = sum(s * s for s in shares)

    dev_pct: float | None = None
    if dev_wallet:
        dev_pct = sum(a for o, a in cleaned if o == dev_wallet) / supply * 100.0

    cluster_pct: float | None = None
    if clusters:
        by_owner: dict[str, float] = {}
        for owner, amount in cleaned:
            by_owner[owner] = by_owner.get(owner, 0.0) + amount
        best = 0.0
        for group in clusters:
            total = sum(by_owner.get(w, 0.0) for w in group)
            best = max(best, total / supply * 100.0)
        cluster_pct = best

    reasons: list[str] = []
    status = "OK"
    if top1 > TOP1_REJECT_PCT:
        status = "REJECT"; reasons.append(f"top1_holder_{top1:.1f}pct_over_{TOP1_REJECT_PCT:.0f}")
    if top10 > TOP10_REJECT_PCT:
        status = "REJECT"; reasons.append(f"top10_{top10:.1f}pct_over_{TOP10_REJECT_PCT:.0f}")
    if cluster_pct is not None and cluster_pct > CLUSTER_REJECT_PCT:
        status = "REJECT"; reasons.append(f"linked_cluster_{cluster_pct:.1f}pct_over_{CLUSTER_REJECT_PCT:.0f}")
    if dev_pct is not None and dev_pct > DEV_REJECT_PCT:
        status = "REJECT"; reasons.append(f"dev_holds_{dev_pct:.1f}pct_over_{DEV_REJECT_PCT:.0f}")
    if status == "OK":
        if top1 > 10.0 or top10 > 40.0 or hhi > 1500:
            status = "RISKY"; reasons.append("holder_concentration_elevated")
        else:
            reasons.append("holder_distribution_acceptable")
    return BubbleMapResult(status, len(cleaned), round(top1, 4), round(top10, 4),
                           round(hhi, 2), None if dev_pct is None else round(dev_pct, 4),
                           None if cluster_pct is None else round(cluster_pct, 4),
                           tuple(reasons))


def analyze_holder_dicts(
    holders: Sequence[dict[str, Any]],
    *,
    total_supply: float | None = None,
    dev_wallet: str | None = None,
    clusters: Sequence[Sequence[str]] | None = None,
) -> BubbleMapResult:
    """Adapter for explorer/launchpad holder lists (Pons, block explorers).

    Accepts dicts with address under ``address``/``owner``/``wallet`` and the
    balance under ``balance``/``amount``/``value``.
    """
    pairs: list[tuple[str, float]] = []
    for item in holders:
        if not isinstance(item, dict):
            continue
        owner = item.get("address") or item.get("owner") or item.get("wallet")
        amount = item.get("balance", item.get("amount", item.get("value")))
        if isinstance(owner, str) and isinstance(amount, (int, float)) and not isinstance(amount, bool):
            pairs.append((owner, float(amount)))
    return analyze_holders(pairs, total_supply=total_supply,
                           dev_wallet=dev_wallet, clusters=clusters)


async def fetch_solana_bubblemap(
    mint: str, *, rpc_url: str | None = None, dev_wallet: str | None = None,
    exclude_owners: set[str] | None = None,
) -> BubbleMapResult:
    """Fetch largest token accounts + supply from a Solana RPC (read-only).

    Note: ``getTokenLargestAccounts`` returns token *accounts*, not owners;
    amounts are what matter for concentration. Fail-closed UNKNOWN on any
    missing/invalid data.
    """
    unknown = BubbleMapResult("UNKNOWN", 0, None, None, None, None, None,
                              ("solana_holder_data_unavailable",))
    if not isinstance(mint, str) or not _BASE58_RE.fullmatch(mint):
        return BubbleMapResult("UNKNOWN", 0, None, None, None, None, None, ("invalid_mint_address",))
    endpoint = (rpc_url or os.environ.get("SOLANA_RPC_URL", "")).strip()
    if not endpoint.startswith("https://"):
        return unknown
    try:
        import aiohttp

        async def call(session, method, params):
            async with session.post(endpoint, json={
                "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
            }) as response:
                if response.status != 200:
                    return None
                body = await response.json(content_type=None)
            if not isinstance(body, dict) or body.get("error") is not None:
                return None
            return body.get("result")

        timeout = aiohttp.ClientTimeout(total=12, connect=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            largest = await call(session, "getTokenLargestAccounts", [mint, {"commitment": "confirmed"}])
            supply = await call(session, "getTokenSupply", [mint, {"commitment": "confirmed"}])
        accounts = largest.get("value") if isinstance(largest, dict) else None
        supply_value = supply.get("value") if isinstance(supply, dict) else None
        if not isinstance(accounts, list) or not isinstance(supply_value, dict):
            return unknown
        total = supply_value.get("amount")
        total_f = float(total) if isinstance(total, (int, float, str)) and str(total).isdigit() else None
        pairs: list[tuple[str, float]] = []
        for acc in accounts:
            if not isinstance(acc, dict):
                continue
            address = acc.get("address")
            amount = acc.get("amount")
            if isinstance(address, str) and isinstance(amount, (int, float, str)):
                try:
                    pairs.append((address, float(amount)))
                except (TypeError, ValueError):
                    continue
        if not pairs:
            return unknown
        # Largest-account addresses are token accounts, not owner wallets, so
        # a dev-wallet match here would be meaningless; dev share stays None.
        return analyze_holders(pairs, total_supply=total_f, dev_wallet=None,
                               exclude_owners=exclude_owners)
    except Exception:
        return unknown
