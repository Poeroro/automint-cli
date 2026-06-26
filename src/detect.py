"""Detect contract + tiers dari OpenSea URL atau contract address."""

import re, time, json
import requests
from web3 import Web3

from .config import get_opensea_api_key, get_rpc, CHAINS, CHAIN_MAP

def resolve_collection(slug: str, chain_hint: str = 'ethereum') -> dict:
    """Cari contract + stages dari OpenSea API v2."""
    result = {'contract': None, 'chain': chain_hint, 'name': '', 'stages': []}
    api_key = get_opensea_api_key()
    if not api_key:
        result['warning'] = 'OPENSEA_API_KEY not set in .env — OS API will fail'
    headers = {
        'X-API-KEY': api_key,
        'Accept': 'application/json',
    }
    # Coba OS API v2
    try:
        r = requests.get(
            f'https://api.opensea.io/v2/collections/{slug}',
            headers=headers, timeout=10
        )
        if r.ok:
            d = r.json()
            result['name'] = d.get('name', slug)
            contracts = d.get('contracts', [])
            if contracts:
                c = contracts[0]
                result['contract'] = c.get('address', '')
                chain_str = c.get('chain', 'ethereum').lower()
                result['chain'] = CHAIN_MAP.get(chain_str, chain_str)
        elif r.status_code in (401, 403):
            result['warning'] = 'OPENSEA_API_KEY invalid or expired (HTTP 401/403)'
    except:
        pass

    # Coba v1 API fallback
    if not result['contract']:
        try:
            r = requests.get(
                f'https://api.opensea.io/api/v1/collection/{slug}',
                headers=headers, timeout=10
            )
            if r.ok:
                d = r.json().get('collection', {})
                result['name'] = d.get('name', slug)
                pac = d.get('primary_asset_contracts', [])
                if pac:
                    result['contract'] = pac[0].get('address', '')
        except:
            pass

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

    # Coba dapetin nama + symbol
    try:
        name_bytes = w3.eth.call({'to': contract, 'data': '0x06fdde03'})
        result['name'] = w3.codec.decode(['string'], name_bytes)[0] if len(name_bytes) > 2 else ''
    except: pass
    try:
        sym_bytes = w3.eth.call({'to': contract, 'data': '0x95d89b41'})
        result['symbol'] = w3.codec.decode(['string'], sym_bytes)[0] if len(sym_bytes) > 2 else ''
    except: pass

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

        # Cek price
        price_sel = price_selectors.get(tier_name)
        if price_sel:
            try:
                resp = w3.eth.call({'to': contract, 'data': price_sel})
                if resp and resp != '0x' and len(resp) >= 66:
                    val = int(resp, 16)
                    if val > 0:
                        tier_price = val / 1e18
                        tier_sig = price_sel
            except: pass

        # Cek start time
        time_sel = time_selectors.get(tier_name)
        if time_sel:
            try:
                resp = w3.eth.call({'to': contract, 'data': time_sel})
                if resp and resp != '0x' and len(resp) >= 66:
                    ts = int(resp, 16)
                    if ts > 1000000000:
                        tier_start = ts
                        tier_sig = tier_sig or sels[0]
            except: pass

        # Cek method exists
        for sel in sels:
            if not tier_sig:
                try:
                    resp = w3.eth.call({'to': contract, 'data': sel + '0' * 63 + '1'})
                    if resp and resp != '0x':
                        tier_sig = sel
                        break
                except: pass

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

        detected.append({
            'name': tier_name,
            'price': tier_price,
            'startTime': tier_start,
            'status': status,
            'methodSig': tier_sig,
        })

    # Fallback: mintPrice global
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
        except: pass

    result['tiers'] = detected
    return result


def detect(url_or_contract: str, chain_hint: str = '', custom_rpc: str = '') -> dict:
    """Main detect — URL → resolve → on-chain, or contract langsung."""
    # Contract address langsung
    if re.match(r'^0x[a-fA-F0-9]{40}$', url_or_contract):
        if not chain_hint:
            return {'error': 'Chain required for contract address'}
        return detect_onchain(url_or_contract, chain_hint, custom_rpc)

    # OpenSea URL
    m = re.search(r'opensea\.io/collection/([^/?#]+)', url_or_contract)
    if m:
        slug = m.group(1)
        resolved = resolve_collection(slug, chain_hint or 'ethereum')
        if not resolved['contract']:
            return {'error': 'Could not resolve contract', 'name': resolved['name'], 'stages': resolved['stages']}
        onchain = detect_onchain(resolved['contract'], resolved['chain'], custom_rpc)
        onchain['name'] = onchain['name'] or resolved['name']
        onchain['slug'] = slug
        # Merge OS stages kalo on-chain tiers kosong
        if not onchain['tiers'] and resolved['stages']:
            onchain['tiers'] = resolved['stages']
        return onchain

    return {'error': 'Invalid input — use OpenSea URL or 0x contract address'}
