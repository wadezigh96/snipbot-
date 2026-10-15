# SnipBot BNB — Autonomous Meme Sniper Agent

Fully autonomous AI agent for BNB Chain meme coins.

**Target platforms:** four.meme + Flap  
**Mode:** Fully Autonomous  
**Risk:** 3–5% wallet per trade  
**Pairs:** BNB + USDT  
**Anti-rug focus:** LP burn, holder/dev concentration (bubblemap), volume filter

Built for **BNB Chain Set and Earn** campaign (ERC-8004 agent identity).

---

## Quick Start

### 1. Install

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# edit .env — isi PRIVATE_KEY / WALLET_PASSWORD, RPC, dll
```

### 3. Register Agent (ERC-8004)

```bash
python -m agent.register
```

Ini akan:
- Generate agent card
- Daftarkan identity di ERC-8004 (gasless via MegaFuel di BSC)
- Simpan `agent_id` ke `agent_state.json`

### 4. Run Agent

```bash
python -m agent.main
```

---

## Project Structure

```
agent/
  ├── __init__.py
  ├── config.py          # settings & risk params
  ├── register.py        # ERC-8004 registration
  ├── main.py            # entry point (fully autonomous loop)
  ├── scanner/
  │   ├── fourmeme.py    # four.meme new listings
  │   └── flap.py        # Flap new listings
  ├── filters/
  │   └── antirug.py     # LP burn, holder, volume, etc.
  ├── portfolio/
  │   └── manager.py     # position sizing, TP/SL, exposure
  ├── execution/
  │   └── trader.py      # buy/sell on curve + PCS
  └── utils/
      └── logger.py
```

---

## Risk Parameters (default)

| Param | Value |
|-------|-------|
| Max per trade | 3–5% of wallet |
| Min volume | $8k – $10k |
| Max volume (early) | ~$15k |
| Priority filter | LP burn → Holder/dev bubblemap → Volume |
| Supported | BNB + USDT |

---

## Set and Earn Checklist

- [x] Public repo
- [ ] Register wallet di campaign page
- [ ] Register agent via ERC-8004 (mainnet atau testnet)
- [ ] List agent di salah satu marketplace shortlist
- [ ] Dapat minimal 3 hire dari wallet independen
- [ ] Minimal 5 on-chain actions di 3 hari berbeda

---

## Disclaimer

Trading meme coin sangat berisiko. Gunakan hanya dana yang siap hilang.  
Agent ini tidak menjamin profit. Anti-rug filter adalah heuristik, bukan audit.
