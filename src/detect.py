"""Detect NFT collection info on-chain + scraped from OpenSea page."""

import re
import os
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

from web3 import Web3

from .config import get_working_rpc
from .config import resolve_chain as _resolve_chain


TIER_METHODS = [
    ('Public',    ['0x1249c58b', '0xa0712d68', '0x2db11544']),
    ('OG',        ['0xa28c555d', '0x3b1ebc7e', '0x7a1ac6c1', '0xb3e126be']),
    ('Allowlist', ['0x3af32abf', '0x5c1f0ecf', '0x415fc4b3', '0x67e0aceb', '0x3cd80455',
                   '0x7bc9200e', '0xfa05a657']),
    ('Presale',   ['0xc693f915', '0xf2c4bc48', '0x316894db', '0xc6690c0f']),
    ('VIP',       ['0x6aaf4481', '0x6403727b']),
    ('Freemint',  ['0xd18e81b3']),
    ('Early',     ['0x2f9166b8', '0xaba3c5f7']),
]

# Selectors that take no arguments
NO_ARG_SIGS = frozenset({'0x1249c58b'})  # mint()

# Merkle allowlist signatures — require bytes32[] proof param
MERKLE_SIGS = frozenset({'0x7bc9200e', '0xfa05a657'})

PRICE_SELECTORS = [
    '0xe7572239',  # cost()
    '0xef18e5e1',  # mintPrice()
    '0x3de39a5c',  # getMintCost()
]

GLOBAL_MAX_SELECTORS = [
    '0xd5abeb01',  # maxSupply()
    '0x32cb6b0c',  # MAX_SUPPLY()
    '0x18160ddd',  # totalSupply() — fallback
]

SCHEDULE_SELECTORS = {
    'public': [
        '0x78e97925',  # startTime()
        '0x1cbaee2d',  # saleStartTime()
        '0x6bb7b1d9',  # publicSaleStartTime()
        '0x255e4685',  # mintStart()
        '0x931e2e49',  # mintStartTime()
    ],
    'allowlist': [
        '0x525fc0e3',  # allowlistMintStartTime()
        '0x3cc1251f',  # allowlistStart()
        '0xbe9feb30',  # wlStartTime()
    ],
    'presale': [
        '0xa82524b2',  # presaleStartTime()
        '0x06d65af3',  # preSaleStartTime()
    ],
}

CACHE_DIR = '.cache'
CACHE_TTL = 3600  # 1 hour

os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(chain: str, contract: str) -> str:
    return os.path.join(CACHE_DIR, f'{chain}_{contract}.json')


def _read_cache(chain: str, contract: str) -> dict | None:
    path = _cache_path(chain, contract)
    try:
        if os.path.exists(path):
            if time.time() - os.stat(path).st_mtime < CACHE_TTL:
                with open(path) as f:
                    return json.load(f)
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _write_cache(chain: str, contract: str, data: dict) -> None:
    try:
        with open(_cache_path(chain, contract), 'w') as f:
            json.dump(data, f)
    except OSError:
        pass


def build_calldata(method_sig: str, quantity: int, merkle_proof: list | None = None) -> str:
    """Build ABI calldata for a mint function.

    Handles three patterns:
    - no-arg: mint()
    - uint256: mint(uint256), publicMint(uint256)
    - uint256 + bytes32[]: allowlistMint(uint256, bytes32[])
    """
    if method_sig in NO_ARG_SIGS:
        return method_sig

    qty_hex = hex(quantity)[2:].zfill(64)

    if method_sig in MERKLE_SIGS and merkle_proof:
        offset_hex = hex(64)[2:].zfill(64)
        proof_len_hex = hex(len(merkle_proof))[2:].zfill(64)
        proof_data = ''.join(p.lstrip('0x').zfill(64) for p in merkle_proof)
        return method_sig + qty_hex + offset_hex + proof_len_hex + proof_data

    return method_sig + qty_hex


_OS_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9',
}


