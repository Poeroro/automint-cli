"""Detect contract + tiers from OpenSea URL or contract address."""

import re, time
import requests
from web3 import Web3

from .config import get_rpc, CHAINS, CHAIN_MAP
from .config import resolve_chain as _resolve_chain

# ── Known chain identifiers from OpenSea ──
OS_CHAIN_MAP = {
    'ethereum': 'ethereum', 'eth': 'ethereum',
    'base': 'base',
    'optimism': 'optimism', 'op': 'optimism',
    'arbitrum': 'arbitrum', 'arb': 'arbitrum',
    'polygon': 'polygon', 'matic': 'polygon',
    'bsc': 'bsc', 'binance': 'bsc',
}


def scrape_opensea_collection(slug: str) -> dict:
    """Scrape OpenSea page HTML for contract address + chain."""
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
        # Pattern: chain object then address within ~500 chars
        # "chain":{"identifier":"ethereum",...}..."address":"0x..."
        chain_addr = re.search(
            r'"chain"\s*:\s*\{[^}]*?"identifier"\s*:\s*"([^"]+)"[^}]*?\}'
            r'[\s\S]{0,500}?"address"\s*:\s*"(0x[a-fA-F0-9]{40})"',
            html
        )
        if not chain_addr:
            # Try reverse: address then chain
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
    """Detect tier info, prices, timestamps via eth_call."""
    rpc = custom_rpc or get_rpc(chain)
    chain_info = CHAINS.get(chain)
    if not chain_info or not rpc:
        return {'error': 'unknown chain'}

    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        return {'error': 'RPC not connected'}

    # Checksum contract address
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

    # Global max mint (fallback)
    global_max = 0
    global_max_selectors = [
        '0xac5ba77b',  # maxMintAmount
        '0x3a84b649',  # maxMintPerTx
        '0xc3c5a547',  # maxPerMint
        '0x1f2dcdb7',  # maxPerWallet
    ]
    for sel in global_max_selectors:
        try:
            resp = w3.eth.call({'to': contract, 'data': sel})
            if resp and resp != '0x' and len(resp) >= 66:
                val = int(resp, 16)
                if 0 < val < 1000000:
                    global_max = val
                    break
        except:
            pass

    # Name + symbol
    try:
        name_bytes = w3.eth.call({'to': contract, 'data': '0x06fdde03'})
        result['name'] = w3.codec.decode(['string'], name_bytes)[0] if len(name_bytes) > 2 else ''
    except:
        pass
    try:
        sym_bytes = w3.eth.call({'to': contract, 'data': '0x95d89b41'})
        result['symbol'] = w3.codec.decode(['string'], sym_bytes)[0] if len(sym_bytes) > 2 else ''
    except:
        pass

    now = int(time.time())

    TIER_METHODS = [
        ('Team',     ['0x8f0f73a8', '0x3b2b4b03']),
        ('GTD',      ['0xb6b5b5b5', '0xcc5c095f']),
        ('FCFS',     ['0xc2cf717c', '0x0c91f87b']),
        ('Allowlist',['0x52044153', '0x075a0e8d']),
        ('Public',   ['0x1249c58b', '0x3808e184']),
    ]

    price_selectors = {
        'Public':     '0x1249c58b',
        'Allowlist':  '0x52044153',
        'FCFS':       '0x0c91f87b',
        'GTD':        '0xb6b5b5b5',
        'Team':       '0x8f0f73a8',
    }
    time_selectors = {
        'Public':     '0xefefefef',
        'Allowlist':  '0x5c1f0ecf',
        'FCFS':       '0xc2cf717c',
    }

    detected = []
    for tier_name, sels in TIER_METHODS:
        tier_price = 0
        tier_start = None
        tier_sig = ''

        # Price
        price_sel = price_selectors.get(tier_name)
        if price_sel:
            try:
                resp = w3.eth.call({'to': contract, 'data': price_sel})
                if resp and resp != '0x' and len(resp) >= 66:
                    val = int(resp, 16)
                    if val > 0:
                        tier_price = val / 1e18
                        tier_sig = price_sel
            except:
                pass

        # Start time
        time_sel = time_selectors.get(tier_name)
        if time_sel:
            try:
                resp = w3.eth.call({'to': contract, 'data': time_sel})
                if resp and resp != '0x' and len(resp) >= 66:
                    ts = int(resp, 16)
                    if ts > 1000000000:
                        tier_start = ts
                        tier_sig = tier_sig or sels[0]
            except:
                pass

        # Method existence check
        for sel in sels:
            if not tier_sig:
                try:
                    resp = w3.eth.call({'to': contract, 'data': sel + '0' * 63 + '1'})
                    if resp and resp != '0x':
                        tier_sig = sel
                        break
                except:
                    pass

        if not tier_sig and tier_name != 'Public':
            continue

        status = 'unknown'
        if tier_start:
            if tier_start > now:
                status = f'scheduled:{tier_start}'
            else:
                status = 'active'
        elif tier_price > 0:
            status = 'active'
        elif tier_name == 'Public':
            status = 'active'

        # Max mint per tier
        tier_max = 0
        tier_max_sels = []
        if tier_name == 'Public':
            tier_max_sels = ['0x64e604ba', '0x77141fb6', '0xce40e4c8']
        elif tier_name == 'Allowlist':
            tier_max_sels = ['0x2a38dee1', '0x84568828', '0x3013ce4b']
        elif tier_name == 'FCFS':
            tier_max_sels = ['0x2e2f4cc2']
        elif tier_name == 'GTD':
            tier_max_sels = ['0x0b6b5b5b']
        elif tier_name == 'Team':
            tier_max_sels = ['0x8f0f73a8']
        for sel in tier_max_sels:
            try:
                resp = w3.eth.call({'to': contract, 'data': sel})
                if resp and resp != '0x' and len(resp) >= 66:
                    val = int(resp, 16)
                    if 0 < val < 1000000:
                        tier_max = val
                        break
            except:
                pass
        if not tier_max:
            tier_max = global_max

        detected.append({
            'name': tier_name,
            'price': tier_price,
            'startTime': tier_start,
            'status': status,
            'methodSig': tier_sig,
            'maxMint': tier_max,
        })

    # Fallback: global mintPrice
    if not detected:
        try:
            resp = w3.eth.call({'to': contract, 'data': '0x1249c58b'})
            if resp and resp != '0x' and len(resp) >= 66:
                val = int(resp, 16)
                if val > 0:
                    result['mintPrice'] = val / 1e18
                    detected.append({
                        'name': 'Public', 'price': val / 1e18,
                        'startTime': None, 'status': 'active',
                        'methodSig': '0x1249c58b',
                    })
        except:
            pass

    result['tiers'] = detected
    return result


