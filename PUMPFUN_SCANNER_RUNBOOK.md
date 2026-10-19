# PumpFun FOMO Radar — read-only scanner runbook

## What this stage does
The scanner connects to PumpPortal's third-party data WebSocket, subscribes to new-token and migration events, normalizes basic fields, deduplicates each mint/event type during the run, and emits JSON Lines. It is read-only: it never requests a wallet, signs a transaction, submits a transaction, or calls a buy/sell endpoint.

PumpPortal is a third-party provider, not the Pump.fun protocol itself. Check its current terms, reliability, API limits, and fee policies before depending on it. This scanner intentionally labels every event `WATCH_ONLY`; its score is only a transparent triage heuristic and does not establish liquidity, holder concentration, token authorities, or rug-pull safety.

## Run locally
Install the existing requirements, then run from the repository root:

```bash
python -m unittest discover -s tests -v
PUMPFUN_SCAN_SECONDS=60 python -m agent.pumpfun.scanner
```

The scanner runs for at most 60 seconds by default. Set `PUMPFUN_SCAN_SECONDS` to another value from 1 to 3600 to change the window. Stop it with Ctrl+C.

## Output and limitations
Each event is printed as one JSON object per line. No event does not prove the market is inactive: the provider may be disconnected, delayed, or filtering events. The current implementation has no reconnect/backfill guarantee and no on-chain verification. Treat all fields as untrusted. The same mint may legitimately have one creation event and one migration event.

## Required next steps
- Add bounded reconnect with backoff, provider-health state, and event-time freshness checks.
- Cross-check mint and curve/pool state through a reliable Solana RPC/indexer.
- Add liquidity, holder concentration, mint/freeze authority and creator history from verifiable sources.
- Add a persisted paper-trading ledger and exit simulation.
- Only later, separately review quote construction, fees, minimum output, exact transaction simulation, signer isolation, and explicit live activation.
