"""CLI display — tables, colors, formatting."""

import time
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


def show_banner():
    console.print(Panel.fit(
        '[bold green]✦ AutoMint CLI[/bold green]  —  NFT Minter Terminal',
        border_style='green', padding=(1, 2)
    ))


def _get_currency(chain, default='ETH'):
    """Ambil currency symbol dari chain."""
    from .config import CHAINS
    return CHAINS.get(chain, {}).get('currency', default)


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
    table.add_column('Status')
    table.add_column('Starts In')

    now_ts = time.time()

    for i, t in enumerate(tiers, 1):
        price = f'{t["price"]} {currency}' if t['price'] > 0 else '[green]FREE[/green]'
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

        table.add_row(str(i), t.get('name', '?'), price, status, starts_in)

    console.print(table)


def show_eligibility(tiers: list, wallet: str, balance: float, currency: str = 'ETH'):
    """Tampilkan eligibility tiap tier."""
    console.print(f'\n[bold]Wallet:[/bold] [cyan]{wallet[:10]}...{wallet[-6:]}[/cyan]')
    console.print(f'[bold]Balance:[/bold] {balance:.6f} {currency}')

    table = Table(box=box.ROUNDED, header_style='bold')
    table.add_column('#', style='dim')
    table.add_column('Tier')
    table.add_column('Price', justify='right')
    table.add_column('Eligible')
    table.add_column('Reason')

    for i, t in enumerate(tiers, 1):
        price = f'{t["price"]} {currency}' if t['price'] > 0 else '[green]FREE[/green]'
        if t['eligible']:
            elig = '[green]✅ YES[/green]'
        else:
            elig = '[red]❌ NO[/red]'
        reason = t.get('reasons', ['—'])[0] if t.get('reasons') else '—'

        table.add_row(str(i), t['name'], price, elig, reason)

    console.print(table)


def show_cost_estimate(est: dict, currency: str = 'ETH'):
    """Tampilkan estimasi biaya."""
    if est.get('error'):
        console.print(f'[red]✕ Estimate: {est["error"]}[/red]')
        return

    console.print(f'\n[bold]Cost Estimate:[/bold]')
    console.print(f'  Mint Price:  [cyan]{est["price_eth"]:.6f} {currency}[/cyan]')
    console.print(f'  Gas Units:   {est["gas_units"]:,}')
    console.print(f'  Gas Price:   {est["gas_price_gwei"]:.2f} Gwei')
    console.print(f'  Gas Cost:    [yellow]{est["gas_cost_eth"]:.6f} {currency}[/yellow]')
    console.print(f'  [bold]Total:      [cyan]{est["total_eth"]:.6f} {currency}[/cyan][/bold]')


def show_report(report: dict, chain: str = ''):
    """Tampilkan laporan hasil mint."""
    status = report.get('status', 'unknown')
    currency = _get_currency(chain)

    if status == 'success':
        explorer = {'ethereum': 'etherscan.io', 'base': 'basescan.org',
                    'optimism': 'optimistic.etherscan.io', 'arbitrum': 'arbiscan.io',
                    'polygon': 'polygonscan.com', 'bsc': 'bscscan.com'}
        exp = explorer.get(chain, 'etherscan.io')

        console.print(Panel.fit(
            '[bold green]✅ MINT SUCCESS[/bold green]\n\n'
            f'[bold]Tx:[/bold]     [link=https://{exp}/tx/{report["tx_hash"]}]{report["tx_hash"][:18]}...{report["tx_hash"][-6:]}[/link]\n'
            f'[bold]Block:[/bold]  {report["block"]:,}\n'
            f'[bold]Gas:[/bold]    {report["gas_used"]:,} units @ {report["gas_price_gwei"]:.2f} Gwei\n'
            f'[bold]Gas Fee:[/bold] {report["gas_cost_eth"]:.6f} {currency}\n'
            f'[bold]Total:[/bold]  [cyan]{report["total_cost_eth"]:.6f} {currency}[/cyan]',
            border_style='green', padding=(1, 2)
        ))
        console.print(f'   [dim]Explorer: https://{exp}/tx/{report["tx_hash"]}[/dim]')

    elif status == 'failed':
        console.print(Panel.fit(
            '[bold red]❌ MINT FAILED[/bold red]\n\n'
            f'Tx: {report.get("tx_hash", "?")[:18]}...\n'
            f'Error: {report.get("message", "unknown")}',
            border_style='red', padding=(1, 2)
        ))

    elif status == 'pending':
        console.print(f'[yellow]⏳ Tx sent: {report["tx_hash"][:18]}... — waiting for receipt[/yellow]')

    else:
        console.print(f'[red]✕ {report.get("message", "Unknown error")}[/red]')
