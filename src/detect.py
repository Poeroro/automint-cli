"""Detect NFT collection info on-chain + scraped from OpenSea page.

detect() = main entry: URL → scrape + on-chain detect.
detect_onchain() = pure on-chain from contract + chain.
scrape_opensea_collection() = parse HTML from OS page via regex.
"""

import re
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

from web3 import Web3

from .config import get_rpc
from .config import resolve_chain as _resolve_chain


# ─── Tier detection: name + method sigs ───
# First selector in each set = preferred mint function
# We detect price separately via dedicated price selectors
TIER_METHODS = [
    ('Public',        ['0x1249c58b']),  # mint()
    ('OG',            ['0xa28c555d', '0x3b1ebc7e', '0x7a1ac6c1', '0xb3e126be']),
    ('Allowlist',     ['0x3af32abf', '0x5c1f0ecf', '0x415fc4b3', '0x67e0aceb', '0x3cd80455']),
    ('Whitelist',     ['0x3af32abf', '0x5c1f0ecf', '0x415fc4b3', '0x67e0aceb']),
    ('Presale',       ['0xc693f915', '0xf2c4bc48', '0x316894db', '0xc6690c0f']),
    ('VIP',           ['0x6aaf4481', '0x6403727b']),
    ('Freemint',      ['0xd18e81b3']),
    ('Early',         ['0x2f9166b8', '0x67e0aceb', '0xaba3c5f7']),
]

# Dedicated price selectors — these ACTUALLY return mint price
PRICE_SELECTORS = [
    '0xe7572239',  # cost()
    '0xef18e5e1',  # mintPrice()
    '0x3de39a5c',  # getMintCost()
]


# Global max supply selectors
GLOBAL_MAX_SELECTORS = [
    '0xeab04e34',  # totalSupply()
    '0x18160ddd',  # totalSupply() (ERC20)
    '0xcb5e698c',  # MAX_SUPPLY()
]


CACHE_DIR = '.cache'
os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(chain, contract):
    return os.path.join(CACHE_DIR, f'{chain}_{contract}.json')


def _read_cache(chain, contract):
    path = _cache_path(chain, contract)
    try:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _write_cache(chain, contract, data):
    try:
        with open(_cache_path(chain, contract), 'w') as f:
            json.dump(data, f)
    except OSError:
        pass






def scrape_opensea_collection(slug: str) -> dict:
    """Get collection info from OpenSea API v2 — no API key needed."""
    url = f'https://api.opensea.io/api/v2/collections/{slug}'
    try:
        resp = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
    except requests.RequestException as e:
        return {'error': f'Failed to fetch: {str(e)[:60]}'}
    if resp.status_code != 200:
        return {'error': f'API HTTP {resp.status_code}'}

    try:
        data = resp.json()
    except ValueError:
        return {'error': 'Invalid API response'}

    contracts = data.get('contracts', [])
    if not contracts:
        return {'error': 'No contracts found for collection'}

    contract_raw = contracts[0].get('address', '')
    contract_chain = contracts[0].get('chain', 'ethereum')
    name = data.get('name', '')

    if not contract_raw:
        return {'error': 'No contract address in API response'}
    if not re.match(r'0x[a-fA-F0-9]{40}', contract_raw):
        return {'error': f'Invalid contract: {contract_raw[:20]}'}

    try:
        contract = Web3.to_checksum_address(contract_raw)
    except Exception:
        return {'error': 'Invalid contract address'}

    # Map chain from API response
    chain_map = {
        'ethereum': 'ethereum', 'eth': 'ethereum',
        'base': 'base',
        'optimism': 'optimism',
        'arbitrum': 'arbitrum', 'arb': 'arbitrum',
        'polygon': 'polygon', 'matic': 'polygon',
        'bsc': 'bsc', 'bnb': 'bsc',
        'sepolia': 'ethereum',  # fallback
    }
    chain = chain_map.get(contract_chain.lower(), 'ethereum')

    return {'contract': contract, 'chain': chain, 'name': name}

def _decode_abi_string(hex_data) -> str:
    """Manual ABI string decoder — no w3.codec dependency."""
    if isinstance(hex_data, (bytes, bytearray)):
        hex_str = hex_data.hex()
    elif isinstance(hex_data, str):
        if hex_data.startswith('0x'):
            hex_str = hex_data[2:]
        else:
            hex_str = hex_data
    else:
        return ''
    if len(hex_str) < 64:
        return ''
    offset_bytes = int(hex_str[:64], 16)
    data_start = offset_bytes * 2
    if data_start + 64 > len(hex_str):
        return ''
    str_len = int(hex_str[data_start:data_start+64], 16)
    if str_len == 0 or data_start + 64 + str_len * 2 > len(hex_str):
        return ''
    raw = hex_str[data_start+64:data_start+64+str_len*2]
    return bytes.fromhex(raw).decode('utf-8', errors='replace')


