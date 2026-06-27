"""Integration tests: automint.py entry points + cross-module flow"""
import sys, os, time, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

TEST_KEY = '0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80'
os.environ.setdefault('PRIVATE_KEY', TEST_KEY)

import automint
from web3 import Web3
from src.config import CHAINS, get_working_rpc
from src.detect import detect
from src.notify import notify, notify_mint_result
from src.merkle import fetch_merkle_proof

errors = 0

def check(name, cond, detail=""):
    global errors
    if cond:
        print(f"  OK  {name}")
    else:
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))
        errors += 1

# ── check_env_file: .env exists ──
if os.path.exists('.env'):
    try:
        automint.check_env_file()
        check("check_env_file(.env exists): no exit", True)
    except SystemExit:
        check("check_env_file(.env exists): unexpected exit", False)
    except Exception as e:
        check("check_env_file(.env exists): no exception", False, str(e))
else:
    check("check_env_file(.env exists): skipped (no .env)", True)

# check_env_file: no .env → exit
if os.path.exists('.env'):
    os.rename('.env', '.env.bak')
    try:
        automint.check_env_file()
        check("check_env_file(no .env): should exit", False)
    except SystemExit:
        check("check_env_file(no .env): exits correctly", True)
    except Exception as e:
        check("check_env_file(no .env): exit not exception", False, str(e))
    finally:
        os.rename('.env.bak', '.env')

# ── append_log ──
entry = {
    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
    'wallet': '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266',
    'chain': 'ethereum', 'contract': '0x1234',
    'tier': 'Public', 'price': 0, 'quantity': 1,
    'status': 'dry_run', 'tx_hash': '',
}
try:
    automint.append_log(entry)
    check("append_log: no exception", True)
    if os.path.exists('automint.log'):
        with open('automint.log') as f:
            lines = f.read().strip().split('\n')
        last = json.loads(lines[-1])
        check("append_log: valid JSON line",    isinstance(last, dict))
        check("append_log: has timestamp",       'timestamp' in last)
        check("append_log: has chain",           'chain' in last)
        check("append_log: has status",          'status' in last)
except Exception as e:
    check("append_log: no exception", False, str(e))

automint.append_log({'minimal': True})
check("append_log(minimal dict): no crash", True)

# ── parse_args ──
sys.argv = ['automint.py', '--url', 'https://example.com', '--dry-run']
args = automint.parse_args()
check("parse_args: --url captured",      args.url == 'https://example.com')
check("parse_args: --dry-run True",      args.dry_run is True)
check("parse_args: --watch default",     args.watch is False)
check("parse_args: --watch-interval=15", args.watch_interval == 15)

sys.argv = ['automint.py', '--contract', '0x1234', '--chain', 'eth', '--wallet', '2']
args = automint.parse_args()
check("parse_args: --contract captured", args.contract == '0x1234')
check("parse_args: --chain captured",    args.chain == 'eth')
check("parse_args: --wallet captured",   args.wallet == '2')

sys.argv = ['automint.py', '--watch', '--watch-interval', '30']
args = automint.parse_args()
check("parse_args: --watch=True",           args.watch is True)
check("parse_args: --watch-interval=30",    args.watch_interval == 30)

# ── show_batch_summary: no results ──
automint.BATCH_RESULTS.clear()
try:
    automint.show_batch_summary()
    check("show_batch_summary(empty): no crash", True)
except Exception as e:
    check("show_batch_summary(empty): no crash", False, str(e))

# with results
automint.BATCH_RESULTS.extend([
    {'wallet': '0x' + 'a' * 40, 'tier': 'Public', 'quantity': 1, 'status': 'success', 'tx_hash': '0x' + 'b' * 64},
    {'wallet': '0x' + 'c' * 40, 'tier': 'Public', 'quantity': 2, 'status': 'success', 'tx_hash': '0x' + 'd' * 64},
    {'wallet': '0x' + 'e' * 40, 'tier': 'Public', 'quantity': 1, 'status': 'failed',  'tx_hash': ''},
])
try:
    automint.show_batch_summary()
    check("show_batch_summary(mixed): no crash", True)
