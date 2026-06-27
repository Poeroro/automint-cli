"""Chain config, env loader, RPC multichain dengan fallback otomatis."""

import os
import time


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
    'ethereum': {'id': 1,     'rpc': 'https://ethereum.publicnode.com',      'currency': 'ETH',  'explorer': 'etherscan.io'},
    'base':     {'id': 8453,  'rpc': 'https://base-rpc.publicnode.com',       'currency': 'ETH',  'explorer': 'basescan.org'},
    'optimism': {'id': 10,    'rpc': 'https://mainnet.optimism.io',           'currency': 'ETH',  'explorer': 'optimistic.etherscan.io'},
    'arbitrum': {'id': 42161, 'rpc': 'https://arb1.arbitrum.io/rpc',          'currency': 'ETH',  'explorer': 'arbiscan.io'},
    'polygon':  {'id': 137,   'rpc': 'https://polygon-bor.publicnode.com',    'currency': 'MATIC','explorer': 'polygonscan.com'},
    'bsc':      {'id': 56,    'rpc': 'https://bsc-dataseed.binance.org',      'currency': 'BNB',  'explorer': 'bscscan.com'},
    'megaeth':  {'id': 4326,  'rpc': 'https://megaeth.drpc.org',              'currency': 'ETH',  'explorer': 'megaeth.blockscout.com'},
}

# Fallback RPC list per chain — tried in order if primary fails
RPC_FALLBACKS = {
    'megaeth': [
        'https://megaeth.drpc.org',
        'https://6342.rpc.thirdweb.com',
    ],
    'ethereum': [
        'https://ethereum.publicnode.com',
        'https://rpc.ankr.com/eth',
        'https://eth.llamarpc.com',
        'https://cloudflare-eth.com',
    ],
    'base': [
        'https://base-rpc.publicnode.com',
        'https://mainnet.base.org',
        'https://rpc.ankr.com/base',
        'https://base.llamarpc.com',
    ],
    'optimism': [
        'https://mainnet.optimism.io',
        'https://rpc.ankr.com/optimism',
        'https://optimism.llamarpc.com',
    ],
    'arbitrum': [
        'https://arb1.arbitrum.io/rpc',
        'https://rpc.ankr.com/arbitrum',
        'https://arbitrum.llamarpc.com',
    ],
    'polygon': [
        'https://polygon-bor.publicnode.com',
        'https://rpc.ankr.com/polygon',
        'https://polygon.llamarpc.com',
    ],
    'bsc': [
        'https://bsc-dataseed.binance.org',
        'https://bsc-dataseed1.defibit.io',
        'https://rpc.ankr.com/bsc',
    ],
}

CHAIN_MAP = {
    'ethereum': 'ethereum', 'eth': 'ethereum',
    'base': 'base',
    'optimism': 'optimism', 'op': 'optimism',
    'arbitrum': 'arbitrum', 'arb': 'arbitrum',
    'polygon': 'polygon',   'matic': 'polygon',
    'bsc': 'bsc',           'binance': 'bsc',
    'megaeth': 'megaeth',   'mega': 'megaeth',
}


def get_rpc(chain_name: str) -> str:
    """Ambil RPC: env override > public default."""
    short_key = {'ethereum': 'ETH', 'base': 'BASE', 'optimism': 'OP',
                 'arbitrum': 'ARB', 'polygon': 'POLYGON', 'bsc': 'BSC'}
    sk = short_key.get(chain_name, chain_name.upper())
    for key in [f'RPC_{sk}', f'RPC_{chain_name.upper()}']:
        val = os.getenv(key)
        if val:
            return val
    info = CHAINS.get(chain_name)
    return info['rpc'] if info else ''


def get_working_rpc(chain_name: str, custom_rpc: str = '') -> str:
    """Return first reachable RPC for chain. Tries custom → env → fallback list.

    Raises RuntimeError if none reachable.
    """
    from web3 import Web3

    candidates = []
    if custom_rpc:
        candidates.append(custom_rpc)

    env_rpc = get_rpc(chain_name)
    if env_rpc and env_rpc not in candidates:
        candidates.append(env_rpc)

    for fallback in RPC_FALLBACKS.get(chain_name, []):
        if fallback not in candidates:
            candidates.append(fallback)

    for rpc in candidates:
        try:
            w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={'timeout': 5}))
            if w3.is_connected():
                return rpc
        except Exception:
            continue

    raise RuntimeError(
        f'No reachable RPC for {chain_name}. '
        f'Tried {len(candidates)} endpoints. Set RPC_{chain_name.upper()} in .env.'
    )


def get_private_key() -> str:
    pk = os.getenv('PRIVATE_KEY', '')
    if not pk:
        return ''
    if not pk.startswith('0x'):
        pk = '0x' + pk
    return pk


def get_all_wallets() -> list:
    """Load semua wallet dari env. PRIVATE_KEYS=0x...,0x... atau PRIVATE_KEY=..."""
    from web3 import Account
    keys_str = os.getenv('PRIVATE_KEYS', '')
    if keys_str.strip():
        raw_keys = [k.strip() for k in keys_str.split(',') if k.strip()]
    else:
        pk = os.getenv('PRIVATE_KEY', '')
        raw_keys = [pk.strip()] if pk.strip() else []

    wallets = []
    for pk in raw_keys:
        if not pk.startswith('0x'):
            pk = '0x' + pk
        try:
            acct = Account.from_key(pk)
            wallets.append({'account': acct, 'address': acct.address, 'private_key': pk})
        except Exception:
            continue
    return wallets


def resolve_chain(input_str: str) -> str | None:
    return CHAIN_MAP.get(input_str.strip().lower())


def get_max_gas_wei() -> int | None:
    """Return MAX_GAS_GWEI from env as wei, or None if not set."""
    val = os.getenv('MAX_GAS_GWEI', '').strip()
    if not val:
        return None
    try:
        return int(float(val) * 1e9)
    except ValueError:
        return None
