# PumpFun FOMO Radar — migration audit (read-only baseline)

## Scope and safety status

This branch is an isolated migration track for Solana/Pump.fun. The existing `main` branch remains unchanged. This document records the initial audit and acceptance gates; it does **not** authorize live trading.

- Trading status: **DISABLED**
- Transaction broadcast: **NOT ENABLED**
- Wallet creation/import: **NOT PERFORMED**
- Seed phrase/private key: must never be requested in chat, logged, committed, or sent to a frontend.

## Confirmed baseline findings

1. The existing `agent/config.py`, `agent/execution/trader.py`, scanner modules and contract ABIs are BNB Chain / EVM oriented (Web3, `eth_account`, BNB chain IDs).
2. `agent/execution/trader.py` has quote-failure paths that fall back to `min_amount = 0` for four.meme and Flap. A Solana implementation must fail closed when a quote, price limit, token state or simulation is unavailable.
3. `agent/portfolio/manager.py` sizes positions as a percentage of BNB balance, keeps positions only in memory, and has TODO-only take-profit/stop-loss handling. It cannot enforce a reliable $1 daily loss cap across restarts.
4. `index.html` is a market-scanning/manual handoff page; it does not prove that a Pump.fun transaction path or a secure signer exists.
5. The existing requirements do not include a Solana SDK. No Solana signing or Pump.fun execution has been verified.

## Target configuration (initial, conservative)

- Maximum total bankroll: USD 10.
- Maximum position: USD 1 per token.
- Maximum concurrent positions: 2.
- Daily realized-loss stop: USD 1; halt new buys after reaching it.
- No leverage, no automatic wallet funding, no blind retry after an uncertain transaction.
- Keep SOL reserved for network fees; the reserve amount must be checked against a live fee estimate before any order.
- If price, liquidity, token status, holder/authority risk data, quote, simulation, balance, or RPC status is stale/unknown, reject the buy.
- A score is a screening heuristic, not a safety guarantee.

## Required implementation gates

1. **Scanner:** identify Pump.fun tokens and mint addresses from a documented, stable source; deduplicate and timestamp every observation.
2. **Token state:** distinguish bonding-curve tokens from migrated PumpSwap tokens; route each state only through a validated supported instruction path.
3. **Quote and limits:** derive expected output, enforce a non-zero minimum output and a strict slippage ceiling. Never replace a failed quote with zero minimum output.
4. **Signer isolation:** signing occurs locally/server-side in a secret store, never in browser JavaScript or logs. Do not add secrets to repository files.
5. **Simulation:** simulate the exact transaction, validate program IDs/accounts and estimated fees, and reject simulation errors or missing results.
6. **Idempotency and reconciliation:** persist intent before broadcast; after timeout, inspect signature/status and balances before any retry.
7. **Risk accounting:** persist positions, fills, fees and daily P&L. Reserve network SOL separately from trade budget. Enforce exposure and daily stop after restarts.
8. **Exit path:** verify sell quotes and actual token balance; test failed/partial sells and migrated-token behavior.
9. **Tests:** deterministic unit tests, mocked RPC/API tests, malformed/stale data tests, quote/simulation failure tests, and dry-run integration tests.
10. **Activation:** remain disabled until tests pass and the owner explicitly confirms live activation. No transaction is to be broadcast by this migration work.

## Initial risk gate

`agent/pumpfun/risk.py` is a dependency-free pre-trade gate for the target dollar limits. It is intentionally not connected to a signer or execution loop. Its tests must pass before it is integrated into any live path.

## Not yet verified

- Current Pump.fun API/SDK compatibility and exact instruction/account requirements.
- Pump.fun and PumpSwap fee schedule at execution time.
- Provider/RPC reliability, priority fee behavior, compute budget, and transaction simulation semantics.
- Token authority/holder/insider data completeness and freshness.
- Live buy/sell behavior. No real-money test has been run.