def scrape_opensea_collection(slug: str) -> dict:
    """Get collection info from OpenSea API v2.

    Supports optional OPENSEA_API_KEY env var.
    Retries on 429/401 with backoff (rate limit or temporary block).
    """
    import os as _os
    url = f'https://api.opensea.io/api/v2/collections/{slug}'
    headers = dict(_OS_HEADERS)
    api_key = _os.getenv('OPENSEA_API_KEY', '').strip()
    if api_key:
        headers['x-api-key'] = api_key

    last_status = None
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=15, headers=headers)
            last_status = resp.status_code
            if resp.status_code == 200:
                break
            if resp.status_code in (401, 429):
                # Rate limited or IP blocked — wait and retry
                retry_after = int(resp.headers.get('retry-after', 5 * (attempt + 1)))
                time.sleep(min(retry_after, 15))
                continue
            # Other error — no point retrying
            return {'error': f'API HTTP {resp.status_code}'}
        except requests.RequestException as e:
            return {'error': f'Failed to fetch: {str(e)[:60]}'}
    else:
        if last_status in (401, 429):
            hint = ' (set OPENSEA_API_KEY in .env to avoid rate limits)' if not api_key else ''
            return {'error': f'API HTTP {last_status} after retries{hint}'}
        return {'error': f'API HTTP {last_status}'}

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
    if not re.match(r'^0x[a-fA-F0-9]{40}$', contract_raw):
        return {'error': f'Invalid contract: {contract_raw[:20]}'}

    try:
        contract = Web3.to_checksum_address(contract_raw)
    except Exception:
        return {'error': 'Invalid contract address'}

    chain_map = {
        'ethereum': 'ethereum', 'eth': 'ethereum',
        'base': 'base',
        'optimism': 'optimism',
        'arbitrum': 'arbitrum', 'arb': 'arbitrum',
        'polygon': 'polygon', 'matic': 'polygon',
        'bsc': 'bsc', 'bnb': 'bsc',
        'sepolia': 'ethereum',
    }
    chain = chain_map.get(contract_chain.lower(), 'ethereum')
    return {'contract': contract, 'chain': chain, 'name': name}


def _decode_abi_string(hex_data) -> str:
    """Decode ABI-encoded string return value."""
    if isinstance(hex_data, (bytes, bytearray)):
        hex_str = hex_data.hex()
    elif isinstance(hex_data, str):
        hex_str = hex_data[2:] if hex_data.startswith('0x') else hex_data
    else:
        return ''
    if len(hex_str) < 64:
        return ''
    try:
        offset_bytes = int(hex_str[:64], 16)
        data_start = offset_bytes * 2
        if data_start + 64 > len(hex_str):
            return ''
        str_len = int(hex_str[data_start:data_start + 64], 16)
        if str_len == 0 or data_start + 64 + str_len * 2 > len(hex_str):
            return ''
        raw = hex_str[data_start + 64:data_start + 64 + str_len * 2]
        return bytes.fromhex(raw).decode('utf-8', errors='replace')
    except (ValueError, IndexError):
        return ''


def _resolve_start_time(w3: Web3, contract: str, tier_name: str) -> int | None:
    """Query on-chain start time selectors. Returns unix timestamp or None."""
    name_lower = tier_name.lower()
    if any(k in name_lower for k in ('allowlist', 'whitelist', 'wl', 'og')):
        sel_list = SCHEDULE_SELECTORS['allowlist'] + SCHEDULE_SELECTORS['public']
    elif any(k in name_lower for k in ('presale', 'early', 'vip')):
        sel_list = SCHEDULE_SELECTORS['presale'] + SCHEDULE_SELECTORS['public']
    else:
        sel_list = SCHEDULE_SELECTORS['public']

    for sel in sel_list:
        try:
            resp = w3.eth.call({'to': contract, 'data': sel})
            if isinstance(resp, (bytes, bytearray)):
                resp = '0x' + resp.hex()
            if not resp or resp in ('0x', '0x0'):
                continue
            val = int(resp, 16)
            # Plausible unix timestamp: 2020-01-01 to 2030-01-01
            if 1_577_836_800 <= val <= 1_893_456_000:
                return val
        except Exception:
            pass
    return None


