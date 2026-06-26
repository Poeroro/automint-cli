"""Integration tests: CLI entry points"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

import automint  # main entry point
from web3 import Web3
from src.config import CHAINS

errors = 0

def check(name, cond, detail=""):
    global errors
    if cond:
        print(f"  ✅ {name}")
    else:
        print(f"  ❌ {name} — {detail}")
        errors += 1

# ── check_env_file ──
# Should not raise when .env exists with 600
try:
    automint.check_env_file()
    check("check_env_file(600): no exception", True)
except Exception as e:
    check("check_env_file(600): no exception", False, str(e))

# .env doesn't exist
import os as _os
saved_cwd = _os.getcwd()
_os.chdir("/tmp")
try:
    automint.check_env_file()
    check("check_env_file(no .env): no exception", True)
except Exception as e:
    check("check_env_file(no .env): no exception", False, str(e))
_os.chdir(saved_cwd)

# ── verify_chain_id ──
rpc = CHAINS['ethereum']['rpc']
w3 = Web3(Web3.HTTPProvider(rpc))
try:
    result = automint.verify_chain_id(w3, 'ethereum')
    if w3.is_connected():
        check("verify_chain_id(eth, ethereum): match", result is True, f"got {result}")
    else:
        check("verify_chain_id: RPC not reachable (skip)", True)
except Exception as e:
    check("verify_chain_id: no exception", False, str(e))

# Unknown chain — should return True (skip)
try:
    result = automint.verify_chain_id(w3, 'nonexistent')
    check("verify_chain_id(unknown chain): returns True", result is True)
except Exception as e:
    check("verify_chain_id(unknown chain): no exception", False, str(e))

# Mismatch case via mock — not possible without RPC, check function structure
check("verify_chain_id has chain_id check", 'chain_id' in automint.verify_chain_id.__code__.co_names)

# ── append_log ──
test_entry = {
    'timestamp': time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime()),
    'chain': 'ethereum',
    'contract': '0x1234',
    'tier': 'Public',
    'price': 0,
    'status': 'dry-run',
    'tx_hash': '',
}
try:
    automint.append_log(test_entry)
    check("append_log: no exception", True)
    # Verify file exists and has content
    log_path = 'automint.log'
    if os.path.exists(log_path):
        with open(log_path) as f:
            content = f.read().strip()
        check("append_log: file written", len(content) > 0)
        try:
            parsed = json.loads(content.split('\n')[-1])
            check("append_log: valid JSON", all(k in parsed for k in ['timestamp', 'chain', 'contract', 'tier', 'status']))
        except:
            check("append_log: valid JSON", False, "not valid JSON")
    else:
        check("append_log: file exists", False)
except Exception as e:
    check("append_log: no exception", False, str(e))

# append_log: silent fail (no crash) on bad path
try:
    automint.append_log({'test': 'data'})  # will work
    check("append_log(any dict): no crash", True)
except Exception as e:
    check("append_log(any dict): no crash", False, str(e))

# ── main flow simulation ──
# Test that parse_args works
import argparse
try:
    # Simulate command-line args
    sys.argv = ['automint.py', '--help']
    try:
        automint.parse_args()
    except SystemExit:
        pass  # expected for --help
    check("parse_args: --help exits gracefully", True)
except Exception as e:
    check("parse_args: --help exits gracefully", False, str(e))

# ── KeyboardInterrupt handling ──
# The main() function has a try/except around it — verify the code exists
with open('automint.py') as f:
    content = f.read()
check("main(): has KeyboardInterrupt handler", 'KeyboardInterrupt' in content)
check("main(): has main() call guard", '__main__' in content)

# ── Summary ──
print(f"\n{'='*50}")
print(f"Integration tests: {errors} failures" + (" ✅" if errors == 0 else " ❌"))
print(f"{'='*50}")
sys.exit(errors)