def detect_onchain(contract: str, chain: str) -> dict:
    """Pure on-chain detection: name, symbol, tiers, chainId.
    Parallel eth_call via ThreadPoolExecutor."""
    # Cache check
    cached = _read_cache(chain, contract)
    if cached:
        return cached

    rpc = get_rpc(chain)
    if not rpc:
        return {'error': f'Unknown chain: {chain}'}

    try:
        contract = Web3.to_checksum_address(contract)
    except Exception:
        return {'error': 'Invalid contract address'}

    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        return {'error': 'RPC not connected'}

    chain_id = w3.eth.chain_id

    # ── Parallel eth_call ──
    name_sig = '0x06fdde03'
    symbol_sig = '0x95d89b41'
    all_selectors = {}

    all_selectors['name'] = name_sig
    all_selectors['symbol'] = symbol_sig

    for sel in GLOBAL_MAX_SELECTORS:
        all_selectors[f'gm:{sel}'] = sel

    for tn, sels in TIER_METHODS:
        for sel in sels:
            all_selectors[f'tp:{tn}:{sel}'] = sel

    # Price selectors — separate from tier detection
    for sel in PRICE_SELECTORS:
        all_selectors[f'pr:{sel}'] = sel

    raw = {}

    with ThreadPoolExecutor(max_workers=10) as pool:
        def _call(key, data):
            try:
                resp = w3.eth.call({'to': contract, 'data': data})
                # Normalize bytes/HexBytes to hex string
                if isinstance(resp, (bytes, bytearray)):
                    resp = '0x' + resp.hex()
                return key, resp
            except Exception:
                return key, None

        futs = {pool.submit(_call, k, s): k for k, s in all_selectors.items()}
        for f in as_completed(futs):
            try:
                k, v = f.result()
                raw[k] = v
            except Exception:
                pass

    # ── Process results ──
    # Global max
    global_max = 0
    for sel in GLOBAL_MAX_SELECTORS:
        resp = raw.get(f'gm:{sel}')
        if resp and resp != '0x' and len(resp) >= 66:
            val = int(resp, 16)
            if 0 < val < 1000000:
                global_max = val
                break

    # Try dedicated price selectors first
    onchain_price = 0
    for sel in PRICE_SELECTORS:
        resp = raw.get(f'pr:{sel}')
        if resp and resp != '0x' and len(resp) >= 3:
            try:
                val = int(resp, 16)
                # Valid price: 1 wei to 10_000 ETH
                if 1 <= val <= 10_000_000_000_000_000_000:
                    onchain_price = val
                    break
            except Exception:
                pass

    # Name + symbol
    result = {'contract': contract, 'chain': chain, 'chainId': chain_id, 'tiers': []}
    n_raw = raw.get('name')
    if n_raw:
        result['name'] = _decode_abi_string(n_raw)
    s_raw = raw.get('symbol')
    if s_raw:
        result['symbol'] = _decode_abi_string(s_raw)

    detected = []

    # Tier detection: a selector EXISTS if it returns data (non-empty, non-zero)
    # but we DON'T use that data as price — it's often totalSupply, maxMint, etc.
    for tn, sels in TIER_METHODS:
        found = False
        for sel in sels:
            resp = raw.get(f'tp:{tn}:{sel}')
            if resp and resp != '0x' and len(resp) >= 66:
                found = True
                break
            elif resp and resp != '0x':
                # Short response but non-zero — function might return bool
                val = int(resp, 16)
                if val > 0 and val < 0x100:
                    found = True
                    break

        if not found:
            continue

        entry = {
            'name': tn,
            'price': onchain_price / 1e18,
            'methodSig': sels[0],
            'status': 'active',
            'maxMint': global_max if global_max > 0 else 0,
        }
        detected.append(entry)

    # Always add Public mint if not already detected
    has_public = any(t['name'] == 'Public' for t in detected)
    if not has_public:
        mint_sig = TIER_METHODS[0][1][0]  # 0x1249c58b
        detected.append({
            'name': 'Public',
            'price': onchain_price / 1e18,
            'methodSig': mint_sig,
            'status': 'active',
            'maxMint': global_max if global_max > 0 else 0,
        })

    result['tiers'] = detected

    # Save to cache
    _write_cache(chain, contract, result)

    return result


def detect(input_str: str, chain_hint: str = '', custom_rpc: str = '') -> dict:
    """Parse input, detect NFT info.
    input_str bisa URL OpenSea atau contract address.
    Kalo contract, chain WAJIB diisi (no more auto-detect multi-chain).
    """
    s = input_str.strip()

    # ── OpenSea URL ──
    if s.startswith('http'):
        # Parse slug from URL
        slug_match = re.search(r'opensea\.io/(?:collection/)?([^/?]+)', s)
        if not slug_match:
            return {'error': 'Invalid OpenSea URL'}
        slug = slug_match.group(1)

        # Scrape
        scraped = scrape_opensea_collection(slug)
        if scraped.get('error'):
            return scraped
        contract = scraped['contract']
        chain = scraped['chain']

        # On-chain detect
        onchain = detect_onchain(contract, chain)
        if onchain.get('error'):
            return onchain
        onchain['contract'] = contract
        onchain['chain'] = chain
        onchain['name'] = onchain.get('name') or scraped.get('name', '')
        return onchain

    # ── Contract address ──
    if s.startswith('0x') and len(s) == 42:
        if not chain_hint:
            return {'error': 'Chain required. Use --chain eth/base/op/arb/polygon/bsc'}
        chain = _resolve_chain(chain_hint)
        if not chain:
            return {'error': f'Unknown chain: {chain_hint}'}
        contract = s
        onchain = detect_onchain(contract, chain)
        if onchain.get('error'):
            return onchain
        onchain['contract'] = contract
        onchain['chain'] = chain
        return onchain

    return {'error': 'Invalid input. Provide OpenSea URL or contract address (0x...)'}
