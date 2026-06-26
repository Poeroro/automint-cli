# ✦ AutoMint CLI

**NFT Minter Terminal** — auto-detect koleksi NFT, cek eligibility tiap tier, countdown ke jadwal buka, eksekusi mint otomatis via private key.

---

## Fitur

| Fitur | Detail |
|---|---|
| **Input** | OpenSea URL atau contract address langsung |
| **Detect** | OpenSea API v2 + `eth_call` on-chain — contract, chain, tiers, price, jadwal |
| **Tier Detection** | Public, Allowlist, FCFS, GTD, Team — lengkap dengan price + start time |
| **Eligibility** | Whitelist check, free mint simulation, balance check |
| **Countdown** | Live countdown ke jadwal buka tier, auto-mint pas countdown 0 |
| **Eksekusi** | Build tx → sign pake private key → send → wait receipt |
| **Multi-Chain** | ETH, Base, Optimism, Arbitrum, Polygon, BSC |
| **RPC** | Public default. Bisa override per-chain via `.env` atau `--rpc` |
| **Keamanan** | ChainId verification kalo custom RPC, `.env` permission check |

---

## Persyaratan

- Python 3.10+
- Wallet Ethereum dengan private key (buat wallet **khusus** AutoMint, jangan wallet utama!)
- OpenSea API Key ([daftar gratis](https://opensea.io/account/api))

---

## Setup

```bash
# Clone
git clone git@github.com:Poeroro/automint-cli.git
cd automint-cli

# Virtual env
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Buat .env dari template
cp .env.example .env

# Edit .env — isi PRIVATE_KEY + OPENSEA_API_KEY
nano .env
```

### File `.env`

```env
# ─── WAJIB ───
PRIVATE_KEY=0x1234...  # Private key wallet kamu (dengan 0x di depan)
OPENSEA_API_KEY=cdef...  # API key dari https://opensea.io/account/api

# ─── OPSIONAL: Custom RPC per Chain ───
# Biarkan kosong untuk pake RPC publik
# RPC_ETH=https://eth-mainnet.g.alchemy.com/v2/xxx
# RPC_BASE=https://base-mainnet.g.alchemy.com/v2/xxx
# RPC_OP=https://optimism-mainnet.g.alchemy.com/v2/xxx
# RPC_ARB=https://arbitrum-mainnet.g.alchemy.com/v2/xxx
# RPC_POLYGON=https://polygon-mainnet.g.alchemy.com/v2/xxx
# RPC_BSC=https://bsc-mainnet.g.alchemy.com/v2/xxx
```

> ⚠️ **Wajib:** `chmod 600 .env` — permission 600 biar private key aman. CLI bakal ngecek permission dan warning kalo terlalu terbuka.

---

## Cara Pakai

### 1. Detect + Estimate aja — dry run

```bash
python automint.py --url https://opensea.io/collection/pudgy-penguins --dry-run
```

Atau pake contract address langsung (gak perlu OS API key):

```bash
python automint.py --contract 0xbd3531da5cf5857e7cfaa92426877b022e612cf8 --chain eth --dry-run
```

Dry-run bakal:
1. Detect contract + tiers + price + jadwal
2. Load wallet dari `.env`
3. Cek eligibility tiap tier
4. Estimasi gas + total cost
5. **Tidak ada tx yang dikirim**

### 2. Eksekusi mint

```bash
# Dari OpenSea URL
python automint.py --url https://opensea.io/collection/pudgy-penguins

# Dari contract address
python automint.py --contract 0xbd3531... --chain eth
```

Flow:
1. Detect → tampilkan tiers
2. Cek wallet + balance
3. Cek eligibility tiap tier
4. Pilih tier (auto-select kalo cuma 1 eligible)
5. Estimasi biaya
6. Countdown kalo tier masih scheduled
7. Konfirmasi → sign → send → tunggu receipt
8. Tampilkan report (tx hash, gas, block, link explorer)

### 3. Multi-chain

```bash
# Base
python automint.py --url https://opensea.io/collection/cool-guys --chain base

# Arbitrum
python automint.py --contract 0x... --chain arbitrum

# Polygon (bisa pake alias)
python automint.py --contract 0x... --chain matic
```

Alias chain: `eth` = `ethereum`, `op` = `optimism`, `arb` = `arbitrum`, `matic` = `polygon`, `bsc` = `binance`

### 4. Custom RPC

```bash
python automint.py --url https://opensea.io/collection/... --rpc https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
```

Kalau custom RPC dipake, CLI bakal verifikasi chainId cocok. Kalo beda — warning + abort.

### 5. Chain tidak dikenal di URL

Kalo OpenSea URL gak specify chain, default ke Ethereum. Paksa pake `--chain`:

```bash
python automint.py --url https://opensea.io/collection/some-base-collection --chain base
```

---

## Chain Support

| Chain | Chain ID | Currency | RPC Publik | Explorer |
|---|---|---|---|---|
| Ethereum `eth` | 1 | ETH | `eth.drpc.org` | etherscan.io |
| Base `base` | 8453 | ETH | `base-rpc.publicnode.com` | basescan.org |
| Optimism `op` | 10 | ETH | `mainnet.optimism.io` | optimistic.etherscan.io |
| Arbitrum `arb` | 42161 | ETH | `arb1.arbitrum.io/rpc` | arbiscan.io |
| Polygon `matic` | 137 | MATIC | `polygon-bor.publicnode.com` | polygonscan.com |
| BSC `bsc` | 56 | BNB | `bsc-dataseed.binance.org` | bscscan.com |

RPC priority: `--rpc` CLI > `RPC_CHAIN` di `.env` > public default

---

## Struktur Project

```
automint-cli/
├── automint.py           # Entry point — argparse, main flow
├── .env.example          # Template env (isi PRIVATE_KEY + OPENSEA_API_KEY)
├── .gitignore            # .env gak di-commit
├── requirements.txt      # Dependencies
├── automint.log          # Log hasil mint (JSON lines)
└── src/
    ├── config.py         # Chain config, RPC multichain, env loader, retry
    ├── detect.py         # OpenSea API resolve + on-chain tier detect
    ├── eligibility.py    # Eligibility check per tier + gas estimate
    ├── executor.py       # Build tx, sign, countdown, send, wait receipt
    └── display.py        # Rich CLI output (tables, colors, report)
```

---

## Log

Semua hasil mint tercatat di `automint.log` (format JSON lines):

```json
{"timestamp": "2026-06-26 12:00:00 UTC", "chain": "ethereum", "contract": "0xbd35...", "tier": "Public", "price": 0.005, "status": "success", "tx_hash": "0xabc123..."}
```

---

## Peringatan Keamanan

1. **Wallet khusus** — jangan pake wallet utama. Buat wallet baru khusus AutoMint.
2. **Private key** — tersimpan di `.env`, jangan pernah commit ke GitHub. `.gitignore` udah configured.
3. **Permission `.env`** — harus 600 (`chmod 600 .env`). CLI warning kalo terlalu terbuka.
4. **Chain mismatch** — kalo custom RPC chainId gak cocok, CLI abort. Dana bisa hilang kalo lanjut.
5. **OS API key** — wajib diisi di `.env`. Daftar gratis di [opensea.io/account/api](https://opensea.io/account/api). Alternatif: pake `--contract` langsung (gak butuh OS API).

---

## CLI Arguments

```
usage: automint.py [-h] (--url URL | --contract CONTRACT)
                   [--chain CHAIN] [--rpc RPC] [--wallet WALLET] [--dry-run]

  --url URL             OpenSea collection URL
  --contract CONTRACT   NFT contract address (0x...)
  --chain CHAIN         Chain: eth/base/op/arb/polygon/bsc
  --rpc RPC             Custom RPC URL (override env/default)
  --wallet WALLET       Wallet index (multi-key — future)
  --dry-run             Detect + estimate only, no mint
```

---

## Troubleshooting

### "OPENSEA_API_KEY not set"
Isi `OPENSEA_API_KEY` di `.env`, atau pake `--contract 0x... --chain eth` langsung.

### ".env permission too open"
Jalanin `chmod 600 .env`. Abort atau jawab `y` kalo yakin (gak disarankan).

### "Chain mismatch"
Custom RPC chainId gak cocok sama chain yang dipilih. Cek RPC URL atau hapus `--rpc`.

### "RPC not connected"
Coba pake `--rpc` dengan URL RPC yang reliable. Atau set `RPC_ETH` di `.env`.

### "Transaction reverted"
Kemungkinan: udah mint, gak eligible, atau contract panggil method lain. Cek di explorer.
