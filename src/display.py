"""CLI display — tables, colors, formatting."""

import time
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from .config import CHAINS, rpc_retry

console = Console()


def _get_currency(chain, default='ETH'):
    """Ambil currency symbol dari chain."""
    return CHAINS.get(chain, {}).get('currency', default)


def show_banner():
    console.print(Panel.fit(
        '[bold green]✦ AutoMint CLI[/bold green]  —  NFT Minter Terminal',
        border_style='green', padding=(1, 2)
    ))


def show_detect_result(data: dict):
    """Tampilkan hasil detect: contract, chain, tiers."""
    if data.get('error'):
        console.print(f'[red]✕ {data["error"]}[/red]')
        return

    name = data.get('name', data.get('slug', ''))
    contract = data.get('contract', '')
    chain = data.get('chain', '?')
    chain_id = data.get('chainId', '')
    currency = _get_currency(chain)

    console.print(f'\n[bold]Collection:[/bold] {name}')
    console.print(f'[bold]Contract:[/bold]  [cyan]{contract}[/cyan]')
    console.print(f'[bold]Chain:[/bold]     {chain} (ID: {chain_id})')
    console.print()

    tiers = data.get('tiers', [])
    if not tiers:
        console.print('[yellow]No tiers detected[/yellow]')
        return

    table = Table(box=box.ROUNDED, header_style='bold')
    table.add_column('#', style='dim')
    table.add_column('Tier')
    table.add_column('Price', justify='right')
    table.add_column('Max', justify='right')
    table.add_column('Status')
    table.add_column('Starts In')

    now_ts = time.time()

    for i, t in enumerate(tiers, 1):
        price = f'{t["price"]} {currency}' if t['price'] > 0 else '[green]FREE[/green]'
        max_mint = t.get('maxMint', 0)
        max_str = str(max_mint) if max_mint else '[dim]—[/dim]'
        status_raw = t.get('status', '?')

        if status_raw == 'active':
            status = '[green]LIVE[/green]'
            starts_in = '[dim]—[/dim]'
        elif status_raw and status_raw.startswith('scheduled:'):
            status = '[yellow]SCHEDULED[/yellow]'
            ts = int(status_raw.split(':')[1])
            rem = max(0, int(ts - now_ts))
            h, rem = rem // 3600, rem % 3600
            m, s = rem // 60, rem % 60
            starts_in = f'{h:02d}:{m:02d}:{s:02d}'
        elif status_raw == 'unknown':
            status = '[dim]?[/dim]'
            starts_in = '[dim]—[/dim]'
        else:
            status = status_raw
            starts_in = '[dim]—[/dim]'

        table.add_row(str(i), t.get('name', '?'), price, max_str, status, starts_in)

    console.print(table)


def show_eligibility(tiers: list, wallet: str, balance: float, currency: str = 'ETH'):
    """Tampilkan eligibility tiap tier."""
    console.print(f'\n[bold]Wallet:[/bold] [cyan]{wallet[:10]}...{wallet[-6:]}[/cyan]')
    console.print(f'[bold]Balance:[/bold] {balance:.6f} {currency}')

    table = Table(box=box.ROUNDED, header_style='bold')
    table.add_column('#', style='dim')
    table.add_column('Tier')
    table.add_column('Price', justify='right')
    table.add_column('Max', justify='right')
    table.add_column('Eligible')
    table.add_column('Reason')

    for i, t in enumerate(tiers, 1):
        price = f'{t["price"]} {currency}' if t['price'] > 0 else '[green]FREE[/green]'
        max_mint = t.get('maxMint', 0)
        max_str = str(max_mint) if max_mint else '[dim]—[/dim]'
        if t['eligible']:
            elig = '[green]✅ YES[/green]'
        else:
            elig = '[red]❌ NO[/red]'
        reason = t.get('reasons', ['—'])[0] if t.get('reasons') else '—'

        table.add_row(str(i), t['name'], price, max_str, elig, reason)

    console.print(table)


