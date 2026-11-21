"""Sniper runner: scanner -> anti-rug -> Bubble Maps -> LLM -> action.

Modes (``SNIPER_MODE`` env, default ``paper``):

- ``paper``: full pipeline; candidates open *paper* positions in the micro
  engine. A background task polls DexScreener prices and runs the exit
  ladder (SL / TP1-TP3 / time stop), printing goal progress. No keys, no
  transactions — this mode needs no wallet at all.
- ``live``: same pipeline, but candidates go to ``executor.Executor``.
  Refuses to start (exit code 2) unless the executor's double gate is open
  AND a local keypair is configured. The sell-route proof is gathered
  before the anti-rug verdict in both modes, using an unsigned transaction
  built for the proof wallet (the signer wallet in live mode; the Solana
  system program address — a valid public key — in paper mode).

Every stage is injectable (``RunnerDeps``) so the whole flow is testable
without network, keys, or funds.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from agent.pumpfun.antirug import RugVerdict, evaluate_rug_risk
from agent.pumpfun.bubblemap import BubbleMapResult, fetch_solana_bubblemap
from agent.pumpfun.executor import Executor, LiveConfig, build_default_executor
from agent.pumpfun.llm_sniper import SniperDecision, score_candidate
from agent.pumpfun.paper import MicroPlan, PaperEngine, goal_progress, next_position_usd
from agent.pumpfun.risk import RiskPolicy
from agent.pumpfun.rpc import MintCheck, verify_mint
from agent.pumpfun.simulation import (SimulationResult, classify_sell_simulation,
                                      simulate_transaction)
from agent.pumpfun.trade_ledger import TradeLedger

SOL_MINT = "So11111111111111111111111111111111111111112"
PROOF_WALLET_FALLBACK = "11111111111111111111111111111111"  # system program
DEX_TOKENS_URL = "https://api.dexscreener.com/latest/dex/tokens/{}"


def parse_mode(environ: dict[str, str] | None = None) -> str:
    values = os.environ if environ is None else environ
    mode = values.get("SNIPER_MODE", "paper").strip().lower()
    if mode not in {"paper", "live"}:
        raise ValueError("SNIPER_MODE must be 'paper' or 'live'")
    return mode


def dexscreener_price_usd(payload: Any) -> float | None:
    """Best (highest-liquidity) pair price from a DexScreener token payload."""
    if not isinstance(payload, dict):
        return None
    pairs = payload.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        return None
    best: tuple[float, float] | None = None  # (liquidity_usd, price)
    for pair in pairs:
        if not isinstance(pair, dict):
            continue
        try:
            price = float(pair.get("priceUsd"))
        except (TypeError, ValueError):
            continue
        liq = pair.get("liquidity")
        liq_usd = float(liq.get("usd") or 0) if isinstance(liq, dict) else 0.0
        if price > 0 and (best is None or liq_usd > best[0]):
            best = (liq_usd, price)
    return best[1] if best else None


async def fetch_price_usd(mint: str, *, get_json: Callable[[str], Awaitable[Any]] | None = None) -> float | None:
    if get_json is None:
        async def _get(url: str) -> Any:
            import aiohttp

            timeout = aiohttp.ClientTimeout(total=10, connect=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return None
                    return await response.json(content_type=None)

        get_json = _get
    try:
        return dexscreener_price_usd(await get_json(DEX_TOKENS_URL.format(mint)))
    except Exception:
        return None


async def sol_price_usd(environ: dict[str, str] | None = None, **kw: Any) -> float | None:
    values = os.environ if environ is None else environ
    raw = values.get("SOL_PRICE_USD", "").strip()
    if raw:
        try:
            price = float(raw)
            return price if price > 0 else None
        except ValueError:
            return None
    return await fetch_price_usd(SOL_MINT, **kw)


@dataclass
class RunnerDeps:
    verify_mint_fn: Callable[[str], Awaitable[MintCheck]] = field(default=lambda mint: verify_mint(mint))
    bubblemap_fn: Callable[[str], Awaitable[BubbleMapResult]] = field(default=lambda mint: fetch_solana_bubblemap(mint))
    score_fn: Callable[..., Awaitable[SniperDecision]] = field(default=score_candidate)
    build_tx_fn: Callable[..., Awaitable[bytes]] | None = None
    simulate_fn: Callable[[bytes], Awaitable[SimulationResult]] = field(default=lambda tx: simulate_transaction(tx))
    price_fn: Callable[[str], Awaitable[float | None]] = field(default=lambda mint: fetch_price_usd(mint))


@dataclass
class RunnerContext:
    mode: str
    plan: MicroPlan
    deps: RunnerDeps
    paper: PaperEngine
    proof_wallet: str = PROOF_WALLET_FALLBACK
    executor: Executor | None = None
    wallet: str | None = None
    risk: RiskPolicy = field(default_factory=lambda: RiskPolicy(
        bankroll_usd=5.0, max_position_usd=1.0, max_open_positions=3,
        daily_loss_limit_usd=1.50, sol_reserve_usd=0.75))
    sol_usd: float | None = None
    order_seq: int = 0
    live_open_positions: int = 0
    live_exposure_usd: float = 0.0


async def _sell_route_proof(ctx: RunnerContext, mint: str) -> SimulationResult:
    if ctx.deps.build_tx_fn is None:
        return SimulationResult(False, "tx_builder_not_configured")
    try:
        sell_tx = await ctx.deps.build_tx_fn(
            public_key=ctx.proof_wallet, mint=mint, action="sell", amount="1",
            denominated_in_sol=False, slippage_percent=5, priority_fee_sol="0.00005",
        )
        return classify_sell_simulation(await ctx.deps.simulate_fn(sell_tx))
    except Exception:
        return SimulationResult(False, "sell_proof_build_or_sim_failed")


async def process_event(event: dict[str, Any], ctx: RunnerContext, *, now: float | None = None) -> dict[str, Any]:
    """Run one scanner event through the full pipeline; returns a JSON-able report."""
    ts = time.time() if now is None else now
    mint = str(event.get("mint", ""))
    out: dict[str, Any] = {"mint": mint, "symbol": event.get("symbol"), "mode": ctx.mode}

    mint_check = await ctx.deps.verify_mint_fn(mint)
    bubblemap = await ctx.deps.bubblemap_fn(mint)
    proof = await _sell_route_proof(ctx, mint)

    market_cap_usd = None
    if event.get("market_cap_sol") and ctx.sol_usd:
        market_cap_usd = float(event["market_cap_sol"]) * ctx.sol_usd
    rug: RugVerdict = evaluate_rug_risk(
        mint_check=mint_check, bubblemap=bubblemap, liquidity_usd=None,
        v_sol_in_curve=event.get("v_sol_in_curve"), market_cap_usd=market_cap_usd,
        sell_simulation_passed=proof.passed,
    )
    sniper = await ctx.deps.score_fn(event, rug, bubblemap.to_dict())
    out.update({
        "mint_check": mint_check.status, "bubblemap": bubblemap.status,
        "sell_route": proof.reason, "antirug_passed": rug.passed,
        "antirug_reasons": list(rug.reasons), "sniper_status": sniper.status,
        "action": "none",
    })
    if sniper.status != "PAPER_BUY_CANDIDATE":
        return out

    price = await ctx.deps.price_fn(mint)
    if price is None:
        out["action"] = "skipped_price_unknown"
        return out

    if ctx.mode == "paper":
        position = ctx.paper.open(mint, price, now=ts)
        if position is None:
            out["action"] = "skipped_paper_limits"
            return out
        out["action"] = "paper_opened"
        out["entry_price_usd"] = price
        out["goal"] = goal_progress(ctx.plan, ctx.paper.equity_usd({mint: price}))
        return out

    # --- live mode -----------------------------------------------------------
    if ctx.executor is None or ctx.wallet is None or not ctx.sol_usd:
        out["action"] = "refused_live_not_ready"
        return out
    position_usd = next_position_usd(ctx.plan, ctx.plan.bankroll_usd)
    risk = ctx.risk.check_buy(
        position_usd=position_usd,
        open_positions=ctx.live_open_positions, open_exposure_usd=ctx.live_exposure_usd,
        daily_realized_loss_usd=0.0,
        available_sol_usd=ctx.plan.bankroll_usd, estimated_network_fee_usd=0.05,
        data_is_fresh=True, quote_is_valid=True, simulation_passed=proof.passed,
    )
    if not risk.allowed:
        out["action"] = f"refused_risk:{risk.reason}"
        return out
    ctx.order_seq += 1
    result = await ctx.executor.buy(
        client_order_id=f"snipe-{int(ts)}-{ctx.order_seq}", mint=mint,
        amount_sol=round(position_usd / ctx.sol_usd, 6), wallet=ctx.wallet,
        rug_passed=rug.passed, sniper_status=sniper.status, risk_allowed=risk.allowed,
    )
    if result.status == "SUBMITTED":
        ctx.live_open_positions += 1
        ctx.live_exposure_usd += position_usd
    out["action"] = "live_submitted" if result.status == "SUBMITTED" else f"live_refused:{result.reason}"
    out["signature"] = result.signature
    return out


async def poll_paper_positions(ctx: RunnerContext, *, interval_seconds: float = 30.0,
                               iterations: int | None = None) -> None:
    """Drive the exit ladder for open paper positions from live prices."""
    done = 0
    while iterations is None or done < iterations:
        await asyncio.sleep(interval_seconds if done or iterations is None else 0)
        done += 1
        open_positions = [p for p in ctx.paper.positions if not p.closed]
        if not open_positions:
            continue
        prices: dict[str, float] = {}
        for position in open_positions:
            price = await ctx.deps.price_fn(position.mint)
            if price is not None:
                prices[position.mint] = price
                action = ctx.paper.update(position, price, now=time.time())
                if action != "hold":
                    print(json.dumps({"type": "paper_exit", "mint": position.mint,
                                      "action": action, "price_usd": price}, separators=(",", ":")), flush=True)
        progress = goal_progress(ctx.plan, ctx.paper.equity_usd(prices))
        print(json.dumps({"type": "goal_progress", **progress}, separators=(",", ":")), flush=True)


async def run() -> int:
    mode = parse_mode()
    plan = MicroPlan(
        bankroll_usd=float(os.environ.get("MICRO_BANKROLL_USD", "5")),
        position_usd=float(os.environ.get("MICRO_POSITION_USD", "1")),
        target_usd=float(os.environ.get("MICRO_TARGET_USD", "1500")),
    )
    deps = RunnerDeps()
    executor: Executor | None = None
    wallet: str | None = None
    proof_wallet = PROOF_WALLET_FALLBACK

    if mode == "live":
        config = LiveConfig.from_env()
        if not config.enabled:
            print(json.dumps({"type": "startup_refused", "reason": config.reason}), flush=True)
            return 2
        try:
            from agent.pumpfun.signer import load_keypair, wallet_address

            keypair = load_keypair()
            wallet = wallet_address(keypair)
            proof_wallet = wallet
            ledger = TradeLedger(os.environ.get("PUMPFUN_TRADE_DB_PATH", "data/pumpfun_trades.sqlite3"))
            executor = build_default_executor(ledger=ledger)
        except Exception as exc:
            print(json.dumps({"type": "startup_refused", "reason": f"signer_or_executor_unavailable:{type(exc).__name__}"}), flush=True)
            return 2
        from agent.pumpfun.pumpportal_local import build_unsigned_transaction

        deps.build_tx_fn = build_unsigned_transaction
    else:
        # Paper mode can still gather sell-route evidence when a builder is
        # reachable; absence of one simply keeps the gate closed.
        try:
            from agent.pumpfun.pumpportal_local import build_unsigned_transaction

            deps.build_tx_fn = build_unsigned_transaction
        except Exception:
            deps.build_tx_fn = None

    ctx = RunnerContext(mode=mode, plan=plan, deps=deps, paper=PaperEngine(plan),
                        proof_wallet=proof_wallet, executor=executor, wallet=wallet)
    ctx.sol_usd = await sol_price_usd()
    print(json.dumps({"type": "startup", "mode": mode, "bankroll_usd": plan.bankroll_usd,
                      "target_usd": plan.target_usd, "sol_price_usd": ctx.sol_usd},
                     separators=(",", ":")), flush=True)

    from agent.pumpfun.scanner import stream_events

    seconds = float(os.environ.get("PUMPFUN_SCAN_SECONDS", "3600"))
    poll_task = asyncio.create_task(poll_paper_positions(ctx)) if mode == "paper" else None
    try:
        async for event in stream_events(seconds=seconds):
            report = await process_event(event.to_dict(), ctx)
            print(json.dumps({"type": "candidate", **report}, separators=(",", ":")), flush=True)
    finally:
        if poll_task is not None:
            poll_task.cancel()
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()
