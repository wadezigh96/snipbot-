#!/data/data/com.termux/files/usr/bin/bash
# Free local-host fallback for Android Termux. Does not configure trading.
set -euo pipefail
umask 077

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG_FILE="${PUMPFUN_CONFIG_FILE:-$HOME/.config/pumpfun-radar.env}"
DATA_DIR="${PUMPFUN_DATA_DIR:-$HOME/.local/share/pumpfun-radar}"
DB_FILE="$DATA_DIR/pumpfun_monitor.sqlite3"

if [[ ! -f "$CONFIG_FILE" ]]; then
  printf 'Missing private config file: %s\n' "$CONFIG_FILE" >&2
  printf 'Create it with chmod 600; never commit it or paste secrets into chat.\n' >&2
  exit 2
fi
if [[ "$(stat -c '%a' "$CONFIG_FILE" 2>/dev/null || true)" != "600" ]]; then
  printf 'Unsafe config permissions. Run: chmod 600 %s\n' "$CONFIG_FILE" >&2
  exit 2
fi

# Config is a trusted shell file owned by the user; never use downloaded content here.
set -a
# shellcheck disable=SC1090
source "$CONFIG_FILE"
set +a

if [[ -z "${PUMPPORTAL_API_KEY:-}" ]]; then
  printf 'PUMPPORTAL_API_KEY is required in the private config file.\n' >&2
  exit 2
fi
if [[ -n "${TELEGRAM_BOT_TOKEN:-}" && -z "${TELEGRAM_CHAT_ID:-}" ]] || [[ -z "${TELEGRAM_BOT_TOKEN:-}" && -n "${TELEGRAM_CHAT_ID:-}" ]]; then
  printf 'Set both Telegram variables or leave both empty.\n' >&2
  exit 2
fi

mkdir -p "$DATA_DIR"
chmod 700 "$DATA_DIR"
export PUMPFUN_RUN_FOREVER=true
export PUMPFUN_SCAN_SECONDS="${PUMPFUN_SCAN_SECONDS:-3600}"
export PUMPFUN_DB_PATH="$DB_FILE"

cd "$REPO_ROOT"
exec python -m agent.pumpfun.run_agent