def show_cost_estimate(est: dict, currency: str = 'ETH'):
    """Tampilkan estimasi biaya."""
    if est.get('error'):
        console.print(f'[red]✕ Estimate: {est["error"]}[/red]')
        return

    console.print('\n[bold]Cost Estimate:[/bold]')
    console.print(f'  Mint Price:  [cyan]{est["price_eth"]:.6f} {currency}[/cyan]')
    console.print(f'  Gas Units:   {est["gas_units"]:,}')
    console.print(f'  Gas Price:   {est["gas_price_gwei"]:.2f} Gwei')
    console.print(f'  Gas Cost:    [yellow]{est["gas_cost_eth"]:.6f} {currency}[/yellow]')
    console.print(f'  [bold]Total:      [cyan]{est["total_eth"]:.6f} {currency}[/cyan][/bold]')


def show_wallets(wallets_info: list, currency: str = 'ETH'):
    """Tampilkan tabel wallet + balance + eligible tier."""
    table = Table(box=box.ROUNDED, header_style='bold')
    table.add_column('#', style='dim')
    table.add_column('Address')
    table.add_column('Balance', justify='right')
    table.add_column('Eligible Tier')

    for i, w in enumerate(wallets_info):
        addr = w['address']
        bal = w['balance_eth']
        best = w.get('best_tier')
        if best:
            tier_str = f'[green]{best["name"]}[/green]'
            if best['price'] > 0:
                tier_str += f' ({best["price"]} {currency})'
            else:
                tier_str += ' ([green]FREE[/green])'
        else:
            tier_str = '[dim]—[/dim]'
        table.add_row(str(i), f'[cyan]{addr[:10]}...{addr[-6:]}[/cyan]',
                      f'{bal:.6f} {currency}', tier_str)

    console.print(table)


def show_gas_menu(w3, chain='ethereum'):
    """Interaktif gas selection: Low/Med/High/Custom.
       Return gas_params dict: {type, max_fee, priority_fee} or {type, gas_price}."""

    block_times = {'ethereum': 12, 'base': 2, 'optimism': 2, 'arbitrum': 1, 'polygon': 2, 'bsc': 3}
    bt = block_times.get(chain, 12)

    # Detect EIP-1559 support
    is_eip1559 = False
    try:
        w3.eth.max_priority_fee
        is_eip1559 = True
    except Exception:
        pass

    if is_eip1559:
        try:
            fh = rpc_retry(lambda: w3.eth.fee_history(4, 'latest', [10, 50, 90]))
            base = fh['baseFeePerGas'][-1]
            rw = fh.get('reward', [])
            if rw and rw[-1]:
                lo = max(int(rw[-1][0]), 1_000_000_000)
                md = max(int(rw[-1][1]), 3_000_000_000)
                hi = max(int(rw[-1][2]), 10_000_000_000)
            else:
                lo, md, hi = 1_000_000_000, 3_000_000_000, 10_000_000_000
        except Exception:
            lo, md, hi = 1_000_000_000, 3_000_000_000, 10_000_000_000
            try:
                base = int(w3.eth.gas_price * 0.7)
            except Exception:
                base = lo * 10

        opts = [
            ('🐢 Low',    lo, f'~{bt * 3}s'),
            ('🚶 Medium', md, f'~{bt}s'),
            ('🚀 High',   hi, f'~{max(1, bt // 2)}s'),
        ]

        console.print('\n[bold]🔥 Gas Price Selection[/bold]')
        t = Table(box=box.ROUNDED, header_style='bold')
        t.add_column('#', style='dim')
        t.add_column('Option')
        t.add_column('Priority', justify='right')
        t.add_column('Max Fee', justify='right')
        t.add_column('Est. Time', justify='right')
        for i, (lbl, prio, est) in enumerate(opts):
            t.add_row(str(i), lbl, f'{prio/1e9:.1f} Gwei', f'{(base + prio)/1e9:.1f} Gwei', est)
        t.add_row('3', '⚙️ Custom', '[dim]manual[/dim]', '[dim]manual[/dim]', '[dim]—[/dim]')
        console.print(t)

        try:
            ch = int((input('\nSelect gas [0-3, default=1] > ').strip() or '1'))
        except (ValueError, EOFError, KeyboardInterrupt):
            ch = 1

        if ch == 3:
            try:
                pi = input(f'Priority fee (Gwei) [{md/1e9:.1f}] > ').strip()
                mi = input(f'Max fee (Gwei) [{(base + md)/1e9:.1f}] > ').strip()
                pf = int(float(pi) * 1e9) if pi else md
                mf = int(float(mi) * 1e9) if mi else (base + md)
            except Exception:
                pf, mf = md, base + md
        elif 0 <= ch < len(opts):
            _, pf, _ = opts[ch]
            mf = base + pf
        else:
            pf, mf = md, base + md

        return {'type': 'eip1559', 'max_fee': mf, 'priority_fee': pf}

    # Legacy
    try:
        gp = w3.eth.gas_price
    except Exception:
        gp = 10_000_000_000
    opts = [
        ('🐢 Low', int(gp * 0.9), f'~{bt * 5}s'),
        ('🚶 Medium', gp, f'~{bt * 2}s'),
        ('🚀 High', int(gp * 1.5), f'~{bt}s'),
    ]

    console.print('\n[bold]🔥 Gas Price Selection[/bold]')
    t = Table(box=box.ROUNDED, header_style='bold')
    t.add_column('#', style='dim')
    t.add_column('Option')
    t.add_column('Gas Price', justify='right')
    t.add_column('Est. Time', justify='right')
    for i, (lbl, pr, est) in enumerate(opts):
        t.add_row(str(i), lbl, f'{pr/1e9:.1f} Gwei', est)
    t.add_row('3', '⚙️ Custom', '[dim]manual[/dim]', '[dim]—[/dim]')
    console.print(t)

    try:
        ch = int((input('\nSelect gas [0-3, default=1] > ').strip() or '1'))
    except (ValueError, EOFError, KeyboardInterrupt):
        ch = 1

    if ch == 3:
        try:
            gi = input(f'Gas price (Gwei) [{gp/1e9:.1f}] > ').strip()
            gp_out = int(float(gi) * 1e9) if gi else gp
        except (ValueError, EOFError):
            gp_out = gp
    elif 0 <= ch < len(opts):
        _, gp_out, _ = opts[ch]
    else:
        gp_out = gp

    return {'type': 'legacy', 'gas_price': gp_out}


