"""Unit tests: config.py"""
# ruff: noqa: E402
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from src.config import (
    CHAINS, CHAIN_MAP, get_rpc, get_private_key,
    resolve_chain, rpc_retry
)

errors = 0

def check(name, cond, detail=""):
    global errors
    if cond:
        print(f"  ✅ {name}")
    else:
        print(f"  ❌ {name} — {detail}")
        errors += 1

# ── CHAINS ──
check("CHAINS: 6 entries", len(CHAINS) == 6)
for k in ['ethereum','base','optimism','arbitrum','polygon','bsc']:
    check(f"CHAINS[{k}]: has id", 'id' in CHAINS[k])
    check(f"CHAINS[{k}]: has rpc", 'rpc' in CHAINS[k])
    check(f"CHAINS[{k}]: has currency", 'currency' in CHAINS[k])
    check(f"CHAINS[{k}]: has explorer", 'explorer' in CHAINS[k])

# Chain IDs
check("ethereum id=1", CHAINS['ethereum']['id'] == 1)
check("base id=8453", CHAINS['base']['id'] == 8453)
check("optimism id=10", CHAINS['optimism']['id'] == 10)
check("arbitrum id=42161", CHAINS['arbitrum']['id'] == 42161)
check("polygon id=137", CHAINS['polygon']['id'] == 137)
check("bsc id=56", CHAINS['bsc']['id'] == 56)

# Currencies
check("polygon currency=MATIC", CHAINS['polygon']['currency'] == 'MATIC')
check("bsc currency=BNB", CHAINS['bsc']['currency'] == 'BNB')
check("other chains currency=ETH", CHAINS['ethereum']['currency'] == 'ETH')

# ── CHAIN_MAP ──
check("CHAIN_MAP: eth→ethereum", CHAIN_MAP['eth'] == 'ethereum')
check("CHAIN_MAP: op→optimism", CHAIN_MAP['op'] == 'optimism')
check("CHAIN_MAP: arb→arbitrum", CHAIN_MAP['arb'] == 'arbitrum')
check("CHAIN_MAP: matic→polygon", CHAIN_MAP['matic'] == 'polygon')
check("CHAIN_MAP: binance→bsc", CHAIN_MAP['binance'] == 'bsc')
check("CHAIN_MAP: base→base", CHAIN_MAP['base'] == 'base')

# ── resolve_chain ──
check("resolve_chain('eth')→ethereum", resolve_chain('eth') == 'ethereum')
check("resolve_chain('ETH')→ethereum", resolve_chain('ETH') == 'ethereum')
check("resolve_chain('  eth  ')→ethereum", resolve_chain('  eth  ') == 'ethereum')
check("resolve_chain('polygon')→polygon", resolve_chain('polygon') == 'polygon')
check("resolve_chain('invalid')→None", resolve_chain('invalid') is None)
check("resolve_chain('')→None", resolve_chain('') is None)

# ── get_rpc ──
rpc_eth = get_rpc('ethereum')
check("get_rpc(ethereum)=default", rpc_eth == CHAINS['ethereum']['rpc'])
check("get_rpc(bsc)=bsc-dataseed", 'bsc-dataseed' in get_rpc('bsc'))
check("get_rpc(nonexistent)=''", get_rpc('nonexistent') == '')

# ── get_private_key ──
pk = get_private_key()
check("private key starts with 0x", pk.startswith('0x'))
check("private key length=66", len(pk) == 66)

# ── rpc_retry ──
check("rpc_retry(success)=42", rpc_retry(lambda: 42) == 42)

call_count = [0]
def fail_twice():
    call_count[0] += 1
    if call_count[0] < 3:
        raise ConnectionError("transient")
    return "ok"
check("rpc_retry(retry+success) ok", rpc_retry(fail_twice, max_attempts=3, delay=0.01) == "ok")

def always_fail():
    raise ValueError("permanent")
try:
    rpc_retry(always_fail, max_attempts=2, delay=0.01)
    check("rpc_retry(exhaustion) raises", False, "should have raised")
except ValueError:
    check("rpc_retry(exhaustion) raises ValueError", True)

# ── Summary ──
print(f"\n{'='*50}")
print(f"config.py: {errors} failures" + (" ✅" if errors == 0 else " ❌"))
print(f"{'='*50}")
sys.exit(errors)
