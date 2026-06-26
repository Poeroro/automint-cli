"""Eligibility check: balance, whitelist, gas estimate."""

import time
from web3 import Web3

from .config import get_rpc

def check_eligibility(contract: str, chain: str, wallet: str, tiers: list, custom_rpc: str = '') -> list:
    """Cek eligibility tiap tier buat wallet tertentu."""
    rpc = custom_rpc or get_rpc(chain)
    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        return []

    # Balance ETH
    wei_balance = w3.eth.get_balance(wallet)
    eth_balance = wei_balance / 1e18

    # Minted count (balanceOf)
    minted = 0
    balance_of_sig = '0x70a08231' + '0' * 24 + wallet[2:].lower()
    try:
        resp = w3.eth.call({'to': contract, 'data': balance_of_sig})
        if resp and resp != '0x':
            minted = int(resp, 16)
    except: pass

    results = []
    for tier in tiers:
        name = tier.get('name', '')
        price = tier.get('price', 0)
        method_sig = tier.get('methodSig', '')
        status = tier.get('status', 'unknown')

        eligible = False
        reasons = []

        # Whitelist check for non-public tiers
        if 'public' not in name.lower():
            view_sels = [
                ('0x3af32abf', 'isWhitelisted'),
                ('0x5c1f0ecf', 'isAllowlisted'),
                ('0x415fc4b3', 'whitelisted'),
            ]
            for sel, _ in view_sels:
                try:
                    data = sel + '0' * 24 + wallet[2:].lower()
                    resp = w3.eth.call({'to': contract, 'data': data})
                    if resp and resp not in ('0x', None) and len(resp) >= 66:
                        val = int(resp, 16)
                        if val == 1:
                            eligible = True
                            reasons.append('whitelisted')
                            break
                except: pass

        # Free tier — simulate mint
        if not eligible and price == 0 and method_sig:
            try:
                calldata = method_sig + '0' * 63 + '1'
                tx = {'from': wallet, 'to': contract, 'data': calldata, 'value': '0x0'}
                w3.eth.call(tx)
                eligible = True
                reasons.append('free mint OK')
            except: pass

        # Public paid — balance check
        if not eligible and 'public' in name.lower():
            if eth_balance >= price:
                eligible = True
                reasons.append(f'balance: {eth_balance:.4f} >= {price} ETH')
            else:
                reasons.append(f'insufficient: {eth_balance:.4f} < {price} ETH')

        if not eligible and not reasons:
            reasons.append('not eligible')

        results.append({
            'name': name,
            'price': price,
            'status': status,
            'eligible': eligible,
            'reasons': reasons,
            'balance': eth_balance,
            'minted': minted,
        })

    return results


def estimate_total_cost(contract: str, chain: str, wallet: str, tier: dict, custom_rpc: str = '') -> dict:
    """Estimasi total cost: mint price + gas."""
    rpc = custom_rpc or get_rpc(chain)
    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        return {'error': 'RPC not connected'}

    price_wei = int(tier.get('price', 0) * 1e18)
    method_sig = tier.get('methodSig', '')
    if not method_sig:
        method_sig = '0x1249c58b'

    calldata = method_sig + '0' * 63 + '1'

    try:
        gas_estimate = w3.eth.estimate_gas({'from': wallet, 'to': contract, 'data': calldata, 'value': hex(price_wei)})
    except Exception as e:
        return {'error': f'estimate gas failed: {str(e)[:60]}'}

    try:
        fee_history = w3.eth.fee_history(1, 'latest', [25])
        base_fee = fee_history['baseFeePerGas'][-1]
        max_priority = fee_history['reward'][-1][0] if fee_history['reward'] else 1000000000
        max_fee = base_fee + max_priority
    except:
        max_fee = w3.eth.gas_price

    gas_cost_wei = gas_estimate * max_fee
    total_wei = price_wei + gas_cost_wei

    return {
        'price_eth': price_wei / 1e18,
        'price_wei': price_wei,
        'gas_units': gas_estimate,
        'gas_price_gwei': max_fee / 1e9,
        'gas_cost_eth': gas_cost_wei / 1e18,
        'total_eth': total_wei / 1e18,
        'total_wei': total_wei,
    }
