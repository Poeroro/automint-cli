"""Detect contract + tiers from OpenSea URL or contract address.

Parallel eth_call + cache contract results.
"""

import re, time, os, json
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from web3 import Web3

from .config import get_rpc, CHAINS, CHAIN_MAP
from .config import resolve_chain as _resolve_chain

OS_CHAIN_MAP = {
    'ethereum': 'ethereum', 'eth': 'ethereum',
    'base': 'base',
    'optimism': 'optimism', 'op': 'optimism',
    'arbitrum': 'arbitrum', 'arb': 'arbitrum',
    'polygon': 'polygon', 'matic': 'polygon',
    'bsc': 'bsc', 'binance': 'bsc',
}

CACHE_DIR = '.cache'


def _cache_path(chain: str, contract: str) -> str:
    """Path for cached detect result."""
    return os.path.join(CACHE_DIR, f'{chain}_{contract.lower()}.json')


def _load_cache(chain: str, contract: str) -> dict | None:
    """Load cached detect result. Return None if miss/expired/stale."""
    path = _cache_path(chain, contract)
    try:
        with open(path) as f:
            data = json.load(f)
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_cache(chain: str, contract: str, data: dict):
    """Save detect result to cache."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        path = _cache_path(chain, contract)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    except OSError:
        pass  # cache failure non-fatal


def scrape_opensea_collection(slug: str) -> dict:
    """Scrape OpenSea page HTML for contract address + chain (~1-3s)."""
    result = {'contract': '', 'chain': 'ethereum', 'name': slug}
    try:
        resp = requests.get(
            f'https://opensea.io/collection/{slug}',
            headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'},
            timeout=10
        )
        if not resp.ok:
            result['error'] = f'HTTP {resp.status_code} fetching collection page'
            return result

        html = resp.text
        chain_addr = re.search(
            r'"chain"\s*:\s*\{[^}]*?"identifier"\s*:\s*"([^"]+)"[^}]*?\}'
            r'[\s\S]{0,500}?"address"\s*:\s*"(0x[a-fA-F0-9]{40})"',
            html
        )
        if not chain_addr:
            chain_addr = re.search(
                r'"address"\s*:\s*"(0x[a-fA-F0-9]{40})"'
                r'[\s\S]{0,500}?"chain"\s*:\s*\{[^}]*?"identifier"\s*:\s*"([^"]+)"',
                html
            )
            if chain_addr:
                contract, raw_chain = chain_addr.group(1), chain_addr.group(2)
            else:
                result['error'] = 'Could not find contract + chain in page'
                return result
        else:
            raw_chain, contract = chain_addr.group(1), chain_addr.group(2)

        result['contract'] = Web3.to_checksum_address(contract) if contract else ''
        result['chain'] = OS_CHAIN_MAP.get(raw_chain.lower(), raw_chain.lower())
        return result

    except requests.RequestException as e:
        result['error'] = f'Network error: {e}'
        return result


def detect_onchain(contract: str, chain: str, custom_rpc: str = '') -> dict:
    """Detect tier info, prices, timestamps via parallel eth_call (~300ms)."""
    rpc = custom_rpc or get_rpc(chain)
    chain_info = CHAINS.get(chain)
    if not chain_info or not rpc:
        return {'error': 'unknown chain'}

    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={'timeout': 10}))
    if not w3.is_connected():
        return {'error': 'RPC not connected'}

    try:
        contract = Web3.to_checksum_address(contract)
    except:
        return {'error': 'Invalid contract address'}

    result = {
        'contract': contract,
        'chain': chain,
        'chainId': chain_info['id'],
        'name': '',
        'symbol': '',
        'mintPrice': None,
        'startTime': None,
        'tiers': [],
    }

    # ── Build all eth_calls ──
    global_max_selectors = ['0xac5ba77b', '0x3a84b649', '0xc3c5a547', '0x1f2dcdb7']

    TIER_METHODS = [
        ('Team',     ['0x8f0f73a8', '0x3b2b4b03']),
        ('GTD',      ['0xb6b5b5b5', '0xcc5c095f']),
        ('FCFS',     ['0xc2cf717c', '0x0c91f87b']),
        ('Allowlist',['0x52044153', '0x075a0e8d']),
        ('Public',   ['0x1249c58b', '0x3808e184']),
    ]

    price_selectors = {
        'Public': '0x1249c58b', 'Allowlist': '0x52044153',
        'FCFS': '0x0c91f87b', 'GTD': '0xb6b5b5b5', 'Team': '0x8f0f73a8',
    }
    time_selectors = {
        'Public': '0xefefefef', 'Allowlist': '0x5c1f0ecf', 'FCFS': '0xc2cf717c',
    }

    tier_max_map = {
        'Public':    ['0x64e604ba', '0x77141fb6', '0xce40e4c8'],
        'Allowlist': ['0x2a38dee1', '0x84568828', '0x3013ce4b'],
        'FCFS':      ['0x2e2f4cc2'],
        'GTD':       ['0x0b6b5b5b'],
        'Team':      ['0x8f0f73a8'],
    }

    # Build flat call list: (key, data)
    # key format: "category:detail" or "global_max:sel" or "name" etc.
    calls = []
    for sel in global_max_selectors:
        calls.append((f'gm:{sel}', sel, False))

    calls.append(('name', '0x06fdde03', False))
    calls.append(('symbol', '0x95d89b41', False))

    for tn, sels in TIER_METHODS:
        ps = price_selectors.get(tn)
        if ps:
            calls.append((f'{tn}:price', ps, False))
        ts = time_selectors.get(tn)
        if ts:
            calls.append((f'{tn}:time', ts, False))
        for sel in sels:
            calls.append((f'{tn}:meth:{sel}', sel + '0' * 63 + '1', True))

        tn_max = tier_max_map.get(tn, [])
        for sel in tn_max:
            calls.append((f'{tn}:max:{sel}', sel, False))

    # ── Execute all eth_calls in parallel ──
    def do_call(args):
        key, data, _ = args
        resp = w3.eth.call({'to': contract, 'data': data})
        return key, resp

    raw = {}
    with ThreadPoolExecutor(max_workers=min(len(calls), 25)) as ex:
        futs = {ex.submit(do_call, c): c[0] for c in calls}
        for f in as_completed(futs):
            try:
                k, v = f.result()
                raw[k] = v
            except:
                pass

    # ── Process results ──
    # Global max
    global_max = 0
    for sel in global_max_selectors:
        resp = raw.get(f'gm:{sel}')
        if resp and resp != '0x' and len(resp) >= 66:
            val = int(resp, 16)
            if 0 < val < 1000000:
                global_max = val
                break

    # Name + symbol
    n_raw = raw.get('name')
    if n_raw and len(n_raw) > 2:
        try:
            result['name'] = w3.codec.decode(['string'], n_raw)[0]
        except:
            pass
    s_raw = raw.get('symbol')
    if s_raw and len(s_raw) > 2:
        try:
            result['symbol'] = w3.codec.decode(['string'], s_raw)[0]
        except:
            pass

    now = int(time.time())
    detected = []

    for tn, sels in TIER_METHODS:
        tier_price = 0
        tier_start = None
        tier_sig = ''

        # Price
        ps = price_selectors.get(tn)
        if ps:
            resp = raw.get(f'{tn}:price')
            if resp and resp != '0x' and len(resp) >= 66:
                val = int(resp, 16)
                if val > 0:
                    tier_price = val / 1e18
                    tier_sig = ps

        # Start time
        ts = time_selectors.get(tn)
        if ts:
            resp = raw.get(f'{tn}:time')
            if resp and resp != '0x' and len(resp) >= 66:
                val = int(resp, 16)
                if val > 1000000000:
                    tier_start = val
                    tier_sig = tier_sig or sels[0]

        # Method existence check
        for sel in sels:
            k = f'{tn}:meth:{sel}'
            if k in raw and raw[k] and raw[k] != '0x':
                tier_sig = sel
                break

        if not tier_sig and tn != 'Public':
            continue

        status = 'unknown'
        if tier_start:
            if tier_start > now:
                status = f'scheduled:{tier_start}'
            else:
                status = 'active'
        elif tier_price > 0:
            status = 'active'
        elif tn == 'Public':
            status = 'active'

        # Max mint
        tier_max = 0
        tn_mx = tier_max_map.get(tn, [])
        for sel in tn_mx:
            resp = raw.get(f'{tn}:max:{sel}')
            if resp and resp != '0x' and len(resp) >= 66:
                val = int(resp, 16)
                if 0 < val < 1000000:
                    tier_max = val
                    break
        if not tier_max:
            tier_max = global_max

        detected.append({
            'name': tn,
            'price': tier_price,
            'startTime': tier_start,
            'status': status,
            'methodSig': tier_sig,
            'maxMint': tier_max,
        })

    # Fallback
    if not detected:
        resp = raw.get('Public:price') or raw.get('gm:0x1249c58b')
        if resp and resp != '0x' and len(resp) >= 66:
            val = int(resp, 16)
            if val > 0:
                result['mintPrice'] = val / 1e18
                detected.append({
                    'name': 'Public', 'price': val / 1e18,
                    'startTime': None, 'status': 'active',
                    'methodSig': '0x1249c58b',
                })

    result['tiers'] = detected
    return result


def detect(url_or_contract: str, chain_hint: str = '', custom_rpc: str = '') -> dict:
    """Main detect — URL → scrape → on-chain, or contract → on-chain.

    Checks cache first. Skips detect_onchain if cached result exists.
    """
    # Contract address langsung
    if re.match(r'^0x[a-fA-F0-9]{40}$', url_or_contract):
        chain_resolved = _resolve_chain(chain_hint)
        if not chain_resolved:
            if chain_hint:
                return {'error': f'Unknown chain: "{chain_hint}". Use: eth/base/op/arb/polygon/bsc'}
            return {'error': 'Chain required with contract address. Use --chain eth/base/op/arb/polygon/bsc'}
        # Check cache
        cached = _load_cache(chain_resolved, url_or_contract)
        if cached:
            cached['_cached'] = True
            return cached
        result = detect_onchain(url_or_contract, chain_resolved, custom_rpc)
        if not result.get('error'):
            _save_cache(chain_resolved, url_or_contract, result)
        return result

    # OpenSea URL — scrape not API
    m = re.search(r'opensea\.io/collection/([^/?#]+)', url_or_contract)
    if m:
        slug = m.group(1)
        resolved = scrape_opensea_collection(slug)
        if resolved.get('error'):
            return {'error': resolved['error'], 'name': slug}
        # Check cache
        cached = _load_cache(resolved['chain'], resolved['contract'])
        if cached:
            cached['_cached'] = True
            cached['name'] = cached.get('name') or resolved['name']
            cached['slug'] = slug
            return cached
        onchain = detect_onchain(resolved['contract'], resolved['chain'], custom_rpc)
        if onchain.get('error'):
            return onchain
        onchain['name'] = onchain.get('name') or resolved['name']
        onchain['slug'] = slug
        if not onchain.get('error'):
            _save_cache(resolved['chain'], resolved['contract'], onchain)
        return onchain

    return {'error': 'Invalid input — use OpenSea URL or 0x contract address'}
