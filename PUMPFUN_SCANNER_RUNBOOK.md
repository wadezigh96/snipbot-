# PumpFun FOMO Radar — read-only monitor and worker runbook

## Safety boundary

This service observes PumpPortal's third-party WebSocket, performs a partial read-only Solana mint-account check, stores observations in SQLite, and optionally sends Telegram notifications and an LLM advisory. It does not create/import wallets, sign transactions, quote trades, submit transactions, or call buy/sell endpoints. Every event alert says **WATCH ONLY** and **Execution: DISABLED**.

The scanner score is a triage heuristic, not a buy signal. A `VERIFIED` mint status only means the supported base mint layout was parsed; it does not prove that a token is safe, liquid, sellable, or free from concentrated/insider ownership. Unsupported or unknown data must remain UNKNOWN.

## Audit findings addressed in this branch

- WebSocket close/error now raises a generic reconnect signal instead of silently ending a monitor session.
- Monitor health is emitted as JSON lines (connected, disconnected, reconnecting, and notification result).
- Reconnect uses capped exponential backoff (2, 4, 8... up to 60 seconds); provider exception text and credential-bearing URLs are never printed.
- Telegram is optional and best-effort. Missing or failed Telegram configuration does not stop scanning.
- A new mint/event pair is alerted only when SQLite reports it as new; duplicate observations update persistence without sending repeat token alerts.
- The worker container uses a minimal PumpFun-specific requirements file and runs as an unprivileged user.
- Runtime remains read-only; there is no execution switch in this worker.

## Required runtime environment variables

Set these in the hosting provider's private environment/secret settings, never in GitHub source files:

