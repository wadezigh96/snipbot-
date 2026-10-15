# SnipBot BNB — Autonomous Meme Sniper Agent

Fully autonomous AI agent for BNB Chain meme coins.

**Target:** four.meme + Flap  
**Mode:** Fully Autonomous  
**Risk:** 3–5% wallet per trade  
**Pairs:** BNB (+ USDT ready)  
**Anti-rug:** LP burn → Holder/dev → Volume ($8k–$15k)

Built for **BNB Chain Set and Earn** (ERC-8004).

---

## Install & Run

```bash
git clone https://github.com/wadezigh96/snipbot-
cd snipbot-
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# isi PRIVATE_KEY + NETWORK=bsc (atau bsc-testnet)
```

### 1. Register agent (ERC-8004)

```bash
python -m agent.register
```

Gasless di BSC via MegaFuel. Simpan `agent_id` di `agent_state.json`.

### 2. Jalankan agent

```bash
python -m agent.main
```

Agent akan:
1. Scan listing baru four.meme (API + TokenCreate event)
2. Scan listing baru Flap (Portal TokenCreated)
3. Filter anti-rug (LP, holder, volume)
4. Auto-buy jika score ≥ 58 (respect 3–5% risk)
5. Track open positions

---

## Structure

```
agent/
  contracts.py          # addresses + ABIs
  register.py           # ERC-8004
  main.py               # autonomous loop
  scanner/
    fourmeme.py         # API + on-chain
    flap.py             # Portal events
  filters/
    antirug.py          # LP → holder → volume
  portfolio/
    manager.py          # sizing + exposure
  execution/
    trader.py           # buyTokenAMAP + swapExactInput
```

---

## Risk defaults

| Param | Value |
|-------|-------|
| Max per trade | 4% (atur di .env 0.03–0.05) |
| Max total exposure | 25% |
| Min volume | $8,000 |
| Max volume | $15,000 |
| Slippage | 3% |

---

## Set and Earn checklist

- [x] Public repo  
- [x] ERC-8004 registration script  
- [x] Real scanner four.meme + Flap  
- [x] Real trader (curve buy/sell)  
- [x] Anti-rug filter  
- [ ] List agent di marketplace shortlist  
- [ ] Minimal 3 hire + 5 on-chain actions di 3 hari  

---

## Disclaimer

Meme trading = high risk. Hanya pakai dana yang siap hilang.  
Filter anti-rug adalah heuristik, **bukan** audit keamanan.
