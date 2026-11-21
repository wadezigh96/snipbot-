#!/data/data/com.termux/files/usr/bin/bash
# Sniper runner (paper by default; live only when the private config opens
# the double gate). Mirrors pumpfun-worker.sh config handling.
set -euo pipefail
umask 077

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_FILE="${SNIPER_CONFIG_FILE:-$HOME/.config/pumpfun-sniper.env}"

if [[ ! -f "$CONFIG_FILE" ]]; then
  printf 'Missing private config file: %s\n' "$CONFIG_FILE" >&2
  printf 'Create it with chmod 600; never commit it or paste secrets into chat.\n' >&2
  exit 2
fi
if [[ "$(stat -c '%a' "$CONFIG_FILE" 2>/dev/null || true)" != "600" ]]; then
  printf 'Unsafe config permissions. Run: chmod 600 %s\n' "$CONFIG_FILE" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$CONFIG_FILE"
set +a

: "${PUMPPORTAL_API_KEY:?PUMPPORTAL_API_KEY is required in the private config file}"
: "${SOLANA_RPC_URL:?SOLANA_RPC_URL is required in the private config file}"

MODE="${SNIPER_MODE:-paper}"
if [[ "$MODE" == "live" ]]; then
  if [[ "${SNIPER_LIVE_ENABLED:-}" != "true" || "${SNIPER_LIVE_CONFIRM:-}" != "I_UNDERSTAND_LIVE_TRADING" ]]; then
    printf 'Live mode refused: SNIPER_LIVE_ENABLED=true and the confirm phrase are both required.\n' >&2
    exit 2
  fi
  if [[ -z "${SOLANA_KEYPAIR_PATH:-}" || ! -f "${SOLANA_KEYPAIR_PATH}" ]]; then
    printf 'Live mode refused: SOLANA_KEYPAIR_PATH must point to a keypair file outside the repo.\n' >&2
    exit 2
  fi
  printf 'LIVE MODE: real transactions possible. Bankroll at risk: %s USD.\n' "${MICRO_BANKROLL_USD:-5}"
else
  printf 'PAPER MODE: no transactions will be sent.\n'
fi

cd "$REPO_ROOT"
exec python -m agent.pumpfun.run_live
