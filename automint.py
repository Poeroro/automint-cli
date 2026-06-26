#!/usr/bin/env python3

"""AutoMint CLI — NFT Minter Terminal.

Usage:
  automint                           # interactive — masukin URL/contract
  automint --url https://...         # langsung dari URL
  automint --contract 0x... --chain eth [--rpc ...] [--dry-run]

Flow: input → detect → eligibility → pilih tier → countdown → execute → report
"""

import sys, os, time, argparse, json
from dotenv import load_dotenv

load_dotenv()

from src.detect import detect
from src.eligibility import check_eligibility, estimate_total_cost
from src.executor import execute_mint, wait_for_countdown, get_wallet
from src.display import (
    show_banner, show_detect_result, show_eligibility,
    show_cost_estimate, show_report, console
)
from src.config import resolve_chain, get_rpc, get_opensea_api_key, CHAINS
from web3 import Web3


LOG_FILE = 'automint.log'


def check_env_file():
    """Cek .env exist + permission 600."""
    env_path = '.env'
    if not os.path.exists(env_path):
        console.print('[yellow]⚠ .env file not found![/yellow]')
        console.print('  Copy [cyan].env.example[/cyan] ke [cyan].env[/cyan] dan isi:')
        console.print('  [yellow]cp .env.example .env[/yellow]')
        console.print('  [yellow]nano .env[/yellow]')
        console.print()
        if input('Continue without .env? (hanya contract langsung tanpa OS API) [y/N] > ').strip().lower() != 'y':
            sys.exit(1)
        return
    mode = os.stat(env_path).st_mode & 0o777
    if mode > 0o600:
        console.print(f'[red]⚠ .env permission {oct(mode)} — too open! Run:[/red]')
        console.print(f'  [yellow]chmod 600 {env_path}[/yellow]')
        console.print()
        if input('Continue anyway? [y/N] > ').strip().lower() != 'y':
            sys.exit(1)


def verify_chain_id(w3: Web3, chain: str) -> bool:
    """Cek chainId RPC cocok dengan chain yg dipilih."""
    expected = CHAINS.get(chain, {}).get('id')
    if not expected:
        return True
    try:
        actual = w3.eth.chain_id
    except:
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
    except:
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


