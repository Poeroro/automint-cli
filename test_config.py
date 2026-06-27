"""Unit tests: config.py"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from src.config import (
    CHAINS, CHAIN_MAP, RPC_FALLBACKS, get_rpc, get_working_rpc,
    get_private_key, get_all_wallets, get_max_gas_wei, resolve_chain, rpc_retry
)

errors = 0

def check(name, cond, detail=""):
    global errors
    if cond:
        print(f"  OK  {name}")
    else:
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))
        errors += 1

# ── CHAINS ──
check("CHAINS: 6 entries", len(CHAINS) == 6)
for k in ['ethereum', 'base', 'optimism', 'arbitrum', 'polygon', 'bsc']:
    check(f"CHAINS[{k}]: has id",       'id'       in CHAINS[k])
    check(f"CHAINS[{k}]: has rpc",      'rpc'      in CHAINS[k])
    check(f"CHAINS[{k}]: has currency", 'currency' in CHAINS[k])
    check(f"CHAINS[{k}]: has explorer", 'explorer' in CHAINS[k])

check("ethereum id=1",       CHAINS['ethereum']['id'] == 1)
check("base     id=8453",    CHAINS['base']['id'] == 8453)
check("optimism id=10",      CHAINS['optimism']['id'] == 10)
check("arbitrum id=42161",   CHAINS['arbitrum']['id'] == 42161)
check("polygon  id=137",     CHAINS['polygon']['id'] == 137)
check("bsc      id=56",      CHAINS['bsc']['id'] == 56)

check("polygon  currency=MATIC", CHAINS['polygon']['currency'] == 'MATIC')
check("bsc      currency=BNB",   CHAINS['bsc']['currency'] == 'BNB')
check("ethereum currency=ETH",   CHAINS['ethereum']['currency'] == 'ETH')

# ── RPC_FALLBACKS ──
for chain in ['ethereum', 'base', 'optimism', 'arbitrum', 'polygon', 'bsc']:
    check(f"RPC_FALLBACKS[{chain}]: >= 2 entries", len(RPC_FALLBACKS.get(chain, [])) >= 2)
    for url in RPC_FALLBACKS[chain]:
        check(f"  fallback starts with https", url.startswith('https://'), url)

# ── CHAIN_MAP ──
check("resolve eth->ethereum",  CHAIN_MAP['eth']     == 'ethereum')
check("resolve op->optimism",   CHAIN_MAP['op']      == 'optimism')
check("resolve arb->arbitrum",  CHAIN_MAP['arb']     == 'arbitrum')
check("resolve matic->polygon", CHAIN_MAP['matic']   == 'polygon')
check("resolve binance->bsc",   CHAIN_MAP['binance'] == 'bsc')
check("resolve base->base",     CHAIN_MAP['base']    == 'base')

# ── resolve_chain ──
check("resolve_chain('eth')",        resolve_chain('eth')       == 'ethereum')
check("resolve_chain('ETH')",        resolve_chain('ETH')       == 'ethereum')
check("resolve_chain('  eth  ')",    resolve_chain('  eth  ')   == 'ethereum')
check("resolve_chain('polygon')",    resolve_chain('polygon')   == 'polygon')
check("resolve_chain('invalid')=None", resolve_chain('invalid') is None)
check("resolve_chain('')=None",        resolve_chain('')         is None)

# ── get_rpc ──
check("get_rpc(ethereum)=publicnode", 'publicnode' in get_rpc('ethereum') or 'ethereum' in get_rpc('ethereum'))
check("get_rpc(bsc)=bsc-dataseed",    'bsc-dataseed' in get_rpc('bsc'))
check("get_rpc(nonexistent)=''",      get_rpc('nonexistent') == '')

# env override
os.environ['RPC_ETH'] = 'https://custom-rpc.test'
check("get_rpc env override works", get_rpc('ethereum') == 'https://custom-rpc.test')
del os.environ['RPC_ETH']
check("get_rpc env override removed", get_rpc('ethereum') != 'https://custom-rpc.test')

# ── get_private_key ──
saved_pk = os.environ.get('PRIVATE_KEY', '')
os.environ['PRIVATE_KEY'] = ''
check("get_private_key(empty)=''", get_private_key() == '')

os.environ['PRIVATE_KEY'] = 'abcdef' + '0' * 58  # without 0x prefix
pk = get_private_key()
check("get_private_key: prepends 0x",  pk.startswith('0x'))
check("get_private_key: length=66", len(pk) == 66)

os.environ['PRIVATE_KEY'] = '0x' + 'ab' * 32
pk2 = get_private_key()
check("get_private_key: keeps 0x prefix", pk2.startswith('0x'))
check("get_private_key: no double 0x",    not pk2.startswith('0x0x'))

os.environ['PRIVATE_KEY'] = saved_pk

# ── get_max_gas_wei ──
saved_max = os.environ.get('MAX_GAS_GWEI', '')
os.environ['MAX_GAS_GWEI'] = ''
check("get_max_gas_wei(unset)=None", get_max_gas_wei() is None)

os.environ['MAX_GAS_GWEI'] = '50'
check("get_max_gas_wei(50)=50e9", get_max_gas_wei() == 50_000_000_000)

os.environ['MAX_GAS_GWEI'] = '0.5'
check("get_max_gas_wei(0.5 Gwei)=500000000", get_max_gas_wei() == 500_000_000)

os.environ['MAX_GAS_GWEI'] = 'bad'
check("get_max_gas_wei(bad)=None", get_max_gas_wei() is None)

os.environ['MAX_GAS_GWEI'] = saved_max

# ── get_all_wallets ──
saved_pk = os.environ.get('PRIVATE_KEY', '')
saved_pks = os.environ.get('PRIVATE_KEYS', '')

os.environ['PRIVATE_KEY'] = ''
os.environ['PRIVATE_KEYS'] = ''
check("get_all_wallets(none)=[]", get_all_wallets() == [])

# Hardhat test key — well-known, safe to use in tests
test_key = '0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80'
os.environ['PRIVATE_KEY'] = test_key
wallets = get_all_wallets()
check("get_all_wallets(single): len=1",           len(wallets) == 1)
check("get_all_wallets(single): has address",     'address' in wallets[0])
check("get_all_wallets(single): has private_key", 'private_key' in wallets[0])
check("get_all_wallets(single): address checksummed",
      wallets[0]['address'].startswith('0x') and len(wallets[0]['address']) == 42)

test_key2 = '0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d'
os.environ['PRIVATE_KEYS'] = f'{test_key},{test_key2}'
os.environ['PRIVATE_KEY'] = ''
wallets_multi = get_all_wallets()
check("get_all_wallets(multi): len=2", len(wallets_multi) == 2)

os.environ['PRIVATE_KEYS'] = f'{test_key},INVALID_KEY,{test_key2}'
wallets_skip = get_all_wallets()
check("get_all_wallets: skips invalid key", len(wallets_skip) == 2)

os.environ['PRIVATE_KEY'] = saved_pk
os.environ['PRIVATE_KEYS'] = saved_pks

# ── rpc_retry ──
check("rpc_retry(success)=42", rpc_retry(lambda: 42) == 42)

call_count = [0]
def fail_twice():
    call_count[0] += 1
    if call_count[0] < 3:
        raise ConnectionError("transient")
    return "ok"
check("rpc_retry(retry then success)", rpc_retry(fail_twice, max_attempts=3, delay=0.01) == "ok")

def always_fail():
    raise ValueError("permanent")
try:
    rpc_retry(always_fail, max_attempts=2, delay=0.01)
    check("rpc_retry(exhausted): raises", False, "should have raised")
except ValueError:
    check("rpc_retry(exhausted): raises ValueError", True)

# ── Summary ──
print(f"\n{'='*50}")
print(f"config.py: {errors} failures" + (" OK" if errors == 0 else " FAIL"))
print(f"{'='*50}")
sys.exit(errors)
