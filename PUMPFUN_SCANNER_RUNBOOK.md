# PumpFun FOMO Radar — read-only scanner and LLM monitor runbook

## What this stage does
The scanner connects to PumpPortal's third-party data WebSocket, subscribes to new-token and migration events, normalizes basic fields, deduplicates each mint/event type during the run, and emits JSON Lines. The monitor runner can optionally send normalized event fields to a configured OpenAI-compatible LLM endpoint for cautious triage.

It is read-only: it never requests a wallet, signs a transaction, submits a transaction, or calls a buy/sell endpoint. LLM decisions are limited to WATCH or REJECT. Missing configuration, malformed responses, unsupported actions, and request failures all fall back to WATCH_ONLY. No model response can authorize a trade.

PumpPortal is a third-party provider, not the Pump.fun protocol itself. Check its current terms, reliability, API limits, and fee policies before depending on it. Event scores and LLM opinions do not establish liquidity, holder concentration, token authorities, creator history, or rug-pull safety.

## Configure PumpPortal safely
The scanner reads `PUMPPORTAL_API_KEY` from the runtime environment and builds the WebSocket URL in memory. Never put a real key in `.env.example`, source code, command-line arguments, GitHub files, or logs. If PumpPortal issued the API key alongside a wallet/private key, treat it as trading-capable: do not add it to Vercel or any hosted environment for this read-only scanner. Prefer a dedicated data-only credential if the provider offers one. The current scanner only subscribes to the free `subscribeNewToken` and `subscribeMigration` streams; do not add paid trade/account subscriptions.

On Termux, set the key in the current shell without sharing its value:
```bash
read -rsp "PumpPortal API key: " PUMPPORTAL_API_KEY; export PUMPPORTAL_API_KEY; echo
```
This keeps the value out of shell history. Do not run `env`, `printenv`, or commands that dump the variable. Close the shell when finished to clear this session variable.

## Run locally
Install requirements from the repository root:

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -p "test_pumpfun_*.py" -v
PUMPFUN_SCAN_SECONDS=60 python -m agent.pumpfun.scanner
```

To run scanner plus optional LLM advisory and read-only mint-account checks, configure `SOLANA_RPC_URL` with an HTTPS Solana RPC endpoint. If it is absent or fails, the mint check is recorded as UNKNOWN and no buy is permitted. This checks the SPL mint layout and mint/freeze authority flags only; it does not verify holder concentration, liquidity, creator history, bonding-curve/PumpSwap state, or sellability.

To run scanner plus optional LLM advisory:

```bash
PUMPFUN_SCAN_SECONDS=60 PUMPFUN_DB_PATH=data/pumpfun_monitor.sqlite3 SOLANA_RPC_URL=https://your-rpc-endpoint.example python -m agent.pumpfun.run_agent
```

Without LLM_API_KEY (or OPENAI_API_KEY) and LLM_MODEL (or OPENAI_MODEL), the runner operates in WATCH_ONLY mode and does not make an LLM request. Configure an HTTPS OpenAI-compatible endpoint with LLM_BASE_URL if needed. API usage may incur separate charges; a ChatGPT subscription does not automatically include API credits. Keep all keys in local environment variables or a secret store—never commit them.

The scan window defaults to 60 seconds and can be set from 1 to 3600 seconds with PUMPFUN_SCAN_SECONDS. Stop with Ctrl+C.

## Output and limitations
Each new event is printed as one JSON object per line and persisted in a SQLite database. The store deduplicates mint/event pairs across restarts; repeated observations update the stored count and latest normalized fields. No event does not prove the market is inactive: the provider may be disconnected, delayed, or filtering events. The current implementation has no reconnect/backfill guarantee and no on-chain verification. SQLite persistence is local to the configured path; it does not provide a shared database or hosted always-on runtime. Treat all fields as untrusted. The same mint may legitimately have one creation event and one migration event.

## Required next steps
- Add bounded reconnect with backoff, provider-health state, and event-time freshness checks.
- Cross-check mint and curve/pool state through a reliable Solana RPC/indexer; the current mint parser is only one partial check.
- Add liquidity, holder concentration, mint/freeze authority and creator history from verifiable sources.
- Add a persisted paper-trading ledger and exit simulation.
- Only later, separately review quote construction, fees, minimum output, exact transaction simulation, signer isolation, and explicit live activation.