def show_report(report: dict, chain: str = ''):
    """Tampilkan laporan hasil mint."""
    status = report.get('status', 'unknown')
    currency = _get_currency(chain)
    exp = CHAINS.get(chain, {}).get('explorer', 'etherscan.io')

    if status == 'success':
        tx = report.get('tx_hash', '')
        tx_short = f'{tx[:18]}...{tx[-6:]}' if tx else '?'
        console.print(Panel.fit(
            '[bold green]✅ MINT SUCCESS[/bold green]\n\n'
            f'[bold]Tx:[/bold]     [link=https://{exp}/tx/{tx}]{tx_short}[/link]\n'
            f'[bold]Block:[/bold]  {report.get("block", 0):,}\n'
            f'[bold]Gas:[/bold]    {report.get("gas_used", 0):,} units @ {report.get("gas_price_gwei", 0):.2f} Gwei\n'
            f'[bold]Gas Fee:[/bold] {report.get("gas_cost_eth", 0):.6f} {currency}\n'
            f'[bold]Total:[/bold]  [cyan]{report.get("total_cost_eth", 0):.6f} {currency}[/cyan]',
            border_style='green', padding=(1, 2)
        ))
        console.print(f'   [dim]Explorer: https://{exp}/tx/{tx}[/dim]')

    elif status == 'failed':
        tx = report.get('tx_hash', '') or '?'
        tx_short = f'{tx[:18]}...' if tx != '?' else '?'
        console.print(Panel.fit(
            '[bold red]❌ MINT FAILED[/bold red]\n\n'
            f'Tx: {tx_short}\n'
            f'Error: {report.get("message", "unknown")}',
            border_style='red', padding=(1, 2)
        ))

    elif status == 'pending':
        tx = report.get('tx_hash', '') or '?'
        tx_short = f'{tx[:18]}...' if tx != '?' else '?'
        console.print(f'[yellow]⏳ Tx sent: {tx_short} — waiting for receipt[/yellow]')

    else:
        console.print(f'[red]✕ {report.get("message", "Unknown error")}[/red]')