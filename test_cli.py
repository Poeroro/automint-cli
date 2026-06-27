"""CLI command tests — edge cases, flags, real URL"""
# ruff: noqa: E402
import subprocess
import sys
import os
HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, '.venv', 'bin', 'python3')
MAIN = os.path.join(HERE, 'automint.py')

errors = 0

def run(args, timeout=15):
    """Run automint with args, return (exit_code, stdout, stderr)."""
    try:
        r = subprocess.run([PY, MAIN] + args, capture_output=True, timeout=timeout, cwd=HERE, text=True)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT", ""

def check(name, cond, detail=""):
    global errors
    if cond:
        print(f"  ✅ {name}")
    else:
        print(f"  ❌ {name} — {detail}")
        errors += 1

# ── CLI: --help ──
code, out, err = run(['--help'])
check("--help: exit 0", code == 0, f"code={code}")
check("--help: shows usage", 'usage:' in out)
check("--help: shows --url", '--url' in out)
check("--help: shows --contract", '--contract' in out)
check("--help: shows --chain", '--chain' in out)
check("--help: shows --rpc", '--rpc' in out)
check("--help: shows --dry-run", '--dry-run' in out)
check("--help: shows --wallet", '--wallet' in out)

# ── CLI: no args ──
code, out, err = run([])
check("no args: exit 1 (interactive mode)", code == 1, f"code={code}")
check("no args: prompts for input", 'Target NFT' in out or 'contract address' in out)

# ── CLI: invalid input ──
code, out, err = run(['--url', 'not-a-url'])
check("--url invalid: exit 1", code == 1, f"code={code}")
check("--url invalid: error message", 'Invalid input' in out)

# ── CLI: --url with real OS URL ──
code, out, err = run(['--url', 'https://opensea.io/collection/pudgypenguins', '--dry-run'], timeout=30)
check("--url pudgypenguins --dry-run: exit 0 (dry-run sukses)", code == 0, f"code={code}")
check("  — banner shown", '✦ AutoMint CLI' in out)
check("  — collection detected", 'PudgyPenguins' in out or 'Pudgy' in out)
check("  — contract resolved", '0x' in out)
check("  — wallet loaded", 'Wallets loaded' in out)
check("  — eligibility checked", 'Eligible' in out or 'eligible' in out or 'Public' in out)
check("  — no crash traceback", 'Traceback' not in out and 'Traceback' not in err)

# ── CLI: --contract + --chain ──
code, out, err = run(['--contract', '0xBd3531dA5CF5857e7CfAA92426877b022e612cf8', '--chain', 'eth', '--dry-run'], timeout=30)
check("--contract pudgy --chain eth --dry-run: exit 0", code == 0, f"code={code}")
check("  — collection detected", 'PudgyPenguins' in out or 'Pudgy' in out)
check("  — chain eth resolved", 'ethereum' in out)
check("  — no traceback", 'Traceback' not in out)

# ── CLI: --chain alias 'eth' → 'ethereum' ──
check("  — chain alias resolved", 'ethereum' in out and 'ID: 1' in out)

# ── CLI: --rpc override ──
code, out, err = run(['--contract', '0xBd3531dA5CF5857e7CfAA92426877b022e612cf8', '--chain', 'eth', '--rpc', 'https://ethereum.publicnode.com', '--dry-run'], timeout=30)
check("--rpc override: works", 'Traceback' not in out and 'Traceback' not in err, f"err={err[:200]}")
check("  — detects OK with custom rpc", 'PudgyPenguins' in out or 'Pudgy' in out)

# ── CLI: chain mismatch with custom RPC ──
code, out, err = run(['--contract', '0xBd3531dA5CF5857e7CfAA92426877b022e612cf8', '--chain', 'base', '--rpc', 'https://ethereum.publicnode.com', '--dry-run'], timeout=15)
check("--chain base + --rpc eth: mismatch detected", 'Chain mismatch' in out or 'Chain mismatch' in err)
check("  — shows chain id", 'chainId=1' in out or 'chainId=1' in err)
check("  — exit=1 (user declined force continue)", code == 1, f"code={code}")

# ── CLI: invalid chain → error (gak ada fallback lagi) ──
code, out, err = run(['--contract', '0x1234567890123456789012345678901234567890', '--chain', 'invalid', '--dry-run'], timeout=15)
check("--chain invalid: error shown", 'Unknown chain' in out)

# ── CLI: multiple tiers (test display code path) ──
code, out, err = run(['--url', 'https://opensea.io/collection/pudgypenguins', '--dry-run'], timeout=30)
check("multi-tier display: tiers table shown", 'Tier' in out and 'Price' in out and 'Status' in out)
check("  — price shown for tier", 'ETH' in out)

# ── automint.log: written by non-dry-run code path ──
# Note: dry-run mode exits BEFORE log write, so no entries from CLI tests
# The log is tested in test_integration.py instead

# ── Summary ──
print(f"\n{'='*50}")
print(f"CLI command tests: {errors} failures" + (" ✅" if errors == 0 else " ❌"))
print(f"{'='*50}")
sys.exit(errors)
