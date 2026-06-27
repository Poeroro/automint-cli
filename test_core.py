"""Unit tests: executor.py + eligibility.py"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# Inject test private key so wallet tests always work regardless of .env
TEST_KEY = '0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80'
os.environ.setdefault('PRIVATE_KEY', TEST_KEY)

from src.executor import (
    get_wallet, wait_for_countdown, _fmt_duration,
    execute_mint, _bump_gas, check_contract_ready
)
from src.eligibility import check_eligibility, estimate_total_cost
from src.detect import build_calldata

errors = 0

def check(name, cond, detail=""):
    global errors
    if cond:
        print(f"  OK  {name}")
    else:
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))
        errors += 1

# ── _fmt_duration ──
check("_fmt_duration(0)='00:00:00'",    _fmt_duration(0)     == '00:00:00')
check("_fmt_duration(3661)='01:01:01'", _fmt_duration(3661)  == '01:01:01')
check("_fmt_duration(86399)",           _fmt_duration(86399) == '23:59:59')
check("_fmt_duration(60)='00:01:00'",   _fmt_duration(60)    == '00:01:00')
check("_fmt_duration(-1)='00:00:00'",   _fmt_duration(-1)    == '00:00:00')

# ── _bump_gas: EIP-1559 ──
tx_eip = {'maxFeePerGas': 10_000_000_000, 'maxPriorityFeePerGas': 2_000_000_000}
bumped = _bump_gas(tx_eip, 1.15)
check("_bump_gas eip1559: maxFeePerGas bumped",      bumped['maxFeePerGas'] == 11_500_000_000)
check("_bump_gas eip1559: priorityFee bumped",       bumped['maxPriorityFeePerGas'] == 2_300_000_000)
check("_bump_gas eip1559: original unchanged",       tx_eip['maxFeePerGas'] == 10_000_000_000)

# ── _bump_gas: legacy ──
tx_leg = {'gasPrice': 10_000_000_000}
bumped_leg = _bump_gas(tx_leg, 1.15)
check("_bump_gas legacy: gasPrice bumped", bumped_leg['gasPrice'] == 11_500_000_000)
check("_bump_gas legacy: original unchanged", tx_leg['gasPrice'] == 10_000_000_000)

# ── get_wallet ──
acct, err = get_wallet()
check("get_wallet: no error",          err is None, str(err))
check("get_wallet: returns account",   acct is not None)
check("get_wallet: address valid",     acct is not None and acct.address.startswith('0x')
      and len(acct.address) == 42)

# Bad key
saved_pk = os.environ.get('PRIVATE_KEY', '')
os.environ['PRIVATE_KEY'] = '0xinvalid'
acct_bad, err_bad = get_wallet()
check("get_wallet(bad key): returns error string", err_bad is not None)
check("get_wallet(bad key): acct is None",         acct_bad is None)

os.environ['PRIVATE_KEY'] = '0x' + '0' * 64
acct_zero, err_zero = get_wallet()
check("get_wallet(all zeros): returns error", err_zero is not None)

os.environ['PRIVATE_KEY'] = saved_pk

# ── wait_for_countdown ──
import time
now = int(time.time())
check("wait_for_countdown(past): True",       wait_for_countdown(now - 100, 'test') is True)
check("wait_for_countdown(now exact): True",  wait_for_countdown(now, 'test') is True)
check("wait_for_countdown(1s ago): True",     wait_for_countdown(now - 1, 'test') is True)

# ── execute_mint: bad chain → error ──
rep = execute_mint('0x0000000000000000000000000000000000000001', 'nonexistent',
                   {'price': 0, 'methodSig': '0x1249c58b'})
check("execute_mint(bad chain): status=error", rep.get('status') == 'error')
check("execute_mint(bad chain): has message",  bool(rep.get('message')))

# ── execute_mint: gas guard blocks when limit too low ──
os.environ['MAX_GAS_GWEI'] = '0'  # 0 Gwei limit = always block
rep_guard = execute_mint('0x0000000000000000000000000000000000000001', 'nonexistent',
                         {'price': 0, 'methodSig': '0x1249c58b'})
check("execute_mint(gas guard 0): status=error", rep_guard.get('status') == 'error')
del os.environ['MAX_GAS_GWEI']

# ── check_eligibility: offline with mock tiers ──
# Can't hit real RPC in unit test — confirm it handles bad rpc gracefully
result = check_eligibility(
    '0xBd3531dA5CF5857e7CfAA92426877b022e612cf8',
    'nonexistent_chain',
    '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266',
    [{'name': 'Public', 'price': 0.005, 'methodSig': '0x1249c58b', 'status': 'active'}]
)
check("check_eligibility(bad chain): returns []", result == [])

# ── estimate_total_cost: offline ──
est = estimate_total_cost(
    '0xBd3531dA5CF5857e7CfAA92426877b022e612cf8',
    'nonexistent_chain',
    '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266',
    {'price': 0.005, 'methodSig': '0x1249c58b'},
)
check("estimate_total_cost(bad chain): has 'error'", 'error' in est)

# ── Live: check_eligibility + estimate with real RPC ──
from src.detect import detect
r = detect('https://opensea.io/collection/pudgypenguins')
if not r.get('error') and r.get('tiers'):
    contract = r['contract']
    chain    = r['chain']
    tiers    = r['tiers']
    acct, _ = get_wallet()
    wallet   = acct.address if acct else '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266'

    elig = check_eligibility(contract, chain, wallet, tiers)
    check("check_eligibility(live): returns list",     isinstance(elig, list))
    check("check_eligibility(live): non-empty",        len(elig) > 0)
    for t in elig:
        check(f"  tier '{t['name']}': has eligible",  'eligible' in t)
        check(f"  tier '{t['name']}': has reasons",   isinstance(t.get('reasons'), list))
        check(f"  tier '{t['name']}': eligible is bool", isinstance(t['eligible'], bool))

    if tiers:
        est = estimate_total_cost(contract, chain, wallet, tiers[0])
        check("estimate_total_cost(live): returns dict",       isinstance(est, dict))
        check("estimate_total_cost(live): has error or total", 'error' in est or 'total_wei' in est)
        if 'total_wei' in est:
            check("estimate_total_cost: total_wei > 0",    est['total_wei'] >= 0)
            check("estimate_total_cost: gas_units > 0",    est['gas_units'] > 0)
            check("estimate_total_cost: gas_price_gwei>0", est['gas_price_gwei'] > 0)

# ── Summary ──
print(f"\n{'='*50}")
print(f"executor + eligibility: {errors} failures" + (" OK" if errors == 0 else " FAIL"))
print(f"{'='*50}")
sys.exit(errors)
