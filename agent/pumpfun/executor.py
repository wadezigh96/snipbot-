"""Live executor — the only path that can broadcast a trade.

Double gate, both required, neither stored in the repo:

- ``SNIPER_LIVE_ENABLED=true``
- ``SNIPER_LIVE_CONFIRM=I_UNDERSTAND_LIVE_TRADING``

Buy flow (every step fail-closed, in this order):
1. live gate open
2. anti-rug verdict passed AND LLM sniper status is PAPER_BUY_CANDIDATE
3. deterministic risk policy allowed the position
4. PumpPortal builds the unsigned buy transaction
5. buy simulation passes
6. sell route proven (sell transaction builds + simulation classification)
7. local signer signs; RPC broadcasts; the trade ledger records
   PREPARED -> SIMULATED -> SUBMITTED with the real signature

Confirmation polling/reconciliation stays with the trade ledger's rules:
an UNKNOWN outcome is never retried blindly. This module is deliberately
not wired into the read-only monitor; a live runner must call it explicitly.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from agent.pumpfun.simulation import (SimulationResult, classify_sell_simulation,
                                      send_transaction, simulate_transaction)

BuildFn = Callable[..., Awaitable[bytes]]
SimFn = Callable[[bytes], Awaitable[SimulationResult]]
SignFn = Callable[[bytes], bytes]
SendFn = Callable[[bytes], Awaitable[str]]

CONFIRM_PHRASE = "I_UNDERSTAND_LIVE_TRADING"


@dataclass(frozen=True)
class LiveConfig:
    enabled: bool
    reason: str

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "LiveConfig":
        values = os.environ if environ is None else environ
        if values.get("SNIPER_LIVE_ENABLED", "").strip().lower() != "true":
            return cls(False, "live_not_enabled")
        if values.get("SNIPER_LIVE_CONFIRM", "").strip() != CONFIRM_PHRASE:
            return cls(False, "live_confirm_phrase_missing")
        return cls(True, "live_gate_open")


@dataclass(frozen=True)
class ExecutionResult:
    status: str  # SUBMITTED | REFUSED
    reason: str
    signature: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "reason": self.reason, "signature": self.signature}


class Executor:
    def __init__(
        self,
        config: LiveConfig,
        *,
        build_tx: BuildFn,
        sign: SignFn,
        simulate: SimFn | None = None,
        send: SendFn | None = None,
        ledger: Any | None = None,
    ):
        self.config = config
        self.build_tx = build_tx
        self.sign = sign
        self.simulate = simulate or (lambda tx: simulate_transaction(tx))
        self.send = send or (lambda tx: send_transaction(tx))
        self.ledger = ledger

    async def buy(
        self,
        *,
        client_order_id: str,
        mint: str,
        amount_sol: float,
        wallet: str,
        rug_passed: bool,
        sniper_status: str,
        risk_allowed: bool,
        slippage_percent: int = 5,
    ) -> ExecutionResult:
        if not self.config.enabled:
            return ExecutionResult("REFUSED", self.config.reason)
        if not rug_passed:
            return ExecutionResult("REFUSED", "antirug_gate_failed")
        if sniper_status != "PAPER_BUY_CANDIDATE":
            return ExecutionResult("REFUSED", f"sniper_status_not_candidate:{sniper_status}")
        if not risk_allowed:
            return ExecutionResult("REFUSED", "risk_policy_denied")
        if amount_sol <= 0:
            return ExecutionResult("REFUSED", "amount_must_be_positive")

        if self.ledger is not None:
            self.ledger.create_order(client_order_id, mint, "buy", amount_sol)

        try:
            buy_tx = await self.build_tx(
                public_key=wallet, mint=mint, action="buy", amount=str(amount_sol),
                denominated_in_sol=True, slippage_percent=slippage_percent,
                priority_fee_sol="0.00005",
            )
        except Exception:
            return ExecutionResult("REFUSED", "buy_transaction_build_failed")

        buy_sim = await self.simulate(buy_tx)
        if not buy_sim.passed:
            return ExecutionResult("REFUSED", f"buy_simulation_failed:{buy_sim.reason}")

        # Sell-route proof: build a sell for a nominal token amount and
        # classify its simulation (wallet holds none yet — see simulation.py).
        try:
            sell_tx = await self.build_tx(
                public_key=wallet, mint=mint, action="sell", amount="1",
                denominated_in_sol=False, slippage_percent=slippage_percent,
                priority_fee_sol="0.00005",
            )
            sell_sim = classify_sell_simulation(await self.simulate(sell_tx))
            if not sell_sim.passed:
                return ExecutionResult("REFUSED", f"sell_route_not_proven:{sell_sim.reason}")
        except Exception:
            return ExecutionResult("REFUSED", "sell_transaction_build_failed")

        if self.ledger is not None:
            self.ledger.transition(client_order_id, "SIMULATED",
                                   evidence="buy_and_sell_simulation", updated_at=time.time())
        try:
            signed = self.sign(buy_tx)
        except Exception:
            return ExecutionResult("REFUSED", "local_signing_failed")
        try:
            signature = await self.send(signed)
        except Exception:
            if self.ledger is not None:
                try:
                    self.ledger.transition(client_order_id, "FAILED",
                                           error="broadcast_failed", updated_at=time.time())
                except Exception:
                    pass
            return ExecutionResult("REFUSED", "broadcast_failed")
        if self.ledger is not None:
            self.ledger.transition(client_order_id, "SUBMITTED",
                                   tx_signature=signature, updated_at=time.time())
        return ExecutionResult("SUBMITTED", "buy_broadcast_confirmed_by_rpc_accept", signature)


def build_default_executor(ledger: Any | None = None) -> Executor:
    """Wire the real PumpPortal/signer/RPC pieces. Still gated by LiveConfig."""
    from agent.pumpfun.pumpportal_local import build_unsigned_transaction
    from agent.pumpfun.signer import load_keypair, sign_transaction

    keypair = load_keypair()  # raises SignerError when unconfigured — fail closed

    def _sign(tx: bytes) -> bytes:
        return sign_transaction(tx, keypair)

    return Executor(LiveConfig.from_env(), build_tx=build_unsigned_transaction,
                    sign=_sign, ledger=ledger)
