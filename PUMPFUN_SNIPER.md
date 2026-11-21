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