- `PUMPPORTAL_API_KEY`: required data-stream credential. Prefer a dedicated data-only key. If the provider issued it with wallet/private-key capability, do not use it on hosted infrastructure.
- `SOLANA_RPC_URL`: optional HTTPS RPC endpoint. If missing/unavailable, mint checks remain UNKNOWN.
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`: optional; configure both to enable alerts.
- `PUMPFUN_RUN_FOREVER=true`: required for the persistent worker container.
- `PUMPFUN_SCAN_SECONDS=3600`: each WebSocket session window; sessions rotate after this bound.
- `PUMPFUN_DB_PATH=/app/data/pumpfun_monitor.sqlite3`: database location. Attach persistent storage at `/app/data` on the host.
- Optional LLM: `LLM_API_KEY` (or `OPENAI_API_KEY`) and `LLM_MODEL` (or `OPENAI_MODEL`). LLM calls may cost money and are not required for monitoring.

Do not put secrets in Docker build arguments, image layers, command-line arguments, repository files, logs, or screenshots. Do not run `env`/`printenv` when secret variables are exported.

## Telegram setup

1. Create a Telegram bot with the official `@BotFather` account and copy its token directly into the hosting provider's secret settings.
2. Open the bot's private chat and press Start (or send `/start`).
3. Determine the destination chat ID using your own trusted Telegram tooling; do not paste the bot token or private API response into this chat.
4. Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to the worker environment and restart it.
5. Verify delivery using a newly observed event or a controlled staging test. The process reports only `sent`, `failed`, or `disabled`; it does not print the token or Telegram response body.

Telegram delivery is best-effort, not guaranteed. Provider/network failures are recorded as status output and do not stop the scanner.

## Hosting: persistent worker, not a serverless web function

Use an always-on background worker/container service that supports outbound WebSocket connections and persistent disk. This repository includes `Dockerfile.pumpfun` and `requirements-pumpfun.txt`. In the host's service settings, select the custom Dockerfile path `Dockerfile.pumpfun`, configure the environment variables above, and mount persistent disk at `/app/data`.

Do not deploy this worker as a Vercel serverless function or scheduled HTTP endpoint: it needs a long-lived outbound WebSocket and a writable persistent database. The Dockerfile is separate from the repository's ordinary web app build. No hosting provider has been deployed or verified by this code change; hosting credentials and the persistent volume must be configured by the owner.

## Free hosting assessment and $0 fallback

A suitable always-on free managed host is not currently verified. Do not mistake a free web-service tier for a free persistent worker:

- Render's free web services can spin down and have ephemeral filesystems; they do not support persistent disks. That fails the current always-on WebSocket + SQLite requirement.
- Koyeb's free instance cannot run a Worker Service and cannot attach a persistent volume.
- Fly.io's free trial is time-limited and stops without billing setup; do not use it for a zero-cost 24/7 deployment.
- Vercel serverless functions and scheduled HTTP endpoints are not a substitute for a long-lived WebSocket worker with durable local SQLite.

Official references: https://render.com/docs/free, https://www.koyeb.com/docs/reference/instances, https://www.koyeb.com/docs/reference/volumes, and https://fly.io/docs/about/free-trial/.

For strict $0 hosting today, the prepared fallback is a **local Android Termux worker**. SQLite stays in private app storage on the phone; this is persistent local storage, not a managed server and not a guaranteed 24/7 service. Android battery management, network loss, and OS process termination can interrupt it. Do not describe it as production uptime.

### Free local fallback: Android Termux

1. In Termux, install Python and Git if needed, then install the worker dependency from the repository root:

   ```sh
   pkg update
   pkg install python git
   python -m pip install -r requirements-pumpfun.txt
   ```

2. Create a private config file in an editor, not as a command-line argument:

   ```sh
   mkdir -p ~/.config
   nano ~/.config/pumpfun-radar.env
   chmod 600 ~/.config/pumpfun-radar.env
   ```

   File contents (replace placeholders locally; never commit or share this file):

   ```sh
   PUMPPORTAL_API_KEY='YOUR_DATA_ONLY_API_KEY'
   SOLANA_RPC_URL=''
   TELEGRAM_BOT_TOKEN=''
   TELEGRAM_CHAT_ID=''
   ```

   Only use a dedicated data-only PumpPortal key. If the credential can authorize transactions, do not put it on this worker. Configure both Telegram values or leave both empty. The launcher rejects unsafe file permissions and incomplete Telegram configuration.

3. Run the launcher from the repository checkout:

   ```sh
   bash deploy/termux/pumpfun-worker.sh
   ```

   It sets `PUMPFUN_RUN_FOREVER=true`, uses a private data directory under `~/.local/share/pumpfun-radar`, and keeps trading disabled. The worker stores SQLite locally and never prints the configured secrets. To interrupt it, press Ctrl+C.

4. For a longer local test, keep Termux open, prevent Android battery optimization for Termux, and use `termux-wake-lock` only while you intentionally want the phone to stay awake. These measures do not guarantee uninterrupted service.

The launcher is an optional zero-cost local fallback; it does not deploy anything to the internet or guarantee 24/7 availability. For a real remote worker with durable storage, a host that provides persistent disk and always-on compute will be needed, and that may incur costs.

For managed Docker hosting, this repository includes `Dockerfile.pumpfun` and `requirements-pumpfun.txt`. Select the custom Dockerfile path `Dockerfile.pumpfun`, configure the variables above in private host secret settings, and mount persistent disk at `/app/data`. Confirm the mount is writable by UID 10001 before starting the worker. No hosting provider has been deployed or verified by this code change.

## Local run and tests

From the repository root:

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -p "test_pumpfun_*.py" -v
```

For a bounded local monitor session (60 seconds by default):

```bash
PUMPFUN_SCAN_SECONDS=60 python -m agent.pumpfun.run_agent
```

For a persistent worker, set `PUMPFUN_RUN_FOREVER=true` and `PUMPFUN_SCAN_SECONDS=3600`. Ensure the required `PUMPPORTAL_API_KEY` is set in the current environment. Never print the environment or expose the secret in shell history. Use `PUMPFUN_DB_PATH` to select a local database path.

## Operational limits

- Reconnect cannot recover events missed while disconnected; no provider backfill is implemented.
- Backoff is capped at 60 seconds; bad credentials/provider outages can continue retrying and should be monitored.
- Telegram notifications are best-effort and duplicate-suppressed by the local SQLite database.
- SQLite persistence survives container replacement only if the host mounts persistent disk at `/app/data`.
- One monitor instance should use one database file on a supported persistent disk; do not share a SQLite file across multiple hosts.
- Current mint checks do not cover holder concentration, liquidity, creator history, bonding-curve/PumpSwap state, sellability, or all Token-2022 extensions.
- LLM advisory is optional and cannot authorize transactions.
- **Live trading is not implemented or enabled.** Paper trading, quote validation, transaction simulation, persistent risk accounting, and any future signer/execution integration require separate design, tests, and explicit authorization.
