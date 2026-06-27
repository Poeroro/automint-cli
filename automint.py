#!/usr/bin/env python3

"""AutoMint CLI — NFT Minter Terminal.

Usage:
  automint                           # interactive — masukin URL/contract
  automint --url https://...         # langsung dari URL
  automint --contract 0x... --chain eth [--rpc ...] [--dry-run]

Flow: input → detect → load wallets → eligibility → pilih wallet + tier → execute
"""

import sys
import os
import time
import argparse
import json
from dotenv import load_dotenv

load_dotenv()  # noqa: E402

from src.detect import detect  # noqa: E402
from src.eligibility import check_eligibility, estimate_total_cost  # noqa: E402
from src.executor import execute_mint, wait_for_countdown  # noqa: E402
from src.display import (  # noqa: E402
    show_banner, show_detect_result, show_eligibility,
    show_cost_estimate, show_report, show_wallets, show_gas_menu, console
)  # noqa: E402
from src.config import resolve_chain, get_rpc, CHAINS, get_all_wallets  # noqa: E402
from web3 import Web3  # noqa: E402


LOG_FILE = 'automint.log'
BATCH_RESULTS = []


def check_env_file():
    """Cek .env exist + permission 600 (Linux/Mac only)."""
    env_path = '.env'
    if not os.path.exists(env_path):
        console.print('[yellow]⚠ .env file not found![/yellow]')
        console.print('  Copy [cyan].env.example[/cyan] ke [cyan].env[/cyan] dan isi:')
        console.print('  [yellow]cp .env.example .env[/yellow]')
        console.print('  [yellow]nano .env[/yellow]')
        console.print()
        try:
            ans = input('Continue without .env? (hanya contract langsung) [y/N] > ').strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.exit(1)
        if ans != 'y':
            sys.exit(1)
        return
    if os.name == 'posix':
        mode = os.stat(env_path).st_mode & 0o777
        if mode > 0o600:
            console.print(f'[red]⚠ .env permission {oct(mode)} — too open! Run:[/red]')
            console.print(f'  [yellow]chmod 600 {env_path}[/yellow]')
            console.print()
            try:
                ans = input('Continue anyway? [y/N] > ').strip().lower()
            except (EOFError, KeyboardInterrupt):
                ans = 'n'
            if ans != 'y':
                sys.exit(1)


def verify_chain_id(w3: Web3, chain: str) -> bool:
    """Cek chainId RPC cocok dengan chain yg dipilih."""
    expected = CHAINS.get(chain, {}).get('id')
    if not expected:
        return True
    try:
        actual = w3.eth.chain_id
    except Exception:
        return True
    if actual != expected:
        console.print(f'[red]✕ Chain mismatch! RPC chainId={actual}, expected {chain}(id={expected})[/red]')
        console.print('[yellow]  Dana bisa hilang kalo lanjut![/yellow]')
        return False
    return True


def append_log(entry: dict):
    """Tulis log ke file JSON-lines."""
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except OSError:
        pass


