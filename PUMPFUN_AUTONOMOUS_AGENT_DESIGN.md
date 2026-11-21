# PumpFun FOMO Radar — autonomous agent design

## User goal
The operator wants to deposit approximately USD 10 into a dedicated Solana wallet and let an LLM-assisted agent monitor Pump.fun continuously for up to nine days, evaluate candidates, and manage buys/sells autonomously. USD 3,500 is an aspirational target only, not a forecast or promise; the agent must never optimize for the target by disabling risk checks or increasing exposure without bounds.

## Execution status
- Live trading: DISABLED
- Transaction broadcast: DISABLED
- No wallet is generated/imported by this repository change.
- No private key or seed phrase may be requested in chat, stored in Git, sent to the browser, or written to logs.
- This design is not proof of a working bot and must not be advertised as production-ready.

## Proposed control loop
1. Read new-token and migration events from a documented data source; deduplicate by mint/signature and timestamp observations.
2. Enrich candidates with on-chain mint/program state, curve or PumpSwap status, liquidity/depth, trade flow, holder concentration where reliably available, creator history where available, and suspicious authority/metadata flags.
3. Reject stale, inconsistent, unverified, or unavailable data. Treat social sentiment and LLM output as weak signals, not ground truth.
4. Ask the LLM to rank and explain candidates using a strict structured schema. The LLM may propose a trade, but cannot bypass deterministic risk checks.
5. Obtain a current route/quote and compute conservative expected output after protocol/creator/LP fees, network fee, priority fee, slippage, and price impact.
6. Simulate the exact transaction against current state. Reject missing or failed simulation, unknown program IDs, unsupported token state, or non-positive minimum output.
7. Check persistent portfolio state and the risk gate. Persist an intent before signing/broadcast.
8. Sign with an isolated server-side secret store or local signer; never in browser JavaScript. Broadcast only after the live-activation gate is explicitly enabled by the operator.
9. Reconcile signature, confirmation, balances, fills, and fees. On timeout, inspect status before retrying; never blindly resend.
10. Monitor exit conditions and sell quotes. If the sell path is unavailable, do not claim the position is protected; halt new buys and alert the operator.

## Initial guardrails to validate
- Total starting bankroll: USD 10; no automatic top-ups.
- Maximum per-position cost: USD 1 including the allocated fees.
- Maximum concurrent positions: 2.
- Halt new buys once realized daily loss reaches USD 1.
- Maintain a separate SOL network-fee reserve; its live USD value must be checked before each trade.
- Enforce total exposure, not just per-position size.
- Maximum trade age/data staleness, slippage, price impact, liquidity, and token-risk thresholds must be configured and tested before use.
- No leverage, no averaging down, no martingale, no copy-trading by default.
- Manual emergency stop and automatic halt on RPC/data/accounting uncertainty.
- Nine-day run must have a hard expiry, persistent state, health checks, and alerts; process restarts must not reset loss limits.

## Mandatory release gates
1. Read-only scanner validated against official Pump.fun/PumpSwap docs and current on-chain state.
2. Unit tests plus mocked RPC, malformed data, duplicate events, persistence/restart, quote failure, simulation failure, partial sell, timeout/reconciliation, and fee accounting tests.
3. Dry-run/paper mode running on live read-only data with no signer and no broadcast.
4. Separate isolated wallet and signing architecture reviewed. Never commit credentials.
5. Explicit live activation only after tests and an operator review. Starting the process must not implicitly activate live trading.
6. Monitoring, halt controls, transaction notifications, and a documented recovery procedure verified.

## Important economic reality
USD 10 to USD 3,500 is a 350x return in nine days. The agent must not treat this as a guaranteed outcome or use it as a reason to bypass controls. Memecoins can become illiquid, suffer extreme slippage, or lose nearly all value; fees can consume a material fraction of a small account.
