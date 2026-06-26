"""Chain config, env loader — RPC multichain dari .env."""

import os
from dotenv import load_dotenv

load_dotenv()

CHAINS = {
    'ethereum': {'id': 1, 'rpc': 'https://eth.drpc.org', 'currency': 'ETH', 'explorer': 'etherscan.io'},
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
    return os.getenv('OPENSEA_API_KEY', '')

def get_private_key() -> str:
    pk = os.getenv('PRIVATE_KEY', '')
    if not pk.startswith('0x'):
        pk = '0x' + pk
    return pk

def resolve_chain(input_str: str) -> str | None:
    """'eth' → 'ethereum', 'matic' → 'polygon', dll."""
    key = input_str.strip().lower()
    return CHAIN_MAP.get(key)
