# PumpFun FOMO Radar — Vercel + Telegram Cloud Architecture

Status: **architecture proposal / not deployed**. This document intentionally does not enable trading.

## Audit result

The existing PumpFun monitor is a long-running Python process. It connects to PumpPortal over WebSocket, verifies mint data with read-only RPC calls, stores observations in SQLite, and sends optional Telegram notifications. The existing Dockerfile runs the monitor continuously and expects writable persistent storage at `/app/data`.

Vercel Functions are request-driven/serverless and are not a suitable direct host for this persistent WebSocket process or a local SQLite database that must survive restarts. Do not deploy `agent.pumpfun.run_agent` as a Vercel Function or Cron route. Vercel can host a small HTTPS control plane/webhook, while the actual worker must run on an always-on container/worker host with durable storage. That separate worker may incur cost; availability of an always-on free tier has not been verified.

Existing Telegram integration is **outbound notifications only**. It has no inbound command handler, no authenticated owner allowlist, and no shared durable pause/status state. Do not claim /status, /pause, or /resume work until implemented and tested.

## Proposed topology

```text
PumpPortal WebSocket
        |
        v
Python worker (Dockerfile.pumpfun; persistent process)
  - scanner + read-only mint checks
  - SQLite on persistent volume
  - trading hard-disabled
  - sends alert messages to Telegram
  - reads desired monitor state from durable control store
        |                               ^
        | outbound HTTPS                | authenticated command updates
        v                               |
Telegram Bot API <---- webhook ---- Vercel HTTPS Function
                                  - validates Telegram secret token
                                  - validates chat ID + sender user ID allowlist
                                  - accepts only /status /pause /resume
                                  - writes command/state to durable store
                                  - never signs or broadcasts transactions
```

## Important Vercel limitation

A Vercel Function cannot directly share its in-memory state or a local SQLite file reliably with a separately hosted worker. Before enabling command controls, choose a durable shared store accessible to both services (for example, a managed Postgres/KV product supported by the account). Do not assume the existing Vercel project has a database attached. Configure credentials as private environment variables; never put them in source, build args, logs, or this document.

## Telegram security requirements

1. Set Telegram webhook to the Vercel HTTPS endpoint using Telegram's webhook secret-token feature; verify the corresponding header in constant time.
2. Configure a fixed allowlist of the owner's numeric Telegram user ID and expected chat ID in private environment variables. Never trust a username alone.
3. Ignore group chats by default; accept only private chat commands from the allowlisted user and expected chat.
4. Accept exact command names only: `/status`, `/pause`, `/resume`. Ignore arbitrary arguments and unknown commands.
5. Rate-limit updates, bound request body size, and return generic errors without secrets.
6. Use durable desired state with an explicit default of `paused` until provisioning and health checks are complete. A worker restart must preserve pause state.
7. `/pause` means stop processing new observations/alerts after a well-defined checkpoint; it must not pretend to cancel an in-flight network operation. `/resume` resumes monitoring only, never trading.
8. Do not accept `/buy`, `/sell`, wallet/private-key commands, or any command that can enable execution.

## State model

- `monitor_state`: `paused` | `running`; initial state must be `paused`.
- `updated_at`, `updated_by_user_id`, `source_update_id` (unique Telegram update ID for idempotency).
- Worker heartbeat and last successful WebSocket connection timestamp.
- Last error category only (never provider exception text, credentials, or signed URLs).

`/status` reports monitor desired state, worker heartbeat age, last data connection state, and `Execution: DISABLED`. It must not reveal environment variables, local paths containing personal data, or raw provider responses.

## Rollout stages

### Stage 0 — read-only audit (current)
- Confirm branch and existing implementation; do not touch `main`, `BiP4444/`, or `BiP4444-PR5-AUDIT/`.
- Keep trading disabled.

### Stage 1 — isolated control-plane prototype
- Add a Vercel webhook route with request authentication, owner/chat allowlists, exact command parsing, size limits, and tests.
- Use an injected durable-store interface; fail closed when no store is configured.
- Unit-test spoofed sender/chat, invalid webhook secret, duplicate update IDs, unknown commands, and store errors.
- Do not configure a production Telegram webhook yet.

### Stage 2 — worker integration
- Add a small control-state client to the worker; default paused when store is missing/unreachable.
- Test restart persistence, pause/resume checkpoints, stale heartbeat reporting, and failure recovery.
- Keep all buy/sell/signing/broadcast paths unavailable.

### Stage 3 — deploy and smoke test
- Deploy the Vercel control route to Preview first and attach a durable store.
- Deploy the Python worker separately with `Dockerfile.pumpfun` and a persistent volume.
- Add runtime secrets privately: PumpPortal data-only key, Telegram bot token, owner numeric user ID, expected chat ID, webhook secret, and database credentials. Do not send secrets to chat or commit them.
- Test from the owner private Telegram chat; verify unauthorized senders cannot change state.
- Enable Production webhook only after tests pass and owner reviews deployment configuration.

## Environment variable names (names only; no values)

Vercel control route:
- `TELEGRAM_BOT_TOKEN` (only if the route registers/uses Telegram API)
- `TELEGRAM_WEBHOOK_SECRET`
- `TELEGRAM_OWNER_USER_ID`
- `TELEGRAM_OWNER_CHAT_ID`
- `CONTROL_STORE_URL` / provider-specific credentials

Worker:
- `PUMPPORTAL_API_KEY` (must be data-only; do not host wallet-capable credentials)
- `SOLANA_RPC_URL` (optional read-only RPC)
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `CONTROL_STORE_URL` / provider-specific credentials
- `PUMPFUN_RUN_FOREVER=true`
- `PUMPFUN_SCAN_SECONDS=3600`
- `PUMPFUN_DB_PATH=/app/data/pumpfun_monitor.sqlite3`

Do not print or retrieve decrypted environment-variable values as part of an audit.

## Acceptance checklist

- [ ] Existing PumpFun unit suite passes.
- [ ] Control route rejects forged webhook headers.
- [ ] Unauthorized user/chat cannot read status or change state.
- [ ] Duplicate Telegram update is idempotent.
- [ ] `/pause` persists through worker restart and blocks new monitor processing.
- [ ] `/resume` resumes monitoring only.
- [ ] Store/network failure causes fail-closed paused state.
- [ ] Worker health and stale heartbeat are observable without leaking secrets.
- [ ] Telegram alert and command smoke tests pass in Preview.
- [ ] Logs and tests confirm `Execution: DISABLED`; no transaction signing/broadcast path is added.
- [ ] Production webhook and worker are explicitly configured by the owner.

## Current conclusion

This is a plan, not a working cloud deployment. The existing code can send Telegram alerts, but authenticated inbound commands and a shared persistent state store do not yet exist. Vercel alone is not enough to host the current always-on WebSocket worker. No production environment variables were read, changed, or exposed, and no deployment or live transaction was performed.