def parse_args():
    p = argparse.ArgumentParser(
        description='AutoMint CLI — NFT Minter Terminal',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh:
  automint                          → interaktif, masukin URL/contract
  automint --url https://opensea.io/collection/...
  automint --contract 0x... --chain eth --dry-run
        """
    )
    p.add_argument('--url', help='OpenSea collection URL')
    p.add_argument('--contract', help='NFT contract address (0x...)')
    p.add_argument('--chain', default='', help='Chain: eth/base/op/arb/polygon/bsc')
    p.add_argument('--rpc', default='', help='Custom RPC URL (override env/default)')
    p.add_argument('--dry-run', action='store_true', help='Detect + estimate only, no mint')
    p.add_argument('--wallet', default='-1', help='Wallet index (multi-account). Contoh: 0 / all')
    return p.parse_args()


def prompt_input(args):
    """Kalo gak ada --url / --contract, minta input dari user."""
    url_or_contract = args.url or args.contract
    if url_or_contract:
        return url_or_contract, args.chain, args.rpc, args.dry_run

    console.print()
    console.print('[bold]Target NFT[/bold]')
    console.print('  Paste [cyan]OpenSea URL[/cyan] atau [cyan]contract address[/cyan] (0x...)')
    val = input('> ').strip()
    while not val:
        val = input('> ').strip()

    rpc = args.rpc

    dry_run = args.dry_run
    if not dry_run:
        ans = input('Dry-run only? (cek doang, gak mint) [y/N] > ').strip().lower()
        dry_run = ans == 'y'

    return val, args.chain, rpc, dry_run


def select_tier_interactive(eligible_tiers, currency):
    """Pilih tier dari eligible. Return tier dict."""
    if len(eligible_tiers) == 1:
        selected = eligible_tiers[0]
        console.print(f'\n[green]→ Auto-selected: {selected["name"]}[/green]')
        return selected

    console.print('\n[bold]Select tier:[/bold]')
    for i, t in enumerate(eligible_tiers, 1):
        price = f'{t["price"]} {currency}' if t['price'] > 0 else 'FREE'
        console.print(f'  [cyan]{i}.[/cyan] {t["name"]} ({price})')
    try:
        choice = int(input('\n> ').strip())
        return eligible_tiers[choice - 1]
    except (ValueError, IndexError):
        console.print('[red]Invalid choice[/red]')
        sys.exit(1)


def prompt_quantity(tier):
    """Minta quantity kalo maxMint > 1."""
    max_mint = tier.get('maxMint', 0)
    quantity = 1
    if max_mint > 1:
        console.print(f'\n[bold]Quantity:[/bold] Max mint per tx = [cyan]{max_mint}[/cyan]')
        try:
            ans = input(f'How many? [1-{max_mint}, enter=1] > ').strip()
            if ans:
                q = int(ans)
                if q < 1 or q > max_mint:
                    console.print(f'[red]Must be 1-{max_mint}[/red]')
                    sys.exit(1)
                quantity = q
        except (ValueError, EOFError, KeyboardInterrupt):
            quantity = 1
        if quantity > 1:
            console.print(f'[green]→ Minting {quantity} NFTs[/green]')
    return quantity


def do_mint(contract, chain, tier, custom_rpc, quantity, wallet_info, dry_run, currency, gas_params=None):
    """Proses mint untuk satu wallet. Handle countdown + auto-execute."""
    status = tier.get('status', 'unknown')

    if status and status.startswith('scheduled:'):
        ts = int(status.split(':')[1])
        console.print(f'\n[bold]⏳ Countdown:[/bold] {tier["name"]} opens at {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts))}')
        console.print('[dim]Auto-mint with selected gas at countdown end...[/dim]')
        ok = wait_for_countdown(ts, tier['name'])
        if not ok:
            return None

    elif status == 'active' or not status:
        console.print(f'\n[green]{tier["name"]} is LIVE — auto-minting...[/green]')

    # Execute
    qty_note = f' × {quantity}' if quantity > 1 else ''
    addr_short = f'{wallet_info["address"][:10]}...{wallet_info["address"][-6:]}'
    console.print(f'\n[bold]🚀 {addr_short} →[/bold] {tier["name"]} @ {currency} {tier["price"]}{qty_note}')

    if dry_run:
        console.print('[yellow]── Dry-run — exiting ──[/yellow]')
        sys.exit(0)

    report = execute_mint(contract, chain, tier, custom_rpc, quantity,
                         wallet_info['private_key'], gas_params)

    # Show report
    show_report(report, chain)

    # Log
    log_entry = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
        'wallet': wallet_info['address'],
        'chain': chain,
        'contract': contract,
        'tier': tier['name'],
        'price': tier.get('price', 0),
        'quantity': quantity,
        'status': report['status'],
        'tx_hash': report.get('tx_hash', ''),
    }
    append_log(log_entry)

    BATCH_RESULTS.append({
        'wallet': wallet_info['address'],
        'tier': tier['name'],
        'quantity': quantity,
        'status': report['status'],
        'tx_hash': report.get('tx_hash', ''),
    })

    return report


def show_batch_summary():
    """Tampilkan ringkasan batch mint."""
    if not BATCH_RESULTS:
        return
    success = [r for r in BATCH_RESULTS if r['status'] == 'success']
    failed = [r for r in BATCH_RESULTS if r['status'] != 'success']
    total_nft = sum(r['quantity'] for r in success)

    console.print('\n')
    console.print('═' * 50)
    console.print('[bold]📊 Batch Summary[/bold]')
    console.print(f'  ✅ {len(success)} success ({total_nft} NFT minted)')
    if failed:
        console.print(f'  ❌ {len(failed)} failed')
        for r in failed:
            console.print(f'     {r["wallet"][:10]}... — {r["status"]}: {r.get("tx_hash", "?")[:18]}...')
    console.print('═' * 50)


def main():
    check_env_file()

    args = parse_args()
    show_banner()

    # ── Step 0: Input ──
    input_str, chain_hint_raw, custom_rpc, dry_run = prompt_input(args)

    chain_hint = resolve_chain(chain_hint_raw)
    if chain_hint_raw and not chain_hint:
        console.print(f'[yellow]⚠ Unknown chain "{chain_hint_raw}" — defaulting to ethereum[/yellow]')
    if not chain_hint:
        chain_hint = 'ethereum'

    # ── Step 1: Detect ──
    console.print(f'\n[bold]🔍 Detecting:[/bold] {input_str[:60]}...')
    result = detect(input_str, chain_hint, custom_rpc)

    if result.get('error'):
        console.print(f'[red]✕ {result["error"]}[/red]')
        sys.exit(1)

    if result.get('warning'):
        console.print(f'[yellow]⚠ {result["warning"]}[/yellow]')

    show_detect_result(result)

    contract = result['contract']
    chain = result['chain']
    tiers = result['tiers']
    currency = CHAINS.get(chain, {}).get('currency', 'ETH')

    if not tiers:
        console.print('[yellow]No tiers detected. Cannot proceed.[/yellow]')
        sys.exit(1)

    # ── RPC ──
    rpc = custom_rpc or get_rpc(chain)
    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        console.print(f'[red]✕ RPC not connected: {chain}[/red]')
        sys.exit(1)
    if custom_rpc:
        if not verify_chain_id(w3, chain):
            if input('Force continue? [y/N] > ').strip().lower() != 'y':
                sys.exit(1)

    # ── Step 2: Load all wallets ──
    all_wallets = get_all_wallets()
    if not all_wallets:
        console.print('[red]✕ No wallets found. Set PRIVATE_KEY or PRIVATE_KEYS in .env[/red]')
        sys.exit(1)

    console.print(f'\n[bold]👛 Wallets loaded:[/bold] {len(all_wallets)}')
    console.print()

    # ── Step 3: Eligibility per wallet ──
    wallets_info = []
    for w in all_wallets:
        address = w['address']
        balance_wei = w3.eth.get_balance(address)
        balance_eth = balance_wei / 1e18

        elig = check_eligibility(contract, chain, address, tiers, custom_rpc)
        eligible_tiers = [t for t in elig if t['eligible']]

        best = eligible_tiers[0] if eligible_tiers else None

        wallets_info.append({
            **w,
            'balance_wei': balance_wei,
            'balance_eth': balance_eth,
            'eligibility': elig,
            'eligible_tiers': eligible_tiers,
            'best_tier': best,
        })

    # ── Step 4: Loop wallet → tier → quantity → execute ──
    first_pass = True
    while True:
        # Filter eligible wallets
        eligible_wallets = [w for w in wallets_info if w['best_tier']]
        if not eligible_wallets:
            console.print('[red]✕ No wallet eligible for any tier[/red]')
            break

        if first_pass:
            console.print('\n[bold]🔎 Eligibility Check[/bold]')
            show_wallets(eligible_wallets, currency)

        # Pilih wallet
        raw_wallet = args.wallet
        if raw_wallet == '-1':
            # Interactive — no CLI override
            if len(eligible_wallets) == 1 and first_pass:
                wallet_index = 0
                console.print(f'\n[green]→ Auto-selected wallet 0: {eligible_wallets[0]["address"][:10]}...[/green]')
            else:
                options = ' / '.join(str(i) for i in range(len(eligible_wallets)))
                if len(eligible_wallets) > 1:
                    options += " / 'all' untuk batch"
                try:
                    ans = input(f'\nSelect wallet [{options}] > ').strip().lower()
                    if ans == 'all':
                        wallet_index = 'all'
                    else:
                        wallet_index = int(ans)
                except (ValueError, EOFError, KeyboardInterrupt):
                    if first_pass:
                        wallet_index = 0
                    else:
                        break
        elif raw_wallet == 'all':
            wallet_index = 'all'
        else:
            try:
                wallet_index = int(raw_wallet)
            except ValueError:
                console.print(f'[red]Invalid --wallet value: {raw_wallet}[/red]')
                break

        if wallet_index == 'all':
            # Batch — semua wallet pake tier + quantity yang sama
            # Pilih tier dari wallet pertama
            if not eligible_wallets:
                break
            first_wallet = eligible_wallets[0]
            selected_tier = select_tier_interactive(first_wallet['eligible_tiers'], currency)
            quantity = prompt_quantity(selected_tier)
            gas_params = show_gas_menu(w3, chain)

            console.print(f'\n[bold]═══ Batch mint: {len(eligible_wallets)} wallets ═══[/bold]')

            for w in eligible_wallets:
                # Cari tier yg sama di wallet ini
                match = [t for t in w['eligible_tiers'] if t['name'] == selected_tier['name']]
                if not match:
                    console.print(f'  [dim]{w["address"][:10]}... — no {selected_tier["name"]} eligible, skip[/dim]')
                    continue
                tier_for_wallet = match[0]
                do_mint(contract, chain, tier_for_wallet, custom_rpc, quantity, w, dry_run, currency, gas_params)

            break

        elif 0 <= wallet_index < len(eligible_wallets):
            wallet_info = eligible_wallets[wallet_index]
            addr_short = f'{wallet_info["address"][:10]}...{wallet_info["address"][-6:]}'
            console.print(f'\n[bold]→ Wallet {wallet_index}:[/bold] [cyan]{addr_short}[/cyan]')

            # Cek eligibility detail + estimate
            show_eligibility(wallet_info['eligibility'], wallet_info['address'],
                           wallet_info['balance_eth'], currency)

            if not wallet_info['eligible_tiers']:
                console.print('[red]✕ No eligible tier[/red]')
                if not first_pass:
                    break
                continue

            # Pilih tier
            selected_tier = select_tier_interactive(wallet_info['eligible_tiers'], currency)

            # Quantity
            quantity = prompt_quantity(selected_tier)

            # Cost estimate
            console.print('\n[bold]💰 Estimating cost...[/bold]')
            est = estimate_total_cost(contract, chain, wallet_info['address'], selected_tier, custom_rpc, quantity)
            show_cost_estimate(est, currency)

            if dry_run:
                console.print('\n[yellow]── Dry-run mode — exiting ──[/yellow]')
                sys.exit(0)

            if est.get('error'):
                console.print(f'[yellow]⚠ Gas estimate failed: {est["error"]}[/yellow]')
                console.print('[yellow]  Proceeding anyway — user bear risk of failed tx[/yellow]')
            elif est['total_wei'] > wallet_info['balance_wei']:
                console.print(f'\n[red]✕ Insufficient balance! Need {est["total_eth"]:.6f} {currency}[/red]')
                break
            else:
                console.print(f'\n[green]✅ Balance sufficient ({wallet_info["balance_eth"]:.6f} >= {est["total_eth"]:.6f})[/green]')

            # Gas selection
            gas_params = show_gas_menu(w3, chain)

            # Execute
            mint_result = do_mint(contract, chain, selected_tier, custom_rpc, quantity, wallet_info, dry_run, currency, gas_params)
            if mint_result is None:
                # Cancelled during countdown
                break

        else:
            console.print('[red]Invalid selection[/red]')
            break

        # Tanya lanjut
        first_pass = False
        if wallet_index != 'all':
            others = [w for w in eligible_wallets
                     if w['address'] != eligible_wallets[wallet_index]['address'] and w['best_tier']]
            if others:
                ans = input('\nMint another wallet? [y/N] > ').strip().lower()
                if ans != 'y':
                    break
            else:
                break
        else:
            break

    show_batch_summary()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        console.print('\n\n[dim]Interrupted by user. Exiting.[/dim]')
        sys.exit(0)
