# JARUM 5/6

Sniper web lokal untuk memindai token yang sudah berumur sekitar 5–6 jam di Solana dan Robinhood Chain, lalu menyiapkan beli lewat FOMO.

## Cara buka

```bash
cd sniper-fomo
python3 -m http.server 8080
```

Buka http://localhost:8080 . Jangan buka file HTML langsung: browser memblokir fetch API publik dari `file://`.

## Yang dilakukan

- Ambil pool baru Solana dari GeckoTerminal, Robinhood Chain dari GeckoTerminal atau DexScreener.
- Saring umur default 5–6,5 jam, likuiditas, sisi jual, jumlah pembeli, dan dump 1 jam.
- Skor anti-rug 0–99 dari heuristik publik. Bukan audit.
- Tiket FOMO menyalin kontrak dan membuka fomo.family. Tidak ada seed phrase.

Kunci fomoapi.io opsional, hanya di localStorage browser ini.
