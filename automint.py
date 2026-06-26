#!/usr/bin/env python3
"""AutoMint CLI — NFT Minter Terminal.

Usage:
  python automint.py --url https://opensea.io/collection/...
  python automint.py --contract 0x... --chain eth [--rpc https://...] [--dry-run]

Flow: detect → eligibility → pilih tier → countdown → execute → report
"""

import sys, os, time, argparse
from dotenv import load_dotenv

load_dotenv()

from src.detect import detect
from src.eligibility import check_eligibility, estimate_total_cost
from src.executor import execute_mint, wait_for_countdown, get_wallet
from src.display import (
    show_banner, show_detect_result, show_eligibility,
    show_cost_estimate, show_report, console
)
from src.config import resolve_chain, get_rpc, CHAINS


def parse_args():
    p = argparse.ArgumentParser(description='AutoMint CLI — NFT Minter Terminal')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--url', help='OpenSea collection URL')
    g.add_argument('--contract', help='NFT contract address (0x...)')
    p.add_argument('--chain', default='', help='Chain: eth/base/op/arb/polygon/bsc')
    p.add_argument('--rpc', default='', help='Custom RPC URL (override env/default)')
    p.add_argument('--wallet', type=int, default=0, help='Wallet index (multi-key dari env)')
    p.add_argument('--dry-run', action='store_true', help='Detect + estimate only, no mint')
    return p.parse_args()


def main():
    args = parse_args()
    show_banner()

    # ── Step 1: Detect ──
    input_str = args.url or args.contract
    chain_hint = resolve_chain(args.chain) or 'ethereum'
    custom_rpc = args.rpc

    console.print(f'\n[bold]🔍 Detecting:[/bold] {input_str[:60]}...')
    result = detect(input_str, chain_hint, custom_rpc)

    if result.get('error'):
        console.print(f'[red]✕ {result["error"]}[/red]')
        sys.exit(1)

    show_detect_result(result)

    contract = result['contract']
    chain = result['chain']
    tiers = result['tiers']

    if not tiers:
        console.print('[yellow]No tiers detected. Cannot proceed.[/yellow]')
        sys.exit(1)

    # ── Step 2: Wallet ──
    from web3 import Web3
    rpc = custom_rpc or get_rpc(chain)
    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        console.print(f'[red]✕ RPC not connected: {chain}[/red]')
        sys.exit(1)

    acct, err = get_wallet(w3)
    if err:
        console.print(f'[red]✕ {err}[/red]')
        sys.exit(1)

    wallet = acct.address
    balance_wei = w3.eth.get_balance(wallet)
    balance_eth = balance_wei / 1e18

    console.print(f'\n[bold]👛 Wallet:[/bold] [cyan]{wallet[:10]}...{wallet[-6:]}[/cyan]')
    console.print(f'[bold]💰 Balance:[/bold] [cyan]{balance_eth:.6f} {CHAINS.get(chain, {}).get("currency", "ETH")}[/cyan]')

    # ── Step 3: Eligibility ──
    console.print('\n[bold]🔎 Checking eligibility...[/bold]')
    elig_results = check_eligibility(contract, chain, wallet, tiers, custom_rpc)
    show_eligibility(elig_results, wallet, balance_eth)

    # Filter eligible
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
            price = f'{t["price"]} ETH' if t['price'] > 0 else 'FREE'
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
    show_cost_estimate(est)

    if est.get('error'):
        sys.exit(1)

    # Cek balance
    if est['total_wei'] > balance_wei:
        console.print(f'\n[red]✕ Insufficient balance! Need {est["total_eth"]:.6f}, have {balance_eth:.6f}[/red]')
        sys.exit(1)
    else:
        console.print(f'\n[green]✅ Balance sufficient ({balance_eth:.6f} >= {est["total_eth"]:.6f})[/green]')

    if args.dry_run:
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
    else:
        console.print(f'[yellow]Tier status: {status} — proceeding with caution[/yellow]')

    # ── Step 7: Execute ──
    console.print(f'\n[bold]🚀 Executing mint:[/bold] {selected["name"]} @ {CHAINS.get(chain, {}).get("currency", "ETH")} {selected["price"]}')
    report = execute_mint(contract, chain, tier_data, custom_rpc)

    # ── Step 8: Report ──
    show_report(report, chain)

    # Log
    log_entry = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
        'chain': chain,
        'contract': contract,
        'tier': selected['name'],
        'status': report['status'],
        'tx_hash': report.get('tx_hash', ''),
    }
    print(f'\n[dim]📝 Logged to automint.log[/dim]')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n\n[dim]Interrupted by user. Exiting.[/dim]')
        sys.exit(0)
