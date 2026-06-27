"""Build tx, sign, countdown, execute, wait receipt, gas bump."""

import time
import sys
from web3 import Web3, Account

from .config import get_working_rpc, get_private_key, get_max_gas_wei, rpc_retry
from .detect import build_calldata

TX_STUCK_TIMEOUT = 45
GAS_BUMP_FACTOR = 1.15
MAX_BUMP_ATTEMPTS = 3

_PAUSED_SELS = ['0x5c975abb']           # paused()
_TOTAL_SUPPLY_SEL = '0x18160ddd'        # totalSupply()
_MAX_SUPPLY_SELS = ['0xd5abeb01', '0x32cb6b0c']  # maxSupply(), MAX_SUPPLY()


def get_wallet() -> tuple:
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


def wait_for_countdown(target_ts: int, tier_name: str) -> bool:
    """Loop countdown to 0. Return False if user cancels."""
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
            pct = min(20, int((initial - remaining) / max(initial, 1) * 20))
            bar = '█' * pct + '░' * (20 - pct)
            sys.stdout.write(f'\r   ⏱  {_fmt_duration(remaining)}  [{bar}]')
            sys.stdout.flush()
            time.sleep(1)
    except KeyboardInterrupt:
        print('\n   ✕ Cancelled by user')
        return False
    print()
    return True


def _fmt_duration(secs: int) -> str:
    if secs < 0:
        secs = 0
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f'{h:02d}:{m:02d}:{s:02d}'


def _bump_gas(tx: dict, factor: float = GAS_BUMP_FACTOR) -> dict:
    bumped = dict(tx)
    if 'maxFeePerGas' in tx:
        bumped['maxFeePerGas'] = int(tx['maxFeePerGas'] * factor)
        bumped['maxPriorityFeePerGas'] = int(tx['maxPriorityFeePerGas'] * factor)
    elif 'gasPrice' in tx:
        bumped['gasPrice'] = int(tx['gasPrice'] * factor)
    return bumped


def _eth_call_int(w3: Web3, contract: str, selector: str) -> int | None:
    try:
        resp = w3.eth.call({'to': contract, 'data': selector})
        if isinstance(resp, (bytes, bytearray)):
            resp = '0x' + resp.hex()
        if not resp or resp in ('0x', '0x0'):
            return None
        return int(resp, 16)
    except Exception:
        return None


def check_contract_ready(w3: Web3, contract: str) -> dict:
    """Check paused + sold-out state before minting.

    Returns {'ok': True} or {'ok': False, 'reason': str}.
    """
    for sel in _PAUSED_SELS:
        if _eth_call_int(w3, contract, sel) == 1:
            return {'ok': False, 'reason': 'contract is paused'}

    total = _eth_call_int(w3, contract, _TOTAL_SUPPLY_SEL)
    if total is not None:
        for sel in _MAX_SUPPLY_SELS:
            max_supply = _eth_call_int(w3, contract, sel)
            if max_supply and max_supply > 0 and total >= max_supply:
                return {'ok': False, 'reason': f'sold out ({total}/{max_supply})'}

    return {'ok': True}


def _get_current_gas_wei(w3: Web3) -> int:
    """Return current effective gas price in wei."""
    try:
        fh = rpc_retry(lambda: w3.eth.fee_history(1, 'latest', [50]))
        base = fh['baseFeePerGas'][-1]
        rewards = fh.get('reward', [])
        priority = rewards[-1][0] if rewards and rewards[-1] else 1_000_000_000
        return base + priority
    except Exception:
        try:
            return w3.eth.gas_price
        except Exception:
            return 10_000_000_000


