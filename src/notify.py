"""Notification backends: Telegram bot + Discord webhook."""

import os
import requests


def _telegram(token: str, chat_id: str, text: str) -> bool:
    try:
        url = f'https://api.telegram.org/bot{token}/sendMessage'
        resp = requests.post(url, json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
                             timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def _discord(webhook_url: str, content: str) -> bool:
    try:
        resp = requests.post(webhook_url, json={'content': content}, timeout=10)
        return resp.status_code in (200, 204)
    except Exception:
        return False


def notify(message: str) -> None:
    """Send message to all configured backends. Silently skip if not configured."""
    tg_token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    tg_chat = os.getenv('TELEGRAM_CHAT_ID', '').strip()
    discord_url = os.getenv('DISCORD_WEBHOOK_URL', '').strip()

    if tg_token and tg_chat:
        _telegram(tg_token, tg_chat, message)

    if discord_url:
        _discord(discord_url, message)


def notify_mint_result(report: dict, chain: str, tier_name: str, wallet: str) -> None:
    """Format and send mint result notification."""
    status = report.get('status', 'unknown')
    addr = f'{wallet[:10]}...{wallet[-6:]}'

    explorers = {
        'ethereum': 'etherscan.io',
        'base': 'basescan.org',
        'optimism': 'optimistic.etherscan.io',
        'arbitrum': 'arbiscan.io',
        'polygon': 'polygonscan.com',
        'bsc': 'bscscan.com',
    }
    exp = explorers.get(chain, 'etherscan.io')
    tx = report.get('tx_hash', '')
    tx_url = f'https://{exp}/tx/{tx}' if tx else ''
    tx_short = f'{tx[:18]}...' if tx else '—'

    if status == 'success':
        msg = (
            f'✅ <b>MINT SUCCESS</b>\n'
            f'Wallet: <code>{addr}</code>\n'
            f'Tier: {tier_name}\n'
            f'Total: {report.get("total_cost_eth", 0):.6f} ETH\n'
            f'Tx: <a href="{tx_url}">{tx_short}</a>'
        )
    elif status == 'failed':
        msg = (
            f'❌ <b>MINT FAILED</b>\n'
            f'Wallet: <code>{addr}</code>\n'
            f'Tier: {tier_name}\n'
            f'Error: {report.get("message", "reverted")}\n'
            f'Tx: {tx_short}'
        )
    elif status == 'pending':
        msg = (
            f'⏳ <b>TX PENDING</b>\n'
            f'Wallet: <code>{addr}</code>\n'
            f'Tx: <a href="{tx_url}">{tx_short}</a>\n'
            f'Check explorer for status.'
        )
    else:
        return

    notify(msg)
