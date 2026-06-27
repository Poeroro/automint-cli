#!/usr/bin/env python3

"""AutoMint CLI — NFT Minter Terminal.

Usage:
  automint                                    # interactive
  automint --url https://...
  automint --contract 0x... --chain eth [--rpc ...] [--dry-run]
  automint --url https://... --watch          # watch until live then mint
  automint --url https://... --watch --watch-interval 30

Flow: input → detect → load wallets → eligibility → tier → execute
"""

import sys
import os
import glob
import time
import argparse
import json
from dotenv import load_dotenv

load_dotenv()

from src.detect import detect, CACHE_DIR
from src.eligibility import check_eligibility, estimate_total_cost
from src.executor import execute_mint, wait_for_countdown, _get_current_gas_wei
from src.merkle import fetch_merkle_proof
from src.notify import notify_mint_result, notify
from src.display import (
    show_banner, show_detect_result, show_eligibility,
    show_cost_estimate, show_report, show_wallets, show_gas_menu, console
)
from src.config import resolve_chain, get_working_rpc, CHAINS, get_all_wallets, get_max_gas_wei
from web3 import Web3


LOG_FILE = 'automint.log'
BATCH_RESULTS = []


def check_env_file():
    env_path = '.env'
    if not os.path.exists(env_path):
        # If key already in environment (e.g. set directly), no need for .env
        if os.getenv('PRIVATE_KEY') or os.getenv('PRIVATE_KEYS'):
            return
        console.print('[yellow]⚠ .env file not found![/yellow]')
        console.print('  Copy [cyan].env.example[/cyan] → [cyan].env[/cyan] dan isi PRIVATE_KEY.')
        console.print()
        try:
            ans = input('Continue without .env? [y/N] > ').strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.exit(1)
        if ans != 'y':
            sys.exit(1)
        return
    if os.name == 'posix':
        mode = os.stat(env_path).st_mode & 0o777
        if mode > 0o600:
            console.print(f'[red]⚠ .env permission {oct(mode)} — too open! Run: chmod 600 .env[/red]')
            try:
                ans = input('Continue anyway? [y/N] > ').strip().lower()
            except (EOFError, KeyboardInterrupt):
                ans = 'n'
            if ans != 'y':
                sys.exit(1)