def main():
    check_env_file()

    # ── Wajib: OpenSea API Key ──
    if not get_opensea_api_key():
        console.print('[red]✕ OPENSEA_API_KEY not set in .env[/red]')
        console.print()
        console.print('  Daftar API key gratis di [link=https://opensea.io/account/api]https://opensea.io/account/api[/link]')
        console.print('  lalu tambahkan ke .env:')
        console.print('  [yellow]OPENSEA_API_KEY=your_key_here[/yellow]')
        console.print()
        console.print('  [dim]Atau gunakan --contract + --chain langsung (tanpa URL OpenSea)[/dim]')
        sys.exit(1)

    args = parse_args()
    show_banner()

    # ── Step 0: Input ──
    input_str, chain_hint_raw, custom_rpc, dry_run = prompt_input(args)

    chain_hint = resolve_chain(chain_hint_raw) or 'ethereum'
    if chain_hint_raw and not resolve_chain(chain_hint_raw):
        console.print(f'[yellow]⚠ Unknown chain "{chain_hint_raw}" — defaulting to ethereum[/yellow]')

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

    # ── Step 1.5: RPC + ChainId ──
    rpc = custom_rpc or get_rpc(chain)
    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        console.print(f'[red]✕ RPC not connected: {chain}[/red]')
        sys.exit(1)
    if custom_rpc:
        if not verify_chain_id(w3, chain):
            if input('Force continue? [y/N] > ').strip().lower() != 'y':
                sys.exit(1)

    # ── Step 2: Wallet ──
    acct, err = get_wallet(w3)
    if err:
        console.print(f'[red]✕ {err}[/red]')
        sys.exit(1)

    wallet = acct.address
    balance_wei = w3.eth.get_balance(wallet)
    balance_eth = balance_wei / 1e18

    console.print(f'\n[bold]👛 Wallet:[/bold] [cyan]{wallet[:10]}...{wallet[-6:]}[/cyan]')
    console.print(f'[bold]💰 Balance:[/bold] [cyan]{balance_eth:.6f} {currency}[/cyan]')

    # ── Step 3: Eligibility ──
    console.print('\n[bold]🔎 Checking eligibility...[/bold]')
    elig_results = check_eligibility(contract, chain, wallet, tiers, custom_rpc)
    show_eligibility(elig_results, wallet, balance_eth, currency)

    eligible_tiers = [t for t in elig_results if t['eligible']]
    if not eligible_tiers:
        console.print('[red]✕ Wallet not eligible for any tier[/red]')
        sys.exit(1)

    # ── Step 4: Pilih Tier ──
    selected = None
    if len(eligible_tiers) == 1:
        selected = eligible_tiers[0]
        console.print(f'\n[green]→ Auto-selected: {selected["name"]}[/green]')
    else:
        console.print('\n[bold]Select tier:[/bold]')
        for i, t in enumerate(eligible_tiers, 1):
            price = f'{t["price"]} {currency}' if t['price'] > 0 else 'FREE'
            console.print(f'  [cyan]{i}.[/cyan] {t["name"]} ({price})')
        try:
            choice = int(input('\n> ').strip())
            selected = eligible_tiers[choice - 1]
        except (ValueError, IndexError):
            console.print('[red]Invalid choice[/red]')
            sys.exit(1)

    # ── Step 5: Cost Estimate ──
    console.print('\n[bold]💰 Estimating cost...[/bold]')
    est = estimate_total_cost(contract, chain, wallet, selected, custom_rpc)
    show_cost_estimate(est, currency)

    if est.get('error'):
        sys.exit(1)

    if est['total_wei'] > balance_wei:
        console.print(f'\n[red]✕ Insufficient balance! Need {est["total_eth"]:.6f} {currency}, have {balance_eth:.6f} {currency}[/red]')
        sys.exit(1)
    else:
        console.print(f'\n[green]✅ Balance sufficient ({balance_eth:.6f} >= {est["total_eth"]:.6f})[/green]')

    if dry_run:
        console.print('\n[yellow]── Dry-run mode — exiting ──[/yellow]')
        sys.exit(0)

    # ── Step 6: Countdown ──
    tier_data = next((t for t in tiers if t['name'] == selected['name']), tiers[0])
    status = tier_data.get('status', 'unknown')

    if status and status.startswith('scheduled:'):
        ts = int(status.split(':')[1])
        console.print(f'\n[bold]⏳ Countdown:[/bold] {selected["name"]} opens at {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts))}')
        console.print('[yellow]Auto-mint when countdown ends?[/yellow]')
        try:
            ans = input('[y/N] > ').strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = 'n'

        if ans != 'y':
            console.print('[dim]Cancelled. Exiting.[/dim]')
            sys.exit(0)

        ok = wait_for_countdown(ts, selected['name'])
        if not ok:
            sys.exit(0)

    elif status == 'active' or not status:
        console.print(f'\n[green]Tier {selected["name"]} is LIVE![/green]')
        console.print('[yellow]Mint now?[/yellow]')
        try:
            ans = input('[y/N] > ').strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = 'n'
        if ans != 'y':
            console.print('[dim]Cancelled. Exiting.[/dim]')
            sys.exit(0)

    # ── Step 7: Execute ──
    console.print(f'\n[bold]🚀 Executing mint:[/bold] {selected["name"]} @ {currency} {selected["price"]}')
    report = execute_mint(contract, chain, tier_data, custom_rpc)

    # ── Step 8: Report ──
    show_report(report, chain)

    # ── Log ──
    log_entry = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
        'chain': chain,
        'contract': contract,
        'tier': selected['name'],
        'price': selected.get('price', 0),
        'status': report['status'],
        'tx_hash': report.get('tx_hash', ''),
    }
    append_log(log_entry)
    console.print(f'[dim]📝 Logged to {LOG_FILE}[/dim]')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        console.print('\n\n[dim]Interrupted by user. Exiting.[/dim]')
        sys.exit(0)
