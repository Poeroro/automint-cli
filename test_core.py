"""Unit tests: eligibility.py + executor.py + display.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from web3 import Web3
from src.eligibility import check_eligibility, estimate_total_cost
from src.executor import get_wallet, wait_for_countdown, _fmt_duration, execute_mint
from src.config import get_rpc

errors = 0

def check(name, cond, detail=""):
    global errors
    if cond:
        print(f"  ✅ {name}")
    else:
        print(f"  ❌ {name} — {detail}")
        errors += 1

# ── _fmt_duration ──
check("_fmt_duration(0)=00:00:00", _fmt_duration(0) == "00:00:00")
check("_fmt_duration(3661)=01:01:01", _fmt_duration(3661) == "01:01:01")
check("_fmt_duration(86399)=23:59:59", _fmt_duration(86399) == "23:59:59")
check("_fmt_duration(60)=00:01:00", _fmt_duration(60) == "00:01:00")

# ── get_wallet (requires .env) ──
rpc = get_rpc('ethereum')
w3 = Web3(Web3.HTTPProvider(rpc))
acct, err = get_wallet(w3)
check("get_wallet: no error", err is None, str(err))
check("get_wallet: returns account", acct is not None)
check("get_wallet: address valid", acct is not None and acct.address.startswith('0x') and len(acct.address) == 42)

# Bad private key
import os as _os
saved = _os.environ.get('PRIVATE_KEY', '')
_os.environ['PRIVATE_KEY'] = '0xinvalid'
from src.config import get_private_key as _gpk
_pk = _gpk()
check("get_private_key(bad) still returns 0x...", _pk.startswith('0x'))
_os.environ['PRIVATE_KEY'] = ''
from src.config import get_private_key as _gpk2
_pk2 = _gpk2()
check("get_private_key(empty) starts with 0x", _pk2.startswith('0x'))
# Restore
_os.environ['PRIVATE_KEY'] = saved

# ── check_eligibility with Pudgy Penguins ──
from src.detect import detect
r = detect("https://opensea.io/collection/pudgypenguins")
if r.get('contract'):
    wallet = acct.address
    tiers = r.get('tiers', [])
    chain = r.get('chain', 'ethereum')
    elig = check_eligibility(r['contract'], chain, wallet, tiers)
    check("check_eligibility returns list", isinstance(elig, list))
    check("check_eligibility has entries", len(elig) > 0)
    for t in elig:
        check(f"  tier '{t['name']}': has 'eligible' key", 'eligible' in t)
        check(f"  tier '{t['name']}': has 'reasons' key", 'reasons' in t)
        check(f"  tier '{t['name']}': has 'price' key", 'price' in t)
        check(f"  tier '{t['name']}': has 'status' key", 'status' in t)
    
    # estimate_total_cost — already tested that it returns error for dummy wallet
    est = estimate_total_cost(r['contract'], chain, wallet, tiers[0] if tiers else {'price':0, 'methodSig':'0x1249c58b'})
    check("estimate_total_cost returns dict", isinstance(est, dict))
    check("estimate_total_cost has 'error' or 'total_wei'", 'error' in est or 'total_wei' in est)

# ── execute_mint: bad chain ──
rep = execute_mint("0x0", "nonexistent", {'price':0, 'methodSig':'0x1249c58b'})
check("execute_mint(bad chain) returns error", rep.get('status') == 'error', str(rep))

# ── wait_for_countdown ──
import time
now = int(time.time())
check("wait_for_countdown(past) returns True", wait_for_countdown(now - 100, "test") is True)
check("wait_for_countdown(now) returns True", wait_for_countdown(now, "test") is True)

# ── Summary ──
print(f"\n{'='*50}")
print(f"eligibility + executor: {errors} failures" + (" ✅" if errors == 0 else " ❌"))
print(f"{'='*50}")
sys.exit(errors)
