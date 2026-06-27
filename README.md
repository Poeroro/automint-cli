# ✦ AutoMint CLI

> NFT Minter Terminal — paste URL OpenSea, auto-detect tier, cek eligibility, countdown ke jadwal buka, eksekusi mint otomatis.

---

## Daftar Isi

- [Cara Kerja](#cara-kerja)
- [Persyaratan](#persyaratan)
- [Instalasi](#instalasi)
  - [Windows](#windows)
  - [Linux / macOS](#linux--macos)
- [Konfigurasi](#konfigurasi)
  - [Wajib — Private Key](#wajib--private-key)
  - [Opsional — RPC, Gas, Notifikasi, dll](#opsional)
- [Cara Pakai](#cara-pakai)
  - [1. Mode Interaktif](#1-mode-interaktif)
  - [2. Langsung via Argumen](#2-langsung-via-argumen)
  - [3. Dry-Run (coba dulu)](#3-dry-run-coba-dulu)
  - [4. Contract Address Langsung](#4-contract-address-langsung)
  - [5. Watch Mode (auto-mint saat tier live)](#5-watch-mode)
  - [6. Batch Multi-Wallet](#6-batch-multi-wallet)
- [Alur Setelah Detect](#alur-setelah-detect)
- [Chain yang Didukung](#chain-yang-didukung)
- [Semua Argumen CLI](#semua-argumen-cli)
- [Fitur Lanjutan](#fitur-lanjutan)
- [Log Mint](#log-mint)
- [Struktur Project](#struktur-project)
- [Keamanan](#keamanan)
- [Troubleshooting](#troubleshooting)

---

## Cara Kerja

```
URL / Contract Address
        ↓
  Detect on-chain          ← tiers, harga, jadwal, chain
        ↓
  Cek eligibility          ← whitelist, merkle proof, balance
        ↓
  Pilih tier + quantity
        ↓
  Countdown (jika scheduled) → eksekusi saat 0
        ↓
  Kirim tx → tunggu receipt → laporan + notifikasi
```

---

## Persyaratan

| Kebutuhan | Detail |
|-----------|--------|
| **Python** | 3.10 atau lebih baru |
| **Git** | Untuk clone repo |
| **Wallet** | Private key wallet Ethereum — **buat wallet khusus, jangan pakai wallet utama!** |
| **Internet** | Koneksi ke RPC publik |

---

## Instalasi

### Windows

Buka **Command Prompt** atau **PowerShell**, jalankan perintah berikut satu per satu:

**1. Clone repository**
```cmd
git clone https://github.com/Poeroro/automint-cli.git
cd automint-cli
```

**2. Buat virtual environment**
```cmd
python -m venv venv
```

**3. Aktifkan virtual environment**
```cmd
venv\Scripts\activate
```
> Kalau berhasil, muncul `(venv)` di awal baris terminal.

**4. Install dependency**
```cmd
pip install -r requirements.txt
```

**5. Siapkan file konfigurasi**
```cmd
copy .env.example .env
notepad .env
```

Isi `PRIVATE_KEY` di Notepad, simpan, tutup. Lanjut ke bagian [Konfigurasi](#konfigurasi).

---

### Linux / macOS

Buka **Terminal**, jalankan perintah berikut:

**1. Clone repository**
```bash
git clone https://github.com/Poeroro/automint-cli.git
cd automint-cli
```

**2. Buat virtual environment**
```bash
python3 -m venv venv
```

**3. Aktifkan virtual environment**
```bash
source venv/bin/activate
```
> Kalau berhasil, muncul `(venv)` di awal baris terminal.

**4. Install dependency**
```bash
pip install -r requirements.txt
```

**5. Siapkan file konfigurasi**
```bash
cp .env.example .env
nano .env
```

Isi `PRIVATE_KEY`, tekan `Ctrl+O` → Enter untuk simpan, `Ctrl+X` untuk keluar.

**6. Kunci file konfigurasi** _(wajib di Linux/macOS)_
```bash
chmod 600 .env
```

**7. (Opsional) Pasang shortcut `automint`**

Supaya bisa ketik `automint` dari mana saja tanpa `python automint.py`:

```bash
# Ganti /path/ke/automint-cli dengan lokasi folder kamu
sudo tee /usr/local/bin/automint > /dev/null << 'EOF'
#!/bin/bash
cd /path/ke/automint-cli
source venv/bin/activate
exec python automint.py "$@"
EOF

sudo chmod +x /usr/local/bin/automint
```

---

## Konfigurasi

Semua konfigurasi ada di file `.env` di folder project.

### Wajib — Private Key

```env
PRIVATE_KEY=0xabc123...
```

> **Penting:** Gunakan wallet khusus AutoMint. Jangan pernah pakai wallet utama yang menyimpan aset besar.

Untuk **lebih dari satu wallet**, gunakan `PRIVATE_KEYS` (pisah koma):
```env
PRIVATE_KEYS=0xabc...,0xdef...,0x123...
```

---

### Opsional

Semua pengaturan di bawah ini **tidak wajib**. Biarkan kosong untuk menggunakan nilai default.

#### OpenSea API Key
```env
# Daftar gratis di: https://docs.opensea.io/reference/api-keys
# Tanpa key: limit 16 request/window. Kalau kena error 401/429, set ini.
OPENSEA_API_KEY=your_key_here
```

#### Custom RPC per Chain
```env
# Default sudah pakai endpoint publik (PublicNode, dll).
# Isi ini kalau mau pakai Alchemy / Infura untuk lebih stabil.
RPC_ETH=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
RPC_BASE=https://base-mainnet.g.alchemy.com/v2/YOUR_KEY
RPC_OP=https://optimism-mainnet.g.alchemy.com/v2/YOUR_KEY
RPC_ARB=https://arbitrum-mainnet.g.alchemy.com/v2/YOUR_KEY
RPC_POLYGON=https://polygon-mainnet.g.alchemy.com/v2/YOUR_KEY
RPC_BSC=https://bsc-mainnet.g.alchemy.com/v2/YOUR_KEY
```

#### Gas Guard
```env
# Kalau gas price melebihi batas ini, mint otomatis dibatalkan.
MAX_GAS_GWEI=50
```

#### Merkle Proof (untuk Allowlist contract)
```env
# Biasanya di-fetch otomatis. Isi manual kalau auto-fetch gagal.
MERKLE_PROOF=0xabc...,0xdef...
```

#### Notifikasi Telegram
```env
# Buat bot via @BotFather di Telegram, ambil token + chat ID.
TELEGRAM_BOT_TOKEN=1234567890:AAxxxxxx
TELEGRAM_CHAT_ID=123456789
```

#### Notifikasi Discord
```env
# Di server Discord: Settings → Integrations → Webhooks → Copy URL
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

---

## Cara Pakai

### 1. Mode Interaktif

Cara paling mudah — jalankan tanpa argumen, ikuti instruksi yang muncul.

**Windows:**
```cmd
python automint.py
```

**Linux / macOS:**
```bash
# Kalau sudah pasang shortcut:
automint

# Kalau belum:
python automint.py
```

Yang muncul di layar:
```
╭──────────────────────────────────────────╮
│  ✦ AutoMint CLI  —  NFT Minter Terminal  │
╰──────────────────────────────────────────╯

Target NFT
  Paste OpenSea URL atau contract address (0x...)
>
```

**Langkah:**
1. Paste URL OpenSea → Enter
2. Ketik `y` untuk dry-run (cek tanpa mint), atau langsung Enter untuk mint

---

### 2. Langsung via Argumen

**Windows:**
```cmd
python automint.py --url https://opensea.io/collection/nama-koleksi
python automint.py --contract 0xABC... --chain eth
```

**Linux / macOS:**
```bash
automint --url https://opensea.io/collection/nama-koleksi
automint --contract 0xABC... --chain eth
```

---

### 3. Dry-Run (coba dulu)

Deteksi + estimasi biaya tanpa mengirim transaksi. **Selalu jalankan ini dulu** sebelum mint beneran.

**Windows:**
```cmd
python automint.py --url https://opensea.io/collection/nama-koleksi --dry-run
python automint.py --contract 0xABC... --chain eth --dry-run
```

**Linux / macOS:**
```bash
automint --url https://opensea.io/collection/nama-koleksi --dry-run
automint --contract 0xABC... --chain eth --dry-run
```

Dry-run akan:
- Detect chain, tier, harga, jadwal
- Cek eligibility wallet
- Estimasi gas dan total biaya
- **Tidak mengirim transaksi apapun**

---

### 4. Contract Address Langsung

Kalau sudah punya contract address, bisa langsung pakai tanpa OpenSea.
`--chain` **wajib** diisi kalau pakai contract address.

**Windows:**
```cmd
python automint.py --contract 0xABC... --chain eth
python automint.py --contract 0xABC... --chain base --dry-run
```

**Linux / macOS:**
```bash
automint --contract 0xABC... --chain eth
automint --contract 0xABC... --chain base --dry-run
```

Alias chain yang tersedia: `eth`, `base`, `op`, `arb`, `matic`, `bsc`

---

### 5. Watch Mode

Poll contract secara otomatis tiap N detik. Begitu ada tier yang live, langsung auto-mint — tidak perlu pantau manual.

**Windows:**
```cmd
:: Poll tiap 15 detik (default)
python automint.py --url https://opensea.io/collection/... --watch

:: Poll tiap 30 detik
python automint.py --url https://opensea.io/collection/... --watch --watch-interval 30
```

**Linux / macOS:**
```bash
# Poll tiap 15 detik (default)
automint --url https://opensea.io/collection/... --watch

# Poll tiap 30 detik
automint --url https://opensea.io/collection/... --watch --watch-interval 30
```

- Tekan `Ctrl+C` kapan saja untuk berhenti
- Notifikasi Telegram/Discord dikirim saat tier live (kalau dikonfigurasi)
- Kalau `MAX_GAS_GWEI` di-set, CLI tunggu gas turun dulu sebelum mint

---

### 6. Batch Multi-Wallet

Mint dengan semua wallet sekaligus menggunakan `--wallet all`.
Pastikan `PRIVATE_KEYS` sudah diisi di `.env`.

**Windows:**
```cmd
python automint.py --url https://opensea.io/collection/... --wallet all
python automint.py --url https://opensea.io/collection/... --wallet all --dry-run
```

**Linux / macOS:**
```bash
automint --url https://opensea.io/collection/... --wallet all
automint --url https://opensea.io/collection/... --wallet all --dry-run
```

Pilih wallet tertentu dengan index:
```
--wallet 0    ← wallet pertama
--wallet 1    ← wallet kedua
--wallet all  ← semua wallet sekaligus
```

---

## Alur Setelah Detect

### Tier Masih Terjadwal

```
⏳ Countdown: Allowlist opens at 2026-07-01 14:00:00 UTC
Auto-mint at countdown end...
   ⏱  02:34:17  [████████░░░░░░░░░░░░]
   [Press Ctrl+C to cancel]
```

CLI otomatis countdown dan mint saat angka menyentuh 0. Tekan `Ctrl+C` untuk batal.

### Tier Sudah Live

```
💰 Estimating cost...

  Mint Price:  0.003000 ETH
  Gas Units:   120,000
  Gas Price:   5.23 Gwei
  Gas Cost:    0.000627 ETH
  Total:       0.003627 ETH

✅ Balance sufficient (0.050000 >= 0.003627)

🔥 Gas Price Selection
  [0] 🐢 Low     (1.0 Gwei)   ~36s
  [1] 🚶 Medium  (3.0 Gwei)   ~12s   ← default
  [2] 🚀 High    (10.0 Gwei)  ~6s
  [3] ⚙️  Custom

Select gas [0-3, default=1] >
```

Pilih opsi gas → mint langsung dieksekusi.

### Ada 2+ Tier Eligible

```
Select tier:
  1. Allowlist (0.003 ETH)
  2. Public    (0.005 ETH)
> 
```

Ketik nomor tier yang diinginkan. Kalau hanya 1 tier eligible, auto-select.

### Tidak Eligible

```
┌───┬───────────┬───────┬──────────┬──────────────────────────────┐
│ # │ Tier      │ Price │ Eligible │ Reason                       │
├───┼───────────┼───────┼──────────┼──────────────────────────────┤
│ 1 │ Team      │ FREE  │ ❌ NO    │ not whitelisted              │
│ 2 │ Allowlist │ 0.003 │ ❌ NO    │ insufficient: 0.01 < 0.003   │
│ 3 │ Public    │ 0.005 │ ❌ NO    │ insufficient: 0.01 < 0.005   │
└───┴───────────┴───────┴──────────┴──────────────────────────────┘

✕ Wallet not eligible for any tier
```

Top up wallet atau cari koleksi lain.

### Hasil Mint

**Sukses:**
```
╭──────────────────────────────────────────╮
│  ✅ MINT SUCCESS                          │
│                                          │
│  Tx:      0xabc123...def456              │
│  Block:   21,543,201                     │
│  Gas:     85,432 units @ 5.23 Gwei       │
│  Gas Fee: 0.000447 ETH                   │
│  Total:   0.003447 ETH                   │
╰──────────────────────────────────────────╯
   Explorer: https://etherscan.io/tx/0xabc...
```

**Gagal:**
```
╭────────────────────────────────────╮
│  ❌ MINT FAILED                     │
│                                    │
│  Tx:     0xabc123...               │
│  Error:  Transaction reverted      │
╰────────────────────────────────────╯
```

---

## Chain yang Didukung

| Chain | Alias | Chain ID | Currency | Explorer |
|-------|-------|----------|----------|----------|
| Ethereum | `eth` | 1 | ETH | etherscan.io |
| Base | `base` | 8453 | ETH | basescan.org |
| Optimism | `op` | 10 | ETH | optimistic.etherscan.io |
| Arbitrum | `arb` | 42161 | ETH | arbiscan.io |
| Polygon | `matic` | 137 | MATIC | polygonscan.com |
| BSC | `bsc` | 56 | BNB | bscscan.com |

Setiap chain punya **3–4 fallback RPC otomatis**. Kalau endpoint utama down, CLI langsung pindah ke yang berikutnya tanpa perlu setup manual.

Prioritas RPC: `--rpc` (CLI) › `RPC_CHAIN` (`.env`) › endpoint publik default

---

## Semua Argumen CLI

```
python automint.py [--url URL] [--contract ADDR] [--chain CHAIN]
                   [--rpc URL] [--wallet N|all] [--dry-run]
                   [--watch] [--watch-interval SEC]
```

| Argumen | Default | Keterangan |
|---------|---------|------------|
| `--url URL` | — | URL koleksi OpenSea |
| `--contract ADDR` | — | Contract address langsung (`0x...`) |
| `--chain CHAIN` | `ethereum` | Chain target. **Wajib** kalau pakai `--contract` |
| `--rpc URL` | — | Custom RPC. Override env dan default |
| `--wallet N` atau `all` | auto | Index wallet spesifik, atau `all` untuk batch |
| `--dry-run` | off | Deteksi + estimasi saja, tidak kirim transaksi |
| `--watch` | off | Poll terus sampai tier live, lalu auto-mint |
| `--watch-interval SEC` | `15` | Jeda antar poll dalam detik (watch mode) |
| `--help` | — | Tampilkan bantuan |

---

## Fitur Lanjutan

### RPC Fallback Otomatis
Kalau RPC utama gagal atau timeout, CLI otomatis coba endpoint cadangan (Ankr, LlamaRPC, dll). Tidak perlu setup manual.

### Gas Guard
Lindungi diri dari mint saat gas sedang mahal. Set batas di `.env`:
```env
MAX_GAS_GWEI=50
```
Kalau gas aktual melebihi batas, transaksi dibatalkan sebelum dikirim. Di watch mode, CLI menunggu gas turun dulu sebelum eksekusi.

### Sold-Out & Paused Check
Sebelum kirim transaksi, CLI cek on-chain apakah contract sudah sold-out atau di-pause. Mencegah gas terbuang sia-sia dari transaksi yang pasti gagal.

### Gas Bump Otomatis
Kalau transaksi stuck lebih dari 45 detik (belum masuk blok), CLI otomatis kirim ulang dengan gas 15% lebih tinggi (replace-by-fee). Maksimal 3 kali percobaan.

### Merkle Proof (Allowlist)
Contract modern pakai Merkle tree untuk allowlist. CLI auto-fetch proof dari Highlight.xyz / Manifold API. Kalau gagal otomatis, isi manual di `.env`:
```env
MERKLE_PROOF=0xabc...,0xdef...
```

### Notifikasi
Terima notifikasi setiap mint selesai — sukses, gagal, atau pending. Setup di `.env`:
```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
DISCORD_WEBHOOK_URL=...
```

---

## Log Mint

Semua hasil mint tersimpan otomatis di `automint.log` (format JSON per baris):

```json
{"timestamp": "2026-07-01 14:00:00 UTC", "wallet": "0xabc...", "chain": "ethereum", "contract": "0xbd35...", "tier": "Public", "price": 0.005, "quantity": 1, "status": "success", "tx_hash": "0xabc123..."}
```

**Cara baca log:**

Windows (Command Prompt):
```cmd
type automint.log
```

Windows (PowerShell, real-time):
```powershell
Get-Content automint.log -Wait
```

Linux / macOS:
```bash
cat automint.log
tail -f automint.log   # real-time
```

---

## Struktur Project

```
automint-cli/
│
├── automint.py          # Entry point — alur utama CLI
│
├── src/
│   ├── config.py        # Chain config, RPC fallback, env loader, gas guard
│   ├── detect.py        # Detect NFT: OpenSea API + on-chain eth_call paralel
│   ├── eligibility.py   # Cek whitelist, merkle proof, balance wallet
│   ├── executor.py      # Build & sign tx, gas bump, sold-out check, kirim
│   ├── merkle.py        # Fetch Merkle proof (API / .env / cache)
│   ├── notify.py        # Notifikasi Telegram & Discord
│   └── display.py       # Tampilan terminal (tabel, panel, warna)
│
├── test_config.py       # Unit test: config, RPC, wallet
├── test_detect.py       # Unit test: detect, scrape, calldata
├── test_core.py         # Unit test: executor, eligibility
├── test_display.py      # Unit test: semua fungsi tampilan
├── test_integration.py  # Integration test: flow lintas modul
├── test_cli.py          # Black-box test: subprocess CLI
│
├── .env.example         # Template konfigurasi
├── .env                 # Konfigurasi kamu (tidak masuk Git)
├── .gitignore
├── requirements.txt
└── automint.log         # Log hasil mint (dibuat otomatis)
```

---

## Keamanan

1. **Wallet khusus** — buat wallet baru khusus AutoMint. Jangan pakai wallet yang menyimpan aset utama.
2. **Jaga private key** — file `.env` tidak pernah masuk Git (sudah ada di `.gitignore`). Jangan share file ini.
3. **Kunci `.env`** (Linux/macOS) — jalankan `chmod 600 .env`. CLI akan peringatkan kalau permission terlalu terbuka.
4. **Dry-run dulu** — selalu jalankan `--dry-run` sebelum mint beneran untuk cek estimasi biaya.
5. **Gas guard** — set `MAX_GAS_GWEI` di `.env` untuk mencegah mint saat gas sedang mahal.
6. **Chain mismatch** — kalau chain ID custom RPC tidak cocok, CLI otomatis abort. Dana aman.

---

## Troubleshooting

### ✕ API HTTP 401 atau 429
OpenSea rate limit. CLI otomatis retry 3x. Kalau masih gagal, daftar API key gratis:

1. Buka https://docs.opensea.io/reference/api-keys
2. Daftar dan ambil API key
3. Tambahkan ke `.env`:
```env
OPENSEA_API_KEY=your_key_here
```

---

### ✕ .env file not found
File konfigurasi belum dibuat.

**Windows:**
```cmd
copy .env.example .env
notepad .env
```

**Linux / macOS:**
```bash
cp .env.example .env
nano .env
```

---

### ✕ No wallets found
`PRIVATE_KEY` belum diisi di `.env`. Buka `.env` dan isi:
```env
PRIVATE_KEY=0xprivatekeykamudisin...
```

---

### ✕ Chain required with contract address
Kalau pakai `--contract`, wajib tambah `--chain`. Contoh:

**Windows:**
```cmd
python automint.py --contract 0xABC... --chain eth
```

**Linux / macOS:**
```bash
automint --contract 0xABC... --chain eth
```

---

### ✕ No reachable RPC for [chain]
Semua endpoint publik tidak bisa dijangkau. Solusi: set RPC custom di `.env`:
```env
RPC_ETH=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
```
Daftar gratis di [Alchemy](https://www.alchemy.com) atau [Infura](https://infura.io).

---

### ✕ Chain mismatch
Chain ID dari `--rpc` tidak cocok dengan `--chain` yang dipilih. Solusi: hapus `--rpc` atau pastikan URL RPC-nya benar untuk chain tersebut.

---

### ✕ Gas too high: X Gwei > MAX_GAS_GWEI=Y
Gas sedang tinggi dan melebihi batas yang kamu set. Pilihan:
- Tunggu gas turun, coba lagi nanti
- Naikkan batas di `.env`: `MAX_GAS_GWEI=100`
- Pakai `--watch` — CLI otomatis tunggu gas turun sebelum mint

---

### ✕ Transaction reverted
Transaksi gagal di blockchain. Kemungkinan penyebab:
- Sudah pernah mint sebelumnya
- Tidak eligible saat eksekusi berlangsung
- Contract sudah sold-out
- Contract menggunakan method yang berbeda

Cek detail di explorer menggunakan tx hash yang ditampilkan.

---

### ✕ Insufficient balance
Saldo wallet tidak cukup untuk mint + gas. Top up wallet dan jalankan `--dry-run` untuk lihat estimasi biaya terbaru.

---

### ✕ merkle proof required
Contract menggunakan Merkle tree allowlist. CLI sudah mencoba fetch otomatis tapi gagal. Isi proof manual di `.env`:
```env
MERKLE_PROOF=0xabc...,0xdef...
```
Proof bisa didapat dari Discord project atau website mint resmi.

---

### Tidak tahu mulai dari mana?

**Windows** — buka Command Prompt, jalankan:
```cmd
venv\Scripts\activate
python automint.py
```
Paste URL OpenSea → Enter → ikuti instruksi di layar.

**Linux / macOS** — buka Terminal, jalankan:
```bash
source venv/bin/activate
automint
```
Paste URL OpenSea → Enter → ikuti instruksi di layar.