def append_log(entry: dict):
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
  automint                               → interaktif
  automint --url https://opensea.io/collection/...
  automint --contract 0x... --chain eth --dry-run
  automint --url https://... --watch
  automint --url https://... --watch --watch-interval 30
        """
    )
    p.add_argument('--url', help='OpenSea collection URL')
    p.add_argument('--contract', help='NFT contract address (0x...)')
    p.add_argument('--chain', default='', help='Chain: eth/base/op/arb/polygon/bsc')
    p.add_argument('--rpc', default='', help='Custom RPC URL')
    p.add_argument('--dry-run', action='store_true', help='Detect + estimate only, no tx')
    p.add_argument('--wallet', default='-1', help='Wallet index or "all" for batch')
    p.add_argument('--watch', action='store_true',
                   help='Watch mode: poll contract until a tier goes live, then auto-mint')
    p.add_argument('--watch-interval', type=int, default=15, metavar='SEC',
                   help='Seconds between polls in watch mode (default: 15)')
    return p.parse_args()


def prompt_input(args):
    url_or_contract = args.url or args.contract
    if url_or_contract:
        return url_or_contract, args.chain, args.rpc, args.dry_run

    console.print()
    console.print('[bold]Target NFT[/bold]')
    console.print('  Paste [cyan]OpenSea URL[/cyan] atau [cyan]contract address[/cyan] (0x...)')
    val = input('> ').strip()
    while not val:
        val = input('> ').strip()

    return val, args.chain, args.rpc, args.dry_run


def select_tier_interactive(eligible_tiers, currency):
    if len(eligible_tiers) == 1:
        selected = eligible_tiers[0]
        console.print(f'\n[green]→ Auto-selected: {selected["name"]}[/green]')
        return selected

    console.print('\n[bold]Select tier:[/bold]')
    for i, t in enumerate(eligible_tiers, 1):
        price = f'{t["price"]} {currency}' if t['price'] > 0 else 'FREE'
        merkle_note = ' [dim](merkle)[/dim]' if t.get('requiresMerkle') else ''
        console.print(f'  [cyan]{i}.[/cyan] {t["name"]} ({price}){merkle_note}')
    try:
        choice = int(input('\n> ').strip())
        return eligible_tiers[choice - 1]
    except (ValueError, IndexError):
        console.print('[red]Invalid choice[/red]')
        sys.exit(1)


def prompt_quantity(tier):
    max_mint = tier.get('maxMint', 0)
    if max_mint <= 1:
        return 1
    # Only ask quantity if max_mint is small (≤20); for large supplies default to 1
    if max_mint > 20:
        console.print(f'\n[dim]Max per wallet: {max_mint} — minting 1 (use --quantity to override)[/dim]')
        return 1
    console.print(f'\n[bold]Quantity:[/bold] Max per tx = [cyan]{max_mint}[/cyan]')
    try:
        ans = input(f'How many? [1-{max_mint}, enter=1] > ').strip()
        if ans:
            q = int(ans)
            if q < 1 or q > max_mint:
                console.print(f'[red]Must be 1-{max_mint}[/red]')
                sys.exit(1)
            if q > 1:
                console.print(f'[green]→ Minting {q} NFTs[/green]')
            return q
    except (ValueError, EOFError, KeyboardInterrupt):
        pass
    return 1


def do_mint(contract, chain, tier, custom_rpc, quantity, wallet_info, dry_run,
            currency, gas_params=None, merkle_proof=None):
    """Execute mint for one wallet. Handle countdown + gas bump."""
    status = tier.get('status', 'unknown')

    if status and status.startswith('scheduled:'):
        ts = int(status.split(':')[1])
        console.print(
            f'\n[bold]⏳ Countdown:[/bold] {tier["name"]} opens at '
            f'{time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts))}'
        )
        console.print('[dim]Auto-mint at countdown end...[/dim]')
        if not wait_for_countdown(ts, tier['name']):
            return None
    else:
        console.print(f'\n[green]{tier["name"]} is LIVE — auto-minting...[/green]')

    qty_note = f' × {quantity}' if quantity > 1 else ''
    addr_short = f'{wallet_info["address"][:10]}...{wallet_info["address"][-6:]}'
    console.print(f'\n[bold]🚀 {addr_short} →[/bold] {tier["name"]} @ {currency} {tier["price"]}{qty_note}')

    if dry_run:
        console.print('[yellow]── Dry-run — no transaction sent ──[/yellow]')
        return {'status': 'dry_run'}

    report = execute_mint(contract, chain, tier, custom_rpc, quantity,
                          wallet_info['private_key'], gas_params, merkle_proof)

    show_report(report, chain)
    notify_mint_result(report, chain, tier['name'], wallet_info['address'])

    append_log({
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
        'wallet': wallet_info['address'],
        'chain': chain,
        'contract': contract,
        'tier': tier['name'],
        'price': tier.get('price', 0),
        'quantity': quantity,
        'status': report['status'],
        'tx_hash': report.get('tx_hash', ''),
    })

    BATCH_RESULTS.append({
        'wallet': wallet_info['address'],
        'tier': tier['name'],
        'quantity': quantity,
        'status': report['status'],
        'tx_hash': report.get('tx_hash', ''),
    })

    return report


def show_batch_summary():
    if not BATCH_RESULTS:
        return
    success = [r for r in BATCH_RESULTS if r['status'] == 'success']
    failed = [r for r in BATCH_RESULTS if r['status'] not in ('success', 'dry_run')]
    total_nft = sum(r['quantity'] for r in success)

    console.print('\n' + '═' * 50)
    console.print('[bold]📊 Batch Summary[/bold]')
    console.print(f'  ✅ {len(success)} success ({total_nft} NFT minted)')
    if failed:
        console.print(f'  ❌ {len(failed)} failed')
        for r in failed:
            tx = r.get('tx_hash', '?')
            console.print(f'     {r["wallet"][:10]}... — {r["status"]}: {tx[:18] if tx else "?"}')
    console.print('═' * 50)


def run_watch_mode(input_str, chain_hint, custom_rpc, args):
    """Poll contract every N seconds. When a tier goes live, proceed to mint."""
    interval = args.watch_interval
    console.print(
        f'\n[bold]👁  Watch mode[/bold] — polling every [cyan]{interval}s[/cyan]. '
        f'[dim]Ctrl+C to stop.[/dim]'
    )

    poll = 0
    while True:
        poll += 1
        try:
            # Bust cache so every poll queries chain fresh
            for f in glob.glob(os.path.join(CACHE_DIR, '*.json')):
                try:
                    os.remove(f)
                except OSError:
                    pass
            result = detect(input_str, chain_hint, custom_rpc)
        except Exception as e:
            console.print(f'[yellow]⚠ Poll #{poll} detect error: {e}[/yellow]')
            time.sleep(interval)
            continue

        if result.get('error'):
            console.print(f'[yellow]⚠ Poll #{poll}: {result["error"]}[/yellow]')
            time.sleep(interval)
            continue

        contract = result['contract']
        chain = result['chain']
        tiers = result.get('tiers', [])
        currency = CHAINS.get(chain, {}).get('currency', 'ETH')

        # Find any active tier
        active = [t for t in tiers if t.get('status') == 'active']
        scheduled = [t for t in tiers if str(t.get('status', '')).startswith('scheduled:')]

        if active:
            console.print(f'\n[green bold]🔔 Poll #{poll}: tier LIVE — {[t["name"] for t in active]}[/green bold]')
            notify(f'🔔 AutoMint: {result.get("name", contract)} tier(s) {[t["name"] for t in active]} are LIVE!')

            # Check gas guard before proceeding
            max_gas_wei = get_max_gas_wei()
            if max_gas_wei:
                try:
                    rpc = get_working_rpc(chain, custom_rpc)
                    w3 = Web3(Web3.HTTPProvider(rpc))
                    current_gas = _get_current_gas_wei(w3)
                    if current_gas > max_gas_wei:
                        console.print(
                            f'[yellow]⚠ Gas {current_gas/1e9:.1f} Gwei > MAX_GAS_GWEI={max_gas_wei/1e9:.1f}. '
                            f'Waiting for gas to drop...[/yellow]'
                        )
                        time.sleep(interval)
                        continue
                except Exception:
                    pass

            return result  # Hand off to normal mint flow

        next_info = ''
        if scheduled:
            soonest = min(int(t['status'].split(':')[1]) for t in scheduled)
            rem = max(0, soonest - int(time.time()))
            h, r = divmod(rem, 3600)
            m, s = divmod(r, 60)
            next_info = f' | next: {h:02d}:{m:02d}:{s:02d}'

        console.print(
            f'[dim]Poll #{poll} — no active tier{next_info}. '
            f'Next check in {interval}s...[/dim]',
            end='\r'
        )
        time.sleep(interval)


def main():
    args = parse_args()
    check_env_file()
    show_banner()

    input_str, chain_hint_raw, custom_rpc, dry_run = prompt_input(args)

    chain_hint = resolve_chain(chain_hint_raw)
    if chain_hint_raw and not chain_hint:
        console.print(f'[yellow]⚠ Unknown chain "{chain_hint_raw}" — defaulting to ethereum[/yellow]')
    if not chain_hint:
        chain_hint = 'ethereum'

    # ── Watch mode ──
    if args.watch:
        try:
            result = run_watch_mode(input_str, chain_hint, custom_rpc, args)
        except KeyboardInterrupt:
            console.print('\n[dim]Watch mode stopped.[/dim]')
            sys.exit(0)
        except Exception as e:
            console.print(f'[red]✕ Watch mode error: {e}[/red]')
            sys.exit(1)
    else:
        # ── Normal detect ──
        console.print(f'\n[bold]🔍 Detecting:[/bold] {input_str[:60]}...')
        result = detect(input_str, chain_hint, custom_rpc)

        if result.get('error'):
            console.print(f'[red]✕ {result["error"]}[/red]')
            sys.exit(1)

    show_detect_result(result)

    contract = result['contract']
    chain = result['chain']
    tiers = result['tiers']
    currency = CHAINS.get(chain, {}).get('currency', 'ETH')

    if not tiers:
        console.print('[yellow]No tiers detected. Cannot proceed.[/yellow]')
        sys.exit(1)

    # ── RPC with fallback ──
    try:
        rpc = get_working_rpc(chain, custom_rpc)
    except RuntimeError as e:
        console.print(f'[red]✕ {e}[/red]')
        sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(rpc))

    # Chain ID check only when custom RPC provided
    if custom_rpc:
        expected_id = CHAINS.get(chain, {}).get('id')
        try:
            actual_id = w3.eth.chain_id
            if expected_id and actual_id != expected_id:
                console.print(f'[red]✕ Chain mismatch! RPC chainId={actual_id}, expected {chain}(id={expected_id})[/red]')
                if input('Force continue? [y/N] > ').strip().lower() != 'y':
                    sys.exit(1)
        except Exception:
            pass

    # ── Load wallets ──
    all_wallets = get_all_wallets()
    if not all_wallets:
        console.print('[red]✕ No wallets found. Set PRIVATE_KEY or PRIVATE_KEYS in .env[/red]')
        sys.exit(1)

    console.print(f'\n[bold]👛 Wallets loaded:[/bold] {len(all_wallets)}')

    # ── Eligibility per wallet (with Merkle proofs) ──
    merkle_proofs_by_wallet = {}
    wallets_info = []

    for w in all_wallets:
        address = w['address']
        balance_wei = w3.eth.get_balance(address)
        balance_eth = balance_wei / 1e18

        merkle_proofs = {}
        for tier in tiers:
            if tier.get('requiresMerkle'):
                proof = fetch_merkle_proof(contract, address)
                if proof:
                    merkle_proofs[tier['name']] = proof

        merkle_proofs_by_wallet[address] = merkle_proofs

        elig = check_eligibility(contract, chain, address, tiers, custom_rpc, merkle_proofs)
        eligible_tiers = [t for t in elig if t['eligible']]

        wallets_info.append({
            **w,
            'balance_wei': balance_wei,
            'balance_eth': balance_eth,
            'eligibility': elig,
            'eligible_tiers': eligible_tiers,
            'best_tier': eligible_tiers[0] if eligible_tiers else None,
        })

    # ── Show eligibility ──
    eligible_wallets = [w for w in wallets_info if w['best_tier']]
    if not eligible_wallets:
        # Give a specific message if tiers exist but balance is the only issue
        _all_elig = [e for w in wallets_info for e in w.get('eligibility', [])]
        _insuf = [e for e in _all_elig if any('insufficient' in r for r in e.get('reasons', []))]
        if _insuf:
            e = _insuf[0]
            console.print(
                f'[red]✕ Wallet balance insufficient.[/red] '
                f'Need [cyan]{e["price"]} {currency}[/cyan], '
                f'have [yellow]{e["balance"]:.6f} {currency}[/yellow]. '
                f'Top up wallet and try again.'
            )
        else:
            console.print('[red]✕ No wallet eligible for any tier[/red]')
        show_batch_summary()
        return

    console.print('\n[bold]🔎 Eligibility Check[/bold]')
    show_wallets(eligible_wallets, currency)

    # Show gas guard status if set
    max_gas_wei = get_max_gas_wei()
    if max_gas_wei:
        current_gas = _get_current_gas_wei(w3)
        status_color = 'green' if current_gas <= max_gas_wei else 'red'
        console.print(
            f'\n[bold]⛽ Gas:[/bold] [{status_color}]{current_gas/1e9:.1f} Gwei[/{status_color}]'
            f' | limit: {max_gas_wei/1e9:.1f} Gwei'
        )

    # ── Resolve target wallets ──
    raw_wallet = args.wallet
    if raw_wallet == 'all':
        target_wallets = eligible_wallets
    elif raw_wallet != '-1':
        try:
            idx = int(raw_wallet)
            target_wallets = [eligible_wallets[idx]]
        except (ValueError, IndexError):
            console.print(f'[red]Invalid --wallet value: {raw_wallet}[/red]')
            return
    else:
        # Interactive: auto-select if only one wallet, else ask
        if len(eligible_wallets) == 1:
            target_wallets = eligible_wallets
            console.print(f'\n[green]→ Auto-selected wallet 0: {eligible_wallets[0]["address"][:10]}...[/green]')
        else:
            options = ' / '.join(str(i) for i in range(len(eligible_wallets))) + " / 'all'"
            try:
                ans = input(f'\nSelect wallet [{options}] > ').strip().lower()
                if ans == 'all':
                    target_wallets = eligible_wallets
                else:
                    idx = int(ans)
                    target_wallets = [eligible_wallets[idx]]
            except (ValueError, IndexError, EOFError, KeyboardInterrupt):
                target_wallets = [eligible_wallets[0]]

    # ── Select tier (once, shared across all target wallets) ──
    first_wallet = target_wallets[0]
    show_eligibility(first_wallet['eligibility'], first_wallet['address'],
                     first_wallet['balance_eth'], currency)

    selected_tier = select_tier_interactive(first_wallet['eligible_tiers'], currency)
    quantity = prompt_quantity(selected_tier)

    # ── Gas selection ──
    # For scheduled tiers: select gas NOW so user can walk away and mint fires automatically
    is_scheduled = selected_tier.get('status', '').startswith('scheduled:')
    if is_scheduled:
        ts = int(selected_tier['status'].split(':')[1])
        console.print(
            f'\n[yellow]⏳ Tier is scheduled — select gas now, '
            f'CLI will auto-mint at {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts))}[/yellow]'
        )
    gas_params = show_gas_menu(w3, chain)

    # ── Cost estimate (skip for scheduled — gas price will change by then) ──
    if not is_scheduled:
        console.print('\n[bold]💰 Estimating cost...[/bold]')
        proof_for_est = merkle_proofs_by_wallet.get(first_wallet['address'], {}).get(selected_tier['name'])
        est = estimate_total_cost(contract, chain, first_wallet['address'], selected_tier,
                                  custom_rpc, quantity, proof_for_est)
        show_cost_estimate(est, currency)

        if est.get('error'):
            console.print(f'[yellow]⚠ Gas estimate failed: {est["error"]}[/yellow]')
            console.print('[yellow]  Proceeding — user bears risk[/yellow]')
        elif est['total_wei'] > first_wallet['balance_wei']:
            console.print(f'\n[red]✕ Insufficient balance! Need {est["total_eth"]:.6f} {currency}[/red]')
            show_batch_summary()
            return
        else:
            console.print(
                f'\n[green]✅ Balance sufficient '
                f'({first_wallet["balance_eth"]:.6f} >= {est["total_eth"]:.6f})[/green]'
            )

    # ── Execute for each target wallet ──
    if len(target_wallets) > 1:
        console.print(f'\n[bold]═══ Batch mint: {len(target_wallets)} wallets ═══[/bold]')

    for w in target_wallets:
        match = [t for t in w['eligible_tiers'] if t['name'] == selected_tier['name']]
        if not match:
            console.print(f'  [dim]{w["address"][:10]}... — tier {selected_tier["name"]} not eligible, skip[/dim]')
            continue
        tier_for_wallet = match[0]
        proof = merkle_proofs_by_wallet.get(w['address'], {}).get(selected_tier['name'])
        mint_result = do_mint(contract, chain, tier_for_wallet, custom_rpc, quantity,
                              w, dry_run, currency, gas_params, proof)
        if mint_result is None:
            # User cancelled countdown
            break

    show_batch_summary()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        console.print('\n\n[dim]Interrupted by user. Exiting.[/dim]')
        sys.exit(0)