except Exception as e:
    check("show_batch_summary(mixed): no crash", False, str(e))
automint.BATCH_RESULTS.clear()

# ── notify: no backend = silent ──
try:
    notify('test message')
    check("notify(no backend): silent, no exception", True)
except Exception as e:
    check("notify(no backend): no exception", False, str(e))

try:
    notify_mint_result({'status': 'success', 'tx_hash': '0x' + 'a' * 64,
                        'total_cost_eth': 0.005},
                       'ethereum', 'Public', '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266')
    check("notify_mint_result(success): no exception", True)
except Exception as e:
    check("notify_mint_result(success): no exception", False, str(e))

for status in ('failed', 'pending', 'error', 'unknown'):
    try:
        notify_mint_result({'status': status, 'message': 'test'},
                           'base', 'Allowlist', '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266')
        check(f"notify_mint_result({status}): no exception", True)
    except Exception as e:
        check(f"notify_mint_result({status}): no exception", False, str(e))

# ── fetch_merkle_proof: returns list, no crash ──
proof = fetch_merkle_proof('0x' + 'a' * 40, '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266')
check("fetch_merkle_proof: returns list", isinstance(proof, list))

# env-provided proof
os.environ['MERKLE_PROOF'] = '0x' + 'ab' * 32 + ',0x' + 'cd' * 32
# clear cache first
import glob, shutil
for f in glob.glob(os.path.join('.cache', 'proofs', '*.json')):
    try: os.remove(f)
    except: pass
proof_env = fetch_merkle_proof('0x' + 'f' * 40, '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266')
check("fetch_merkle_proof(env): len=2",           len(proof_env) == 2)
check("fetch_merkle_proof(env): entries are 0x",  all(p.startswith('0x') for p in proof_env))
del os.environ['MERKLE_PROOF']

# ── get_working_rpc: at least one ethereum endpoint reachable ──
try:
    rpc = get_working_rpc('ethereum')
    check("get_working_rpc(ethereum): returns url", rpc.startswith('https://'))
    w3 = Web3(Web3.HTTPProvider(rpc))
    check("get_working_rpc(ethereum): connects",    w3.is_connected())
except RuntimeError as e:
    check("get_working_rpc(ethereum): RuntimeError (no connectivity)", True, str(e))
except Exception as e:
    check("get_working_rpc(ethereum): no crash", False, str(e))

# bad chain
try:
    get_working_rpc('nonexistent_chain')
    check("get_working_rpc(bad chain): should raise", False)
except RuntimeError:
    check("get_working_rpc(bad chain): raises RuntimeError", True)

# ── Full dry-run flow: detect → eligibility → cost estimate ──
r = detect('https://opensea.io/collection/pudgypenguins')
if not r.get('error'):
    from src.eligibility import check_eligibility, estimate_total_cost
    from src.executor import get_wallet

    acct, _ = get_wallet()
    wallet = acct.address if acct else '0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266'

    elig = check_eligibility(r['contract'], r['chain'], wallet, r['tiers'])
    check("full dry-run: eligibility runs",         isinstance(elig, list))
    check("full dry-run: results match tiers count", len(elig) == len(r['tiers']))

    if r['tiers']:
        est = estimate_total_cost(r['contract'], r['chain'], wallet, r['tiers'][0])
        check("full dry-run: estimate runs",       isinstance(est, dict))
        check("full dry-run: has error or total",  'error' in est or 'total_wei' in est)

# ── main guard ──
with open('automint.py', encoding='utf-8') as f:
    src = f.read()
check("automint.py: has KeyboardInterrupt guard", 'KeyboardInterrupt' in src)
check("automint.py: has __main__ guard",           '__main__' in src)
check("automint.py: has --watch argument",         '--watch' in src)
check("automint.py: has run_watch_mode",           'run_watch_mode' in src)

# ── Summary ──
print(f"\n{'='*50}")
print(f"Integration: {errors} failures" + (" OK" if errors == 0 else " FAIL"))
print(f"{'='*50}")
sys.exit(errors)
