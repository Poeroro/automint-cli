"""Chain config, env loader — RPC multichain dari .env."""

import os, time


def rpc_retry(fn, max_attempts=3, delay=2):
    """Retry RPC call with exponential backoff."""
    last_err = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if attempt < max_attempts - 1:
                time.sleep(delay * (2 ** attempt))
    raise last_err


CHAINS = {
    'ethereum': {'id': 1, 'rpc': 'https://rpc.flashbots.net', 'currency': 'ETH', 'explorer': 'etherscan.io'},
    'base':     {'id': 8453, 'rpc': 'https://base-rpc.publicnode.com', 'currency': 'ETH', 'explorer': 'basescan.org'},
    'optimism': {'id': 10, 'rpc': 'https://mainnet.optimism.io', 'currency': 'ETH', 'explorer': 'optimistic.etherscan.io'},
    'arbitrum': {'id': 42161, 'rpc': 'https://arb1.arbitrum.io/rpc', 'currency': 'ETH', 'explorer': 'arbiscan.io'},
    'polygon':  {'id': 137, 'rpc': 'https://polygon-bor.publicnode.com', 'currency': 'MATIC', 'explorer': 'polygonscan.com'},
    'bsc':      {'id': 56, 'rpc': 'https://bsc-dataseed.binance.org', 'currency': 'BNB', 'explorer': 'bscscan.com'},
}

CHAIN_MAP = {
    'ethereum': 'ethereum', 'eth': 'ethereum',
    'base': 'base',
    'optimism': 'optimism', 'op': 'optimism',
    'arbitrum': 'arbitrum', 'arb': 'arbitrum',
    'polygon': 'polygon', 'matic': 'polygon',
    'bsc': 'bsc', 'binance': 'bsc',
}

def get_rpc(chain_name: str) -> str:
    """Ambil RPC: env > public default. Env key: RPC_CHAINNAME (uppercase)."""
    env_key = f'RPC_{chain_name.upper()}'
    custom = os.getenv(env_key)
    if custom:
        return custom
    info = CHAINS.get(chain_name)
    return info['rpc'] if info else ''

def get_opensea_api_key() -> str:
    """Ambil OS API key dari env. Wajib diisi."""
    return os.getenv('OPENSEA_API_KEY', '')

def get_private_key() -> str:
    pk = os.getenv('PRIVATE_KEY', '')
    if not pk.startswith('0x'):
        pk = '0x' + pk
    return pk

def get_all_wallets() -> list:
    """Load semua wallet dari env. Format: PRIVATE_KEYS=0x...,0x..., atau PRIVATE_KEY=..."""
    from web3 import Account
    keys_str = os.getenv('PRIVATE_KEYS', '')
    if keys_str.strip():
        raw_keys = [k.strip() for k in keys_str.split(',') if k.strip()]
    else:
        pk = os.getenv('PRIVATE_KEY', '')
        if pk.strip():
            raw_keys = [pk.strip()]
        else:
            return []
    wallets = []
    for pk in raw_keys:
        if not pk.startswith('0x'):
            pk = '0x' + pk
        try:
            acct = Account.from_key(pk)
            wallets.append({'account': acct, 'address': acct.address, 'private_key': pk})
        except:
            continue
    return wallets

def resolve_chain(input_str: str) -> str | None:
    """'eth' → 'ethereum', 'matic' → 'polygon', dll."""
    key = input_str.strip().lower()
    return CHAIN_MAP.get(key)
