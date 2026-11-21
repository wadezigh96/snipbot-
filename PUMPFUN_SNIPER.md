# LLM Sniper — Anti-Rugpull + Bubble Maps + Micro-Bankroll Paper Mode

Stacked on the PumpFun FOMO Radar branches (PR #1 → #2 → #3). This layer adds
the three things the radar was missing. **Execution remains DISABLED**: the
output ceiling is `PAPER_BUY_CANDIDATE`. No signer, no live trade path.

## Pipeline

```
PumpPortal event (Pump.fun, Solana)
  → mint check            agent/pumpfun/rpc.py        (authority flags)
  → Bubble Maps holders   agent/pumpfun/bubblemap.py  (top1/top10, HHI, dev, linked clusters)
  → anti-rug gate         agent/pumpfun/antirug.py    (deterministic, fail-closed)
  → LLM sniper score      agent/pumpfun/llm_sniper.py (APPROVE_PAPER / WATCH / REJECT)
  → risk policy           agent/pumpfun/risk.py       (position / daily-loss limits)
  → paper engine          agent/pumpfun/paper.py      ($5 micro plan + exit ladder)
```

Rules that cannot be bypassed:

- Unknown data = REJECT. No holder data, no verified mint, no liquidity/curve
  evidence, or no successful *sell* simulation → the anti-rug gate fails.
- The LLM can only veto. `APPROVE_PAPER` with score ≥ 70 on top of a passed
  anti-rug gate yields a paper candidate; the LLM can never override a
  failed gate, change position sizes, or enable live trading.
- Malformed LLM output fails closed to `WATCH_ONLY`.

## Bubble Maps checks

`bubblemap.py` mirrors what bubblemaps.io visualizes: supply that looks
distributed but is controlled by a few linked wallets.

| Signal | Reject when |
|---|---|
| Top-1 holder share | > 20% |
| Top-10 holder share | > 60% |
| Largest linked cluster (same-funder wallet group) | > 30% |
| Dev wallet share | > 10% |

Solana data comes from read-only RPC (`getTokenLargestAccounts` +
`getTokenSupply`). The same core analyzer accepts EVM holder lists
(`analyze_holder_dicts`), which is how Robinhood Chain / Pons tokens from
`index.html` (JARUM) can be scored when an explorer/launchpad holder list is
available.

## Robinhood + FOMO app

Robinhood Chain tokens stay on the existing JARUM flow in `index.html`:
Pons launchpad feed → anti-rug score → manual handoff to the FOMO app
(fomo.family), where the user signs in their own FOMO account. This repo
never custodies keys for FOMO and never signs on the user's behalf there.

## Micro-bankroll mode: $5 → $1,500 target

Preset in `paper.py` (`MicroPlan`): bankroll $5, $1.00 per position, max 3
open, $1.50 daily loss limit, $0.75 fee reserve, exit ladder
SL −45% → TP1 2x sell 50% + break-even stop → TP2 5x sell 25% → TP3 10x
sell rest → 6h time stop. Fees modelled at 1% + $0.02 per swap.

**Honest math** (`target_math`): $5 → $1,500 is a 300× multiple. Even if
*every* trade won, it needs ~+33% compounded over 20 straight wins, ~+12%
over 50, ~+5.9% over 100. Real meme trading has rugs, dead tokens, and fees,
so treat $1,500 as a moonshot scoreboard for the paper engine — the engine
exists to measure whether the strategy survives at all before any real
money moves. Most memecoins go to zero; only trade money you can lose.

## Run (monitor + new layers)

Same worker as the runbook (`PUMPFUN_SCANNER_RUNBOOK.md`); each event output
now also carries `bubblemap`, `antirug`, and `llm_sniper` objects. Because no
sell simulation exists yet, the anti-rug gate currently reports REJECT for
execution purposes on every candidate — that is the intended fail-closed
behavior until a verified sell-quote/simulation stage is added.

## Tests

```bash
python -m pytest tests/test_pumpfun_bubblemap.py tests/test_pumpfun_antirug.py \
  tests/test_pumpfun_llm_sniper.py tests/test_pumpfun_paper.py -q
```

## Live stage (added in PR #5) — built, but OFF by default

- `simulation.py` — Solana RPC `simulateTransaction` for buys, plus the
  sell-route proof: a pre-buy sell simulation that fails *only* because the
  wallet holds none of the token still proves the sell path exists; any
  program error rejects.
- `signer.py` — local signer. Keypair comes from `SOLANA_KEYPAIR_PATH`
  (Solana CLI JSON file **outside** the repo) or a local-shell secret.
  Never commit a keypair, never paste one into chat or `.env` in the repo.
- `executor.py` — the only broadcast path. Requires BOTH
  `SNIPER_LIVE_ENABLED=true` and `SNIPER_LIVE_CONFIRM=I_UNDERSTAND_LIVE_TRADING`,
  then re-checks anti-rug, LLM candidate status, and the risk policy, in
  that order, before building/simulating/signing/sending. Every refusal is
  explicit; outcomes are written to the trade ledger (PR #2).

Activating live is the owner's deliberate local step: fund a *separate*
sniper wallet with only the $5 bankroll, set the two gate variables and the
keypair path on the host, and run a live runner that calls the executor.
Losing the whole $5 must be acceptable before that switch is flipped.

## Goal tracker (the honest version of "$5 → $1,500")

`paper.py` now includes `goal_progress` (milestones $10 → $25 → $50 → $100 →
$250 → $500 → $1,000 → $1,500, remaining multiple, bankroll-alive check) and
`next_position_usd` compounding: position size = 20% of equity, floored at
$1, capped at $25, fee reserve always untouched, size 0 when equity falls
below the reserve (strategy is dead; stop). This fixes the *plan*, not the
odds: the cap on loss is the $5 itself, and the tracker exists so progress
— or failure — is measured instead of imagined.

## Runner (PR #6) — ready to run

```bash
pip install -r requirements-pumpfun.txt

# Paper (default, no wallet, no transactions):
SNIPER_MODE=paper python -m agent.pumpfun.run_live

# Live (deliberate, owner-only):
SNIPER_MODE=live SNIPER_LIVE_ENABLED=true \
SNIPER_LIVE_CONFIRM=I_UNDERSTAND_LIVE_TRADING \
SOLANA_KEYPAIR_PATH=$HOME/.config/sniper-keypair.json \
python -m agent.pumpfun.run_live
```

Termux: `deploy/termux/pumpfun-live.sh` reads `~/.config/pumpfun-sniper.env`
(chmod 600) and re-checks the live gate in shell before Python even starts.

Paper mode polls DexScreener every 30s for open positions and runs the exit
ladder, printing `goal_progress` JSON lines. Live mode tracks open positions
in memory for the risk policy; exits for live positions are not automated
yet — sell from the wallet/FOMO app, or extend the executor with a sell
path mirroring `buy`. Live startup refuses (exit 2) when the gate is closed
or no keypair is configured.

## Auto sell + early entry (PR #7)

- `executor.sell()` mirrors `buy()`: live gate -> build -> *strict* sell
  simulation (the wallet holds the tokens now, so any failure refuses) ->
  sign -> broadcast -> ledger.
- Live exits are automated in the runner: `poll_live_positions` polls
  DexScreener prices, the `LadderTracker` decides a fraction, the token
  amount is computed from the wallet's real on-chain balance
  (`fetch_token_balance`), and the executor sells it. A refused sell
  restores the fraction and retries next poll.
- **Moonbag ladder**: SL -45% -> TP1 2x sell 40% (break-even stop) ->
  TP2 5x sell 25% -> TP3 10x sell 20% -> remaining 15% moonbag rides with
  a -50%-from-peak trailing stop (24h max). Only the moonbag can capture
  a >1000% move; the earlier stages exist to remove risk on the way.
- **Early mode** (`SNIPER_EARLY_MODE=true`, `early.py`): only creation
  events inside the early curve window (0.5-35 SOL virtual reserves),
  creator initial buy <= 3 SOL, and a *curve-excluded* Bubble Map —
  the bonding-curve account (which holds most supply by design) is
  removed from holder analysis, so what remains visible is real holder
  concentration: top-1 <= 15%, top-10 <= 50%, no linked cluster > 15%.

Reality check: early entry raises both upside and rug exposure. These
filters screen the measurable bundle/authority signals; they cannot
prove a dev will not rug after entry — that is what the stop loss and
the staged exits are for.
