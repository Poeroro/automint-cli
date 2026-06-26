# AutoMint CLI

NFT Minter Terminal. Auto-detect tiers, cek eligibility, countdown, auto-execute mint.

## Fitur

- **Input:** OpenSea URL atau contract address langsung
- **Detect:** OS API v2 + on-chain `eth_call` → tiers + price + jadwal
- **Eligibility:** whitelist check, balance check, free mint simulation
- **Countdown:** live countdown ke jadwal buka, auto-mint after countdown
- **Auto-mint:** build tx → sign pake private key → send → wait receipt
- **RPC:** Multi-chain dari `.env` + override via `--rpc`
- **Report:** tx hash, gas, total cost, link explorer

## Setup

```bash
git clone <repo-url>
cd automint-cli
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — isi PRIVATE_KEY + OPENSEA_API_KEY
```

## .env

```env
# WAJIB
PRIVATE_KEY=0x...
OPENSEA_API_KEY=your_key_here

# OPSIONAL — custom RPC per chain
# RPC_ETH=https://eth-mainnet.g.alchemy.com/v2/xxx
# RPC_BASE=https://base-mainnet.g.alchemy.com/v2/xxx
# RPC_OP=https://optimism-mainnet.g.alchemy.com/v2/xxx
# RPC_ARB=https://arbitrum-mainnet.g.alchemy.com/v2/xxx
# RPC_POLYGON=https://polygon-mainnet.g.alchemy.com/v2/xxx
# RPC_BSC=https://bsc-mainnet.g.alchemy.com/v2/xxx
```

## Usage

```bash
# Dari OpenSea URL
python automint.py --url https://opensea.io/collection/cool-i-guess-crew

# Dari contract address + chain
python automint.py --contract 0x6de7...b67 --chain base

# Custom RPC
python automint.py --url https://opensea.io/collection/unijett --rpc https://eth.drpc.org

# Dry-run (detect + estimate only, no tx)
python automint.py --url https://opensea.io/collection/cool-i-guess-crew --dry-run
```

## Struktur

```
automint-cli/
├── automint.py          # Entry point
├── .env.example         # Template env
├── requirements.txt
└── src/
    ├── config.py        # Chain config + RPC multichain dari env
    ├── detect.py        # OS API + on-chain detect
    ├── eligibility.py   # Eligibility check + gas estimate
    ├── executor.py      # Build tx, sign, send, countdown
    └── display.py       # CLI output (rich)
```

## Chain Support

ETH, Base, Optimism, Arbitrum, Polygon, BSC.

## Peringatan

Gunakan wallet khusus AutoMint, **bukan wallet utama**. Private key ada di `.env` — jaga baik-baik. Jangan commit `.env` ke GitHub.