def detect(url_or_contract: str, chain_hint: str = '', custom_rpc: str = '') -> dict:
    """Main detect — URL → scrape → on-chain, or contract → on-chain.

    If contract address given WITHOUT --chain, returns error immediately.
    No more auto-detect loop across 6 chains (was 18s timeout waste).
    """
    # Contract address langsung
    if re.match(r'^0x[a-fA-F0-9]{40}$', url_or_contract):
        chain_resolved = _resolve_chain(chain_hint)
        if not chain_resolved:
            if chain_hint:
                return {'error': f'Unknown chain: "{chain_hint}". Use: eth/base/op/arb/polygon/bsc'}
            else:
                return {'error': 'Chain required with contract address. Use --chain eth/base/op/arb/polygon/bsc'}
        return detect_onchain(url_or_contract, chain_resolved, custom_rpc)

    # OpenSea URL — scrape not API
    m = re.search(r'opensea\.io/collection/([^/?#]+)', url_or_contract)
    if m:
        slug = m.group(1)
        pass  # print(f'Scraping OpenSea collection "{slug}"...')
        resolved = scrape_opensea_collection(slug)
        if resolved.get('error'):
            return {'error': resolved['error'], 'name': slug}
        onchain = detect_onchain(resolved['contract'], resolved['chain'], custom_rpc)
        if onchain.get('error'):
            return onchain
        onchain['name'] = onchain.get('name') or resolved['name']
        onchain['slug'] = slug
        return onchain

    return {'error': 'Invalid input — use OpenSea URL or 0x contract address'}