def detect_onchain(contract: str, chain: str, custom_rpc: str = '') -> dict:
    """Pure on-chain detection: name, symbol, tiers, chainId."""
    # Checksum before cache lookup so cache keys are consistent
    try:
        contract = Web3.to_checksum_address(contract)
    except Exception:
        return {'error': 'Invalid contract address'}

    cached = _read_cache(chain, contract)
    if cached:
        return cached

    try:
        rpc = get_working_rpc(chain, custom_rpc)
    except RuntimeError as e:
        return {'error': str(e)}

    w3 = Web3(Web3.HTTPProvider(rpc))

    chain_id = w3.eth.chain_id

    all_selectors: dict[str, str] = {
        'name':   '0x06fdde03',
        'symbol': '0x95d89b41',
    }
    for sel in GLOBAL_MAX_SELECTORS:
        all_selectors[f'gm:{sel}'] = sel
    for tn, sels in TIER_METHODS:
        for sel in sels:
            all_selectors[f'tp:{tn}:{sel}'] = sel
    for sel in PRICE_SELECTORS:
        all_selectors[f'pr:{sel}'] = sel

    raw: dict[str, str | None] = {}

    def _to_hex(resp) -> str:
        if resp is None:
            return ''
        if isinstance(resp, (bytes, bytearray)):
            return '0x' + resp.hex()
        return str(resp)

    with ThreadPoolExecutor(max_workers=12) as pool:
        def _call(key: str, data: str):
            try:
                return key, _to_hex(w3.eth.call({'to': contract, 'data': data}))
            except Exception:
                return key, None

        futs = {pool.submit(_call, k, s): k for k, s in all_selectors.items()}
        for f in as_completed(futs):
            try:
                k, v = f.result()
                raw[k] = v
            except Exception:
                pass

    def _hex_to_int(h) -> int | None:
        if not h or h in ('0x', '0x0'):
            return None
        try:
            if isinstance(h, (bytes, bytearray)):
                h = '0x' + h.hex()
            return int(h, 16)
        except (ValueError, TypeError):
            return None

    # Global max supply
    global_max = 0
    for sel in GLOBAL_MAX_SELECTORS:
        val = _hex_to_int(raw.get(f'gm:{sel}'))
        if val and 1 < val <= 10_000_000:
            global_max = val
            break

    # Mint price
    onchain_price = 0
    for sel in PRICE_SELECTORS:
        val = _hex_to_int(raw.get(f'pr:{sel}'))
        if val and 1 <= val <= 10_000_000_000_000_000_000:
            onchain_price = val
            break

    result: dict = {'contract': contract, 'chain': chain, 'chainId': chain_id, 'tiers': []}
    n_raw = raw.get('name')
    if n_raw:
        result['name'] = _decode_abi_string(n_raw)
    s_raw = raw.get('symbol')
    if s_raw:
        result['symbol'] = _decode_abi_string(s_raw)

    now = int(time.time())
    detected = []

    for tn, sels in TIER_METHODS:
        found_sig = None
        for sel in sels:
            resp = raw.get(f'tp:{tn}:{sel}')
            if not resp or resp in ('0x', '0x0', None):
                continue
            stripped = resp[2:] if resp.startswith('0x') else resp
            if len(stripped) >= 64:
                val = _hex_to_int(resp)
                if val is not None and val > 0:
                    found_sig = sel
                    break
            elif len(stripped) in (1, 2):
                if _hex_to_int(resp) == 1:
                    found_sig = sel
                    break

        if not found_sig:
            continue

        start_ts = _resolve_start_time(w3, contract, tn)
        status = f'scheduled:{start_ts}' if (start_ts and start_ts > now) else 'active'

        detected.append({
            'name': tn,
            'price': onchain_price / 1e18,
            'methodSig': found_sig,
            'status': status,
            'maxMint': global_max,
            'requiresMerkle': found_sig in MERKLE_SIGS,
        })

    result['tiers'] = detected
    _write_cache(chain, contract, result)
    return result


def detect(input_str: str, chain_hint: str = '', custom_rpc: str = '') -> dict:
    """Parse input and detect NFT info. Accepts OpenSea URL or contract address."""
    s = input_str.strip()

    if s.startswith('http'):
        slug_match = re.search(r'opensea\.io/(?:collection/)?([^/?#]+)', s)
        if not slug_match:
            return {'error': 'Invalid OpenSea URL'}
        slug = slug_match.group(1)

        scraped = scrape_opensea_collection(slug)
        if scraped.get('error'):
            return scraped

        contract = scraped['contract']
        chain = scraped['chain']

        onchain = detect_onchain(contract, chain, custom_rpc)
        if onchain.get('error'):
            return onchain
        onchain['name'] = onchain.get('name') or scraped.get('name', '')
        return onchain

    if re.match(r'^0x[a-fA-F0-9]{40}$', s):
        if not chain_hint:
            return {'error': 'Chain required. Use --chain eth/base/op/arb/polygon/bsc'}
        chain = _resolve_chain(chain_hint)
        if not chain:
            return {'error': f'Unknown chain: {chain_hint}'}
        return detect_onchain(s, chain, custom_rpc)

    return {'error': 'Invalid input. Provide OpenSea URL or contract address (0x...)'}
