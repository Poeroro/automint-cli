"""Build tx, sign, countdown, execute, wait receipt."""

import time
import sys
from web3 import Web3, Account

from .config import get_rpc, get_private_key, rpc_retry

def get_wallet() -> tuple:
    """Load wallet dari private key env."""
    pk = get_private_key()
    if not pk:
        return None, 'PRIVATE_KEY not set in .env'
    if pk == '0x' + '0' * 64:
        return None, 'PRIVATE_KEY is all zeros — use real key'
    try:
        acct = Account.from_key(pk)
        return acct, None
    except Exception as e:
        return None, f'Invalid private key: {str(e)[:40]}'


def wait_for_countdown(target_ts: int, tier_name: str):
    """Loop countdown sampai 0, return False kalo user cancel."""
    remaining = target_ts - int(time.time())
    if remaining <= 0:
        return True

    print(f'\n⏳ {tier_name} opens in {_fmt_duration(remaining)}')
    print('   [Press Ctrl+C to cancel]')
    try:
        initial = remaining
        while remaining > 0:
            remaining = target_ts - int(time.time())
            if remaining <= 0:
                break
            pct = int((initial - remaining) / max(initial, 1) * 20)
            pct = max(0, min(20, pct))
            bar = '█' * pct + '░' * (20 - pct)
            sys.stdout.write(f'\r   ⏱  {_fmt_duration(remaining)}  [{bar}]')
            sys.stdout.flush()
            time.sleep(1)
    except KeyboardInterrupt:
        print('\n   ✕ Cancelled by user')
        return False
    print()  # newline after countdown ends
    return True


def _fmt_duration(secs: int) -> str:
    if secs < 0:
        secs = 0
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f'{h:02d}:{m:02d}:{s:02d}'


def execute_mint(contract: str, chain: str, tier: dict, custom_rpc: str = '',
                 quantity: int = 1, private_key_override: str = '',
                 gas_params: dict = None) -> dict:
    """Build tx, sign, send, wait receipt. Return report.
       private_key_override — untuk multi-account, pake key tertentu.
       gas_params — dari show_gas_menu: {type:'eip1559', max_fee, priority_fee}
                    or {type:'legacy', gas_price}. Kalo None, auto."""
    rpc = custom_rpc or get_rpc(chain)
    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        return {'status': 'error', 'message': 'RPC not connected'}

    # Pake key tertentu (multi-account), atau default dari env
    if private_key_override:
        try:
            acct = Account.from_key(private_key_override)
        except Exception:
            return {'status': 'error', 'message': 'Invalid private key'}
    else:
        acct, err = get_wallet()
        if err:
            return {'status': 'error', 'message': err}

    wallet = acct.address

    # Checksum contract
    try:
        contract = Web3.to_checksum_address(contract)
    except Exception:
        return {'status': 'error', 'message': 'Invalid contract address'}

    # Build calldata
    method_sig = tier.get('methodSig', '0x1249c58b')
    price_per_unit = tier.get('price', 0)
    price_wei = int(price_per_unit * quantity * 1e18)

    # Encode quantity ke uint256 calldata
    qty_hex = hex(quantity)[2:].zfill(64)
    calldata = method_sig + qty_hex

    # Cek balance dulu
    balance_wei = w3.eth.get_balance(wallet)
    if balance_wei < price_wei:
        return {'status': 'error', 'message': f'Insufficient balance: {balance_wei/1e18:.6f} < {price_wei/1e18}'}

    # Gas
    try:
        gas_estimate = rpc_retry(lambda: w3.eth.estimate_gas({
            'from': wallet, 'to': contract, 'data': calldata, 'value': hex(price_wei)
        }))
    except Exception as e:
        return {'status': 'error', 'message': f'estimate gas: {str(e)[:80]}'}

    # Nonce — pake 'pending' biar gak tabrakan kalo ada tx lain
    nonce = w3.eth.get_transaction_count(wallet, 'pending')

    tx = {
        'to': contract,
        'data': calldata,
        'value': price_wei,
        'gas': gas_estimate,
        'nonce': nonce,
        'chainId': w3.eth.chain_id,
    }

    if gas_params and gas_params.get('type') == 'eip1559':
        tx['maxFeePerGas'] = gas_params['max_fee']
        tx['maxPriorityFeePerGas'] = gas_params['priority_fee']
    elif gas_params and gas_params.get('type') == 'legacy':
        tx['gasPrice'] = gas_params['gas_price']
    else:
        # Auto fallback
        try:
            fee_history = rpc_retry(lambda: w3.eth.fee_history(1, 'latest', [25]))
            base_fee = fee_history['baseFeePerGas'][-1]
            max_priority = fee_history['reward'][-1][0] if fee_history['reward'] else 1000000000
            tx['maxFeePerGas'] = base_fee + max_priority
            tx['maxPriorityFeePerGas'] = max_priority
        except Exception:
            tx['gasPrice'] = w3.eth.gas_price

    # Sign + send
    try:
        signed = acct.sign_transaction(tx)
        tx_hash = rpc_retry(lambda: w3.eth.send_raw_transaction(signed.raw_transaction))
        print(f'\n   📤 Tx sent: {tx_hash.hex()[:18]}...{tx_hash.hex()[-6:]}')
    except Exception as e:
        return {'status': 'error', 'message': f'send tx: {str(e)[:80]}'}

    # Wait receipt
    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120, poll_latency=2)
    except Exception as e:
        return {'status': 'pending', 'tx_hash': tx_hash.hex(), 'message': f'Waiting receipt timeout: {str(e)[:60]}'}

    if receipt['status'] == 1:
        gas_used = receipt['gasUsed']
        gas_price = receipt.get('effectiveGasPrice', tx.get('maxFeePerGas', tx.get('gasPrice', 0)))
        gas_cost = gas_used * gas_price / 1e18
        return {
            'status': 'success',
            'tx_hash': receipt['transactionHash'].hex(),
            'block': receipt['blockNumber'],
            'gas_used': gas_used,
            'gas_price_gwei': gas_price / 1e9,
            'gas_cost_eth': gas_cost,
            'total_cost_eth': price_wei / 1e18 + gas_cost,
        }
    else:
        return {'status': 'failed', 'tx_hash': receipt['transactionHash'].hex(), 'message': 'Transaction reverted'}
