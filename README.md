# ✦ AutoMint CLI

**NFT Minter Terminal** — paste OpenSea URL atau contract address, auto-detect tiers, cek eligibility kamu, countdown ke jadwal buka, eksekusi mint otomatis pake private key.

Gak perlu ribet. Tinggal `automint` → paste URL → enter → selesai.

---

## Daftar Isi

- [Persyaratan](#persyaratan)
- [Install](#install)
- [Setup `.env`](#setup-env)
- [Pasang Command](#pasang-command)
- [Cara Pakai](#cara-pakai)
  - [Mode Interaktif (paling gampang)](#1-mode-interaktif-paling-gampang)
  - [Mode Langsung (pake argumen)](#2-mode-langsung-pake-argumen)
  - [Dry-Run (coba dulu, gak ngirim tx)](#3-dry-run-coba-dulu-gak-ngirim-tx)
  - [Contract Langsung (gak perlu OS API Key)](#4-contract-langsung-gak-perlu-os-api-key)
  - [Chain Lain / Custom RPC](#5-chain-lain--custom-rpc)
- [Yang Terjadi Setelah Detect](#yang-terjadi-setelah-detect)
  - [Kalo Tier Masih Scheduled](#kalo-tier-masih-scheduled)
  - [Kalo Tier Udah Live](#kalo-tier-udah-live)
  - [Kalo Ada 2+ Tier Eligible](#kalo-ada-2-tier-eligible)
  - [Kalo Gak Eligible](#kalo-gak-eligible)
- [Hasil Mint](#hasil-mint)
- [Chain Support](#chain-support)
- [CLI Arguments](#cli-arguments)
- [Struktur Project](#struktur-project)
- [Log](#log)
- [Peringatan Keamanan](#peringatan-keamanan)
- [Troubleshooting](#troubleshooting)

---

## Persyaratan

| Barang | Keterangan |
|---|---|
| Python | 3.10+ |
| Wallet | Ethereum wallet dengan private key. **Buat wallet khusus** AutoMint, jangan wallet utama! |
| OpenSea API Key | (opsional kalo pake `--contract`) Daftar gratis di [opensea.io/account/api](https://opensea.io/account/api) |
| Internet | Koneksi ke RPC publik & OpenSea API |

---

## Install

```bash
# Clone repo — HTTPS recommended (gak perlu setup SSH)
git clone https://github.com/Poeroro/automint-cli.git
# Atau SSH kalo udah setup key
# git clone git@github.com:Poeroro/automint-cli.git
cd automint-cli

# Buat virtual environment
# Windows: python -m venv venv
# Linux/Mac: python3 -m venv venv
python -m venv venv

# Aktifkan
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate
venv\Scripts\activate

# Install semua dependency
python -m pip install -r requirements.txt
```

## Setup `.env`

```bash
# Linux/Mac: copy template
cp .env.example .env

# Windows: copy template
copy .env.example .env

# Lalu edit .env:
# Linux/Mac: nano .env  atau  vim .env
# Windows: notepad .env  atau  code .env
```

Isi file `.env`:

```env
# ─── WAJIB ───
PRIVATE_KEY=0x1234...  # Private key wallet khusus kamu
OPENSEA_API_KEY=***   # Dari https://opensea.io/account/api

# ─── OPSIONAL: Custom RPC per Chain ───
# Biarkan kosong kalo mau pake RPC default (Flashbots untuk ETH)
# RPC_ETH=https://eth-mainnet.g.alchemy.com/v2/xxx
# RPC_BASE=https://base-mainnet.g.alchemy.com/v2/xxx
# RPC_OP=https://optimism-mainnet.g.alchemy.com/v2/xxx
# RPC_ARB=https://arbitrum-mainnet.g.alchemy.com/v2/xxx
# RPC_POLYGON=https://polygon-mainnet.g.alchemy.com/v2/xxx
# RPC_BSC=https://bsc-mainnet.g.alchemy.com/v2/xxx
```

**Wajib:** kunci file `.env` biar gak kebaca orang lain:

```bash
# Linux/Mac
chmod 600 .env

# Windows — gak perlu chmod (NTFS permission beda sistem).
# Cukup pastikan file gak di-share publik.
```

> CLI otomatis ngecek permission `.env` (Linux/Mac). Kalo terlalu terbuka (＞600), bakal muncul warning merah dan minta konfirmasi. Windows skip check ini karena NTFS beda sistem permission.

## Pasang Command

Supaya tinggal ketik `automint` dari mana aja:

```bash
# ─── Linux/Mac ───
sudo tee /usr/local/bin/automint > /dev/null << 'SCRIPT'
#!/bin/bash
cd /path/ke/automint-cli
if [ -f "venv/bin/python3" ]; then
    exec venv/bin/python3 automint.py "$@"
elif [ -f ".venv/bin/python3" ]; then
    exec .venv/bin/python3 automint.py "$@"
else
    exec python3 automint.py "$@"
fi
SCRIPT
sudo chmod +x /usr/local/bin/automint
# Ganti /path/ke/automint-cli dengan directory project kamu

# ─── Windows (PowerShell) ───
# Bikin automint.cmd di folder project:
#   @echo off
#   python venv\Scripts\python.exe automint.py %*
# Lalu tambah folder project ke PATH, atau jalankan pake:
#   venv\Scripts\python automint.py [args]
```

Selesai. Sekarang tinggal `automint` enter (Linux/Mac) atau `python automint.py` (Windows).

---

## Cara Pakai

### 1. Mode Interaktif (paling gampang)

Cukup ketik:

```bash
# Linux/Mac:
automint

# Windows:
python automint.py
```

Nanti muncul:

```
╭──────────────────────────────────────────╮
│  ✦ AutoMint CLI  —  NFT Minter Terminal  │
╰──────────────────────────────────────────╯

Target NFT
  Paste OpenSea URL atau contract address (0x...)
>
```

**Yang lo lakukan:**
1. Paste URL OpenSea (misal `https://opensea.io/collection/pudgy-penguins`) — enter
2. Atau paste contract address (`0xbd3531da5cf5857e7cfaa92426877b022e612cf8`) — enter
3. Ketik `y` kalo mau dry-run dulu (cek doang, gak ngirim tx), enter kalo mau mint beneran

```
Dry-run only? (cek doang, gak mint) [y/N] > y
```

Selesai. CLI otomatis:
- **Chain auto-detect** — nyari contract di ETH → Base → OP → Arbitrum → Polygon → BSC
- Detect tiers + price + jadwal
- Cek eligibility wallet kamu
- Estimasi biaya

### 2. Mode Langsung (pake argumen)

Kalo udah tau mau mint apa, langsung kasih argumen:

```bash
# Linux/Mac:
automint --url https://opensea.io/collection/pudgy-penguins
automint --contract 0xbd3531da5cf5857e7cfaa92426877b022e612cf8

# Windows:
python automint.py --url https://opensea.io/collection/pudgy-penguins
python automint.py --contract 0xbd3531da5cf5857e7cfaa92426877b022e612cf8
```

### 3. Dry-Run (coba dulu, gak ngirim tx)

Pake `--dry-run` kalo mau cek dulu tanpa beneran mint:

```bash
# Linux/Mac:
automint --url https://opensea.io/collection/pudgy-penguins --dry-run
automint --contract 0xbd3531da5cf5857e7cfaa92426877b022e612cf8 --dry-run

# Windows:
python automint.py --url https://opensea.io/collection/pudgy-penguins --dry-run
python automint.py --contract 0xbd3531da5cf5857e7cfaa92426877b022e612cf8 --dry-run
```

Dry-run bakal:
1. Detect contract + chain + tiers + price + jadwal
2. Load wallet dari `.env`
3. Cek eligibility tiap tier
4. Estimasi gas + total cost
5. **Tidak ada tx yang dikirim** — aman buat testing

### 4. Contract Langsung (gak perlu OS API Key)

Kalo males daftar OpenSea API key, tinggal pake contract address:

```bash
# Linux/Mac:
automint --contract 0xbd3531da5cf5857e7cfaa92426877b022e612cf8 --dry-run

# Windows:
python automint.py --contract 0xbd3531da5cf5857e7cfaa92426877b022e612cf8 --dry-run
```

Chain auto-detect jalan otomatis. Gak butuh `OPENSEA_API_KEY`.

### 5. Chain Lain / Custom RPC

Chain auto-detect, tapi kalo mau paksa chain tertentu:

```bash
# Linux/Mac:
automint --contract 0x... --chain base
automint --url https://opensea.io/collection/... --chain polygon
automint --url ... --rpc https://eth-mainnet.g.alchemy.com/v2/xxx

# Windows:
python automint.py --contract 0x... --chain base
python automint.py --url https://opensea.io/collection/... --chain polygon
python automint.py --url ... --rpc https://eth-mainnet.g.alchemy.com/v2/xxx
```

Alias chain: `eth`, `base`, `op` / `optimism`, `arb` / `arbitrum`, `matic` / `polygon`, `bsc`.

Kalo pake custom RPC, CLI verifikasi chainId. Kalo gak cocok — warning + abort. Dana lo aman.

---

## Yang Terjadi Setelah Detect

### Kalo Tier Masih Scheduled

```
⏳ Countdown: Allowlist opens at 2026-06-27 14:00:00 UTC
Auto-mint with selected gas at countdown end...
⏱  02:34:17  ████████░░░░░░░░░░░░
   [Press Ctrl+C to cancel]
```

Pilih gas setelah quantity → CLI otomatis countdown → execute pas 0. `Ctrl+C` selama countdown kalo cancel.

### Kalo Tier Udah Live

```
💰 Estimating cost...

Cost Estimate:
  Mint Price:  0.003000 ETH
  Gas Units:   120,000
  Gas Price:   5.23 Gwei
  Gas Cost:    0.000627 ETH
  Total:       0.003627 ETH

✅ Balance sufficient (0.050000 >= 0.003627)

🔥 Gas Price Selection
  [0] 🐢 Low    (1.0 Gwei)
  [1] 🚶 Medium (3.0 Gwei)     ← default
  [2] 🚀 High   (10.0 Gwei)
  [3] ⚙️ Custom

Allowlist is LIVE — auto-minting...
🚀 executing...
```

Pilih gas → langsung auto-mint via Flashbots private mempool.

### Kalo Ada 2+ Tier Eligible

```
Select tier:
  1. Allowlist (0.003 ETH)
  2. Public (0.005 ETH)
> 1
```

Tinggal ketik nomor. Kalo cuma 1 eligible → auto-select langsung, gak perlu milih.

### Kalo Gak Eligible

```
┌───┬────────────┬────────┬──────────┬──────────────────────────┐
│ # │ Tier       │ Price  │ Eligible │ Reason                   │
├───┼────────────┼────────┼──────────┼──────────────────────────┤
│ 1 │ Team       │ FREE   │ ❌ NO    │ not whitelisted          │
│ 2 │ Allowlist  │ 0.003  │ ❌ NO    │ insufficient: 0.01 < 0.003│
│ 3 │ Public     │ 0.005  │ ❌ NO    │ insufficient: 0.01 < 0.005│
└───┴────────────┴────────┴──────────┴──────────────────────────┘

✕ Wallet not eligible for any tier
```

Top up wallet atau cari NFT lain.

---

## Hasil Mint

Kalo sukses:

```
╭──────────────────────────────────────╮
│          ✅ MINT SUCCESS              │
│                                      │
│ Tx:      0xabc123...def456           │
│ Block:   21,543,201                  │
│ Gas:     85,432 units @ 5.23 Gwei   │
│ Gas Fee: 0.000447 ETH               │
│ Total:   0.003447 ETH               │
╰──────────────────────────────────────╯
```

Tx hash bisa lo klik (link explorer). Buka di browser buat cek status.

Kalo gagal:

```
╭────────────────────────────────╮
│        ❌ MINT FAILED           │
│                                │
│ Tx:     0xabc123...            │
│ Error:  Transaction reverted   │
╰────────────────────────────────╯
```

Kemungkinan: udah mint duluan, gak eligible pas eksekusi, atau contract error.

---

## Chain Support

| Chain | Chain ID | Currency | RPC Default | Explorer |
|---|---|---|---|---|
| Ethereum `eth` | 1 | ETH | `rpc.flashbots.net` (private mempool) | etherscan.io |
| Base `base` | 8453 | ETH | `base-rpc.publicnode.com` | basescan.org |
| Optimism `op` | 10 | ETH | `mainnet.optimism.io` | optimistic.etherscan.io |
| Arbitrum `arb` | 42161 | ETH | `arb1.arbitrum.io/rpc` | arbiscan.io |
| Polygon `matic` | 137 | MATIC | `polygon-bor.publicnode.com` | polygonscan.com |
| BSC `bsc` | 56 | BNB | `bsc-dataseed.binance.org` | bscscan.com |

Priority RPC: `--rpc` CLI > `RPC_CHAIN` di `.env` > public default (tabel atas)

---

## CLI Arguments

```bash
automint [-h] [--url URL] [--contract CONTRACT] [--chain CHAIN]
         [--rpc RPC] [--dry-run] [--wallet WALLET]
```

| Argumen | Fungsi |
|---|---|
| `--url URL` | OpenSea collection URL (misal `https://opensea.io/collection/...`) |
| `--contract CONTRACT` | NFT contract address langsung (`0x...`) |
| `--chain CHAIN` | Paksa chain (skip auto-detect). Contoh: `eth`, `base`, `polygon` |
| `--rpc RPC` | Custom RPC URL. Override env & default |
| `--dry-run` | Cek doang — detect + eligibility + estimate, gak kirim tx |
| `--wallet WALLET` | Wallet index buat multi-account. Contoh: `--wallet 0` atau `--wallet all` buat batch |
| `-h`, `--help` | Tampilkan help |

Kalo gak ada `--url` atau `--contract`, CLI bakal minta input interaktif.

---

## Struktur Project

```
automint-cli/
├── automint.py             # Entry point utama (auto-exec dari symlink)
├── .env.example            # Template env variable
├── .gitignore              # .env gak masuk git
├── requirements.txt        # Dependency Python
├── automint.log            # Log hasil mint (JSON lines)
└── src/
    ├── config.py           # Chain config, RPC multichain, env loader, retry
    ├── detect.py           # OS API resolve + on-chain detect + auto-chain
    ├── eligibility.py      # Cek whitelist, free mint, balance, gas estimate
    ├── executor.py         # Build tx, sign, countdown, send, wait receipt
    └── display.py          # Rich CLI output (tables, panel, warna)
```

---

## Log

Semua hasil mint tercatat di `automint.log` (format JSON lines):

```json
{"timestamp": "2026-06-26 12:00:00 UTC", "chain": "ethereum", "contract": "0xbd35...", "tier": "Public", "price": 0.005, "status": "success", "tx_hash": "0xabc123..."}
```

Bisa dicek pake:
```bash
# Linux/Mac:
cat automint.log
tail -f automint.log

# Windows:
type automint.log
# (gak ada real-time tail di CMD, pake PowerShell Get-Content -Wait automint.log)
```

---

## Peringatan Keamanan

1. **Wallet khusus** — jangan pake wallet utama. Buat wallet baru khusus AutoMint.
2. **Private key di `.env`** — jangan pernah commit ke GitHub. `.gitignore` udah configured.
3. **Permission `.env`** (Linux/Mac) — harus 600 (`chmod 600 .env`). CLI warning kalo kebuka. Windows skip check ini.
4. **Chain mismatch** — kalo custom RPC chainId gak cocok, CLI abort. Dana lo aman.
5. **Multi-key support** — multiple wallet via `PRIVATE_KEYS=0x...,0x...` di `.env`. Pilih wallet index atau `all` untuk batch mint.
6. **Test pake dry-run dulu** — sebelum beneran mint, jalankan `--dry-run` biar tau estimasi biaya.

---

## Troubleshooting

### "OPENSEA_API_KEY not set"
Isi `OPENSEA_API_KEY` di `.env`. Atau pake `--contract 0x...` langsung (gak butuh OS API).

### ".env permission too open"
**Linux/Mac:** Jalanin `chmod 600 .env`. Ketik `y` kalo mau lanjut (gak disarankan).
**Windows:** Abaikan — permission check gak jalan di Windows.

### "Could not auto-detect chain"
Contract gak ketemu di chain mana pun. Pake `--chain eth` / `--chain base` manual.

### "RPC not connected"
Coba pake `--rpc https://eth-mainnet.g.alchemy.com/v2/xxx`. Atau set `RPC_ETH` di `.env`.

### "Chain mismatch"
Custom RPC chainId gak cocok sama chain. Cek URL RPC atau hapus `--rpc`.

### "Transaction reverted"
Kemungkinan: udah mint duluan, gak eligible pas real mint, atau contract pake method beda. Cek di explorer.

### "Insufficient balance"
Top up wallet. Cek balance sama total cost di estimasi.

### Gak tau harus ngapain?
Tinggal:
- **Linux/Mac:** `automint` enter, paste URL, enter, `y` enter.
- **Windows:** `python automint.py` enter, paste URL, enter, `y` enter.

Selesai.
