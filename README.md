
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

---

## PumpFun LLM Sniper (Solana) — anti-rug + Bubble Maps + $5 paper mode

Layer baru di atas PumpFun FOMO Radar (lihat `PUMPFUN_SNIPER.md`):

- **Anti-rugpull gate** (`agent/pumpfun/antirug.py`) — mint/freeze authority,
  likuiditas/curve, dan simulasi jual; data tidak diketahui = REJECT.
- **Bubble Maps holder check** (`agent/pumpfun/bubblemap.py`) — top-1/top-10,
  HHI, dompet dev, dan cluster dompet terhubung (Solana RPC + holder list EVM
  untuk Robinhood/Pons).
- **LLM sniper** (`agent/pumpfun/llm_sniper.py`) — skor terstruktur
  APPROVE_PAPER/WATCH/REJECT; LLM hanya bisa memveto, tidak bisa meloloskan
  token yang gagal gate deterministik.
- **Paper engine modal kecil** (`agent/pumpfun/paper.py`) — preset $5,
  posisi $1, tangga keluar SL −45% / TP 2x–5x–10x / time-stop 6 jam.
  Target $1.500 = 300×: moonshot untuk diukur di paper mode, bukan janji.
- **Robinhood + FOMO** tetap lewat `index.html` (JARUM → Pons → FOMO):
  tanda tangan selalu di akun FOMO pengguna sendiri.

Eksekusi live tetap **DISABLED** — output tertinggi adalah kandidat paper.
