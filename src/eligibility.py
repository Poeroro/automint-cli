"""Eligibility check: balance, whitelist, merkle, gas estimate."""

from web3 import Web3

from .config import get_working_rpc, rpc_retry
from .detect import NO_ARG_SIGS, MERKLE_SIGS, build_calldata


def _resp_to_int(resp) -> int | None:
    if resp is None:
        return None
    if isinstance(resp, (bytes, bytearray)):
        resp = '0x' + resp.hex()
    if not resp or resp in ('0x', '0x0'):
        return None
    try:
        return int(resp, 16)
    except (ValueError, TypeError):
        return None


def check_eligibility(contract: str, chain: str, wallet: str, tiers: list,
                      custom_rpc: str = '', merkle_proofs: dict = None) -> list:
    """Check eligibility for each tier for a given wallet.

    merkle_proofs: optional {tier_name: [proof_hex, ...]}
    """
    try:
        rpc = get_working_rpc(chain, custom_rpc)
    except RuntimeError:
        return []

    w3 = Web3(Web3.HTTPProvider(rpc))

    try:
        contract = Web3.to_checksum_address(contract)
        wallet = Web3.to_checksum_address(wallet)
    except Exception:
        return []

    wei_balance = w3.eth.get_balance(wallet)
    eth_balance = wei_balance / 1e18

    minted = 0
    try:
        data = '0x70a08231' + '000000000000000000000000' + wallet[2:].lower()
        val = _resp_to_int(w3.eth.call({'to': contract, 'data': data}))
        if val is not None:
            minted = val
    except Exception:
        pass

    results = []
    for tier in tiers:
        name = tier.get('name', '')
        price = tier.get('price', 0)
        method_sig = tier.get('methodSig', '')
        status = tier.get('status', 'unknown')
        requires_merkle = tier.get('requiresMerkle', False) or method_sig in MERKLE_SIGS
        is_scheduled = status.startswith('scheduled:')

        eligible = False
        reasons = []

        # ── Scheduled tier: only check balance, skip on-chain simulation ──
        # The contract will reject eth_call before the start time, so we cannot
        # simulate. Instead we trust the balance check and queue the wallet for
        # the countdown. The actual on-chain check happens at mint time.
        if is_scheduled:
            if price == 0 or eth_balance >= price:
                eligible = True
                reasons.append('scheduled — balance ready')
            else:
                reasons.append(f'scheduled — insufficient: {eth_balance:.4f} < {price}')

        # ── Merkle allowlist tier ──
        elif requires_merkle:
            proof = (merkle_proofs or {}).get(name, [])
            if not proof:
                reasons.append('merkle proof required — set MERKLE_PROOF in .env')
            else:
                calldata = build_calldata(method_sig, 1, proof)
                try:
                    w3.eth.call({'from': wallet, 'to': contract, 'data': calldata,
                                 'value': hex(int(round(price * 1e18)))})
                    if price == 0 or eth_balance >= price:
                        eligible = True
                        reasons.append('merkle proof valid')
                    else:
                        reasons.append(f'whitelisted but insufficient: {eth_balance:.4f} < {price}')
                except Exception:
                    reasons.append('merkle proof invalid or not whitelisted')

        # ── Non-public on-chain whitelist ──
        elif 'public' not in name.lower():
            whitelist_sels = [
                '0x3af32abf',  # isWhitelisted(address)
                '0x5c1f0ecf',  # isAllowlisted(address)
                '0x415fc4b3',  # whitelisted(address)
            ]
            for sel in whitelist_sels:
                try:
                    data = sel + '000000000000000000000000' + wallet[2:].lower()
                    if _resp_to_int(w3.eth.call({'to': contract, 'data': data})) == 1:
                        if price == 0 or eth_balance >= price:
                            eligible = True
                            reasons.append('whitelisted')
                        else:
                            reasons.append(f'whitelisted but insufficient: {eth_balance:.4f} < {price}')
                        break
                except Exception:
                    pass

            # Free tier fallback: simulate call
            if not eligible and price == 0 and method_sig:
                calldata = method_sig if method_sig in NO_ARG_SIGS else method_sig + '0' * 63 + '1'
                try:
                    w3.eth.call({'from': wallet, 'to': contract, 'data': calldata, 'value': '0x0'})
                    eligible = True
                    reasons.append('free mint OK')
                except Exception:
                    pass

        # ── Public paid tier ──
        if not eligible and not is_scheduled and 'public' in name.lower():
            if eth_balance >= price:
                eligible = True
                reasons.append(f'balance: {eth_balance:.4f} >= {price}')
            else:
                reasons.append(f'insufficient: {eth_balance:.4f} < {price}')

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
            'maxMint': tier.get('maxMint', 0),
            'requiresMerkle': requires_merkle,
        })

    return results


def estimate_total_cost(contract: str, chain: str, wallet: str, tier: dict,
                        custom_rpc: str = '', quantity: int = 1,
                        merkle_proof: list = None) -> dict:
    """Estimate total cost: mint price (× qty) + gas."""
    try:
        rpc = get_working_rpc(chain, custom_rpc)
    except RuntimeError as e:
        return {'error': str(e)}

    w3 = Web3(Web3.HTTPProvider(rpc))

    try:
        contract = Web3.to_checksum_address(contract)
        wallet = Web3.to_checksum_address(wallet)
    except Exception:
        return {'error': 'Invalid address'}

    price_per_unit = tier.get('price', 0)
    price_wei = int(round(price_per_unit * quantity * 1e18))
    method_sig = tier.get('methodSig', '') or '0x1249c58b'

    calldata = build_calldata(method_sig, quantity, merkle_proof)

    try:
        gas_estimate = w3.eth.estimate_gas({
            'from': wallet, 'to': contract, 'data': calldata, 'value': hex(price_wei)
        })
    except Exception as e:
        return {'error': f'estimate gas failed: {str(e)[:60]}'}

    try:
        fee_history = rpc_retry(lambda: w3.eth.fee_history(1, 'latest', [25]))
        base_fee = fee_history['baseFeePerGas'][-1]
        rewards = fee_history.get('reward', [])
        max_priority = rewards[-1][0] if rewards and rewards[-1] else 1_000_000_000
        max_fee = base_fee + max_priority
    except Exception:
        try:
            max_fee = w3.eth.gas_price
        except Exception:
            max_fee = 10_000_000_000

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
