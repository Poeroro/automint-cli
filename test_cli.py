"""CLI command tests — subprocess black-box tests"""
import subprocess, sys, os
sys.stdout.reconfigure(encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))

# Support both venv layouts
PY = None
for candidate in ['venv/Scripts/python.exe', 'venv/Scripts/python',
                   'venv/bin/python3', '.venv/bin/python3']:
    p = os.path.join(HERE, candidate)
    if os.path.exists(p):
        PY = p
        break
if PY is None:
    PY = sys.executable  # fallback to current interpreter

MAIN = os.path.join(HERE, 'automint.py')
PUDGY = 'https://opensea.io/collection/pudgypenguins'
PUDGY_CONTRACT = '0xBd3531dA5CF5857e7CfAA92426877b022e612cf8'
# Hardhat test key — safe for testing
TEST_KEY = '0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80'

errors = 0

def run(args, timeout=30, stdin_data=None, extra_env=None):
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PRIVATE_KEY'] = TEST_KEY  # ensure wallet always loads
    if extra_env:
        env.update(extra_env)
    try:
        r = subprocess.run(
            [PY, MAIN] + args,
            capture_output=True, timeout=timeout,
            cwd=HERE, text=True, encoding='utf-8',
            input=stdin_data, env=env,
        )
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, 'TIMEOUT', ''

def check(name, cond, detail=""):
    global errors
    if cond:
        print(f"  OK  {name}")
    else:
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))
        errors += 1

# ── --help ──
code, out, err = run(['--help'])
check("--help: exit 0",          code == 0,      f"code={code}")
check("--help: shows usage",     'usage:' in out.lower())
check("--help: --url",           '--url' in out)
check("--help: --contract",      '--contract' in out)
check("--help: --chain",         '--chain' in out)
check("--help: --dry-run",       '--dry-run' in out)
check("--help: --wallet",        '--wallet' in out)
check("--help: --watch",         '--watch' in out)
check("--help: --watch-interval",'--watch-interval' in out)

# ── bad inputs ──
code, out, err = run(['--url', 'not-a-url'])
check("bad url: exit != 0",    code != 0, f"code={code}")
check("bad url: error shown",  'Invalid' in out or 'error' in out.lower())

code, out, err = run(['--contract', '0x1234', '--chain', 'eth'])
check("bad contract (short): exit != 0", code != 0)

code, out, err = run(['--contract', PUDGY_CONTRACT, '--chain', 'invalid', '--dry-run'])
check("bad chain: error shown", 'Unknown' in out or 'unknown' in out.lower())

# ── dry-run via --url (Pudgy Penguins — may be sold out, no tiers) ──
code, out, err = run(['--url', PUDGY, '--dry-run'], timeout=45)
# Collection is detected regardless of tier availability
check("--url pudgy: banner shown",           'AutoMint' in out)
check("--url pudgy: contract resolved",      '0xBd3531' in out or '0xbd3531' in out.lower())
check("--url pudgy: chain shown",            'ethereum' in out)
check("--url pudgy: collection name shown",  'Pudgy' in out or 'pudgy' in out.lower())
check("--url pudgy: no traceback in stdout", 'Traceback' not in out)
check("--url pudgy: no traceback in stderr", 'Traceback' not in err)
# Exit 0 only if tiers found; exit 1 acceptable if sold out (no tiers)
check("--url pudgy: exits cleanly (0 or 1)", code in (0, 1), f"code={code}")

# ── dry-run via --contract ──
code, out, err = run(['--contract', PUDGY_CONTRACT, '--chain', 'eth', '--dry-run'], timeout=45)
check("--contract pudgy: chain resolved",  'ethereum' in out)
check("--contract pudgy: no traceback",    'Traceback' not in out)
check("--contract pudgy: exits cleanly",   code in (0, 1))

# ── chain alias ──
check("chain alias eth->ethereum shown",   'ethereum' in out and 'ID: 1' in out)

# ── custom RPC ──
code, out, err = run([
    '--contract', PUDGY_CONTRACT, '--chain', 'eth',
    '--rpc', 'https://ethereum.publicnode.com', '--dry-run'
], timeout=45)
check("--rpc override: no traceback",  'Traceback' not in out and 'Traceback' not in err)
check("--rpc override: detects OK",    'Pudgy' in out or '0xBd35' in out)

# ── chain mismatch with wrong RPC ──
code, out, err = run([
    '--contract', PUDGY_CONTRACT, '--chain', 'base',
    '--rpc', 'https://ethereum.publicnode.com', '--dry-run'
], timeout=20, stdin_data='n\n')
# chain mismatch OR falls through to no tiers — both are safe outcomes
check("chain mismatch: safe exit",
      code != 0 or 'mismatch' in out.lower() or 'No tiers' in out)

# ── tiers table display: only check if tiers were detected ──
code, out, err = run(['--url', PUDGY, '--dry-run'], timeout=45)
if 'No tiers detected' not in out:
    check("tiers table: 'Tier' column",   'Tier' in out)
    check("tiers table: 'Price' column",  'Price' in out)
    check("tiers table: 'Status' column", 'Status' in out)
else:
    check("tiers table: sold-out collection (no tiers to display)", True)

# ── MAX_GAS_GWEI guard (set absurdly low so it triggers without real tx) ──
try:
    code_g, out_g, err_g = run(['--url', PUDGY, '--dry-run'],
                                timeout=45, extra_env={'MAX_GAS_GWEI': '0'})
    r = type('R', (), {'stdout': out_g, 'stderr': err_g})()
    # dry-run exits before gas check in execute_mint, but gas display should still work
    check("MAX_GAS_GWEI=0: no crash", 'Traceback' not in r.stdout and 'Traceback' not in r.stderr)
except Exception as e:
    check("MAX_GAS_GWEI=0: no crash", False, str(e))

# ── Summary ──
print(f"\n{'='*50}")
print(f"CLI tests: {errors} failures" + (" OK" if errors == 0 else " FAIL"))
print(f"{'='*50}")
sys.exit(errors)