def _wait_with_bump(w3: Web3, acct, tx: dict, tx_hash, receipt_timeout: int = 180) -> dict:
    """Wait for receipt. Bump gas and resubmit same nonce if stuck."""
    send_time = time.time()
    deadline = send_time + receipt_timeout
    bump_count = 0
    current_hash = tx_hash

    while time.time() < deadline:
        try:
            receipt = w3.eth.get_transaction_receipt(current_hash)
            if receipt is not None:
                return receipt
        except Exception:
            pass

        elapsed = time.time() - send_time
        if elapsed > TX_STUCK_TIMEOUT * (bump_count + 1) and bump_count < MAX_BUMP_ATTEMPTS:
            tx = _bump_gas(tx)
            bump_count += 1
            try:
                signed = acct.sign_transaction(tx)
                current_hash = rpc_retry(lambda: w3.eth.send_raw_transaction(signed.raw_transaction))
                print(f'\n   ⚡ Gas bumped (attempt {bump_count}): {current_hash.hex()[:18]}...')
            except Exception:
                pass

        time.sleep(2)

    try:
        return w3.eth.wait_for_transaction_receipt(current_hash, timeout=30, poll_latency=2)
    except Exception as e:
        raise TimeoutError(f'Receipt timeout after {receipt_timeout}s') from e


def execute_mint(contract: str, chain: str, tier: dict, custom_rpc: str = '',
                 quantity: int = 1, private_key_override: str = '',
                 gas_params: dict = None, merkle_proof: list = None) -> dict:
    """Build, sign, and send mint tx. Includes RPC fallback, gas guard, sold-out check."""
    try:
        rpc = get_working_rpc(chain, custom_rpc)
    except RuntimeError as e:
        return {'status': 'error', 'message': str(e)}

    w3 = Web3(Web3.HTTPProvider(rpc))

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

    try:
        contract = Web3.to_checksum_address(contract)
    except Exception:
        return {'status': 'error', 'message': 'Invalid contract address'}

    readiness = check_contract_ready(w3, contract)
    if not readiness['ok']:
        return {'status': 'error', 'message': readiness['reason']}

    method_sig = tier.get('methodSig', '0x1249c58b')
    price_per_unit = tier.get('price', 0)
    price_wei = int(round(price_per_unit * quantity * 1e18))

    calldata = build_calldata(method_sig, quantity, merkle_proof)

    balance_wei = w3.eth.get_balance(wallet)
    if balance_wei < price_wei:
        return {'status': 'error',
                'message': f'Insufficient balance: {balance_wei/1e18:.6f} < {price_wei/1e18}'}

    try:
        gas_estimate = rpc_retry(lambda: w3.eth.estimate_gas({
            'from': wallet, 'to': contract, 'data': calldata, 'value': hex(price_wei)
        }))
    except Exception as e:
        return {'status': 'error', 'message': f'estimate gas: {str(e)[:80]}'}

    nonce = w3.eth.get_transaction_count(wallet, 'pending')

    tx: dict = {
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
        try:
            fee_history = rpc_retry(lambda: w3.eth.fee_history(1, 'latest', [25]))
            base_fee = fee_history['baseFeePerGas'][-1]
            rewards = fee_history.get('reward', [])
            max_priority = rewards[-1][0] if rewards and rewards[-1] else 1_000_000_000
            tx['maxFeePerGas'] = base_fee + max_priority
            tx['maxPriorityFeePerGas'] = max_priority
        except Exception:
            tx['gasPrice'] = w3.eth.gas_price

    # Gas guard
    max_gas_wei = get_max_gas_wei()
    if max_gas_wei:
        effective_gas = tx.get('maxFeePerGas') or tx.get('gasPrice', 0)
        if effective_gas > max_gas_wei:
            return {
                'status': 'error',
                'message': (
                    f'Gas too high: {effective_gas/1e9:.1f} Gwei > '
                    f'MAX_GAS_GWEI={max_gas_wei/1e9:.1f}. Aborted.'
                ),
            }

    try:
        signed = acct.sign_transaction(tx)
        tx_hash = rpc_retry(lambda: w3.eth.send_raw_transaction(signed.raw_transaction))
        print(f'\n   📤 Tx sent: {tx_hash.hex()[:18]}...{tx_hash.hex()[-6:]}')
    except Exception as e:
        return {'status': 'error', 'message': f'send tx: {str(e)[:80]}'}

    try:
        receipt = _wait_with_bump(w3, acct, tx, tx_hash)
    except TimeoutError as e:
        return {'status': 'pending', 'tx_hash': tx_hash.hex(), 'message': str(e)}

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
    return {'status': 'failed', 'tx_hash': receipt['transactionHash'].hex(),
            'message': 'Transaction reverted'}
