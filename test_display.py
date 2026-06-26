"""Unit tests: display.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from src.display import show_banner, show_detect_result, show_eligibility, show_cost_estimate, show_report, console
from io import StringIO
from rich.console import Console

errors = 0

def check(name, cond, detail=""):
    global errors
    if cond:
        print(f"  ✅ {name}")
    else:
        print(f"  ❌ {name} — {detail}")
        errors += 1

# Capture rich output
test_console = Console(file=StringIO(), force_terminal=False)

# ── show_banner ──
try:
    show_banner()
    check("show_banner: no exception", True)
except Exception as e:
    check("show_banner: no exception", False, str(e))

# ── show_detect_result ──
try:
    show_detect_result({'name': 'Test NFT', 'contract': '0xBd3531dA5CF5857e7CfAA92426877b022e612cf8', 'chain': 'ethereum', 'chainId': 1, 'tiers': [{'name': 'Public', 'price': 0, 'status': 'active', 'methodSig': '0x1249c58b'}]})
    check("show_detect_result(normal): no exception", True)
except Exception as e:
    check("show_detect_result(normal): no exception", False, str(e))

# Error case
try:
    show_detect_result({'error': 'Something broke'})
    check("show_detect_result(error): no exception", True)
except Exception as e:
    check("show_detect_result(error): no exception", False, str(e))

# Empty tiers
try:
    show_detect_result({'name': 'Test', 'tiers': []})
    check("show_detect_result(empty tiers): no exception", True)
except Exception as e:
    check("show_detect_result(empty tiers): no exception", False, str(e))

# Scheduled tier
try:
    import time
    future = int(time.time()) + 86400
    show_detect_result({'name': 'Scheduled NFT', 'contract': '0x1234', 'chain': 'ethereum', 'chainId': 1, 'tiers': [{'name': 'Allowlist', 'price': 0.1, 'status': f'scheduled:{future}', 'methodSig': '0x52044153'}]})
    check("show_detect_result(scheduled): no exception", True)
except Exception as e:
    check("show_detect_result(scheduled): no exception", False, str(e))

# ── show_eligibility ──
try:
    show_eligibility([{'name': 'Public', 'price': 0, 'eligible': True, 'reasons': ['balance OK']}, {'name': 'Allowlist', 'price': 0.1, 'eligible': False, 'reasons': ['not whitelisted']}], '0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf', 1.5, 'ETH')
    check("show_eligibility: no exception", True)
except Exception as e:
    check("show_eligibility: no exception", False, str(e))

# With BNB currency
try:
    show_eligibility([{'name': 'Public', 'price': 0.5, 'eligible': True, 'reasons': ['balance OK']}], '0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf', 2.0, 'BNB')
    check("show_eligibility(BNB): no exception", True)
except Exception as e:
    check("show_eligibility(BNB): no exception", False, str(e))

# ── show_cost_estimate ──
try:
    show_cost_estimate({'price_eth': 0.1, 'price_wei': 100000000000000000, 'gas_units': 21000, 'gas_price_gwei': 25.5, 'gas_cost_eth': 0.0005355, 'total_eth': 0.1005355, 'total_wei': 100535500000000000})
    check("show_cost_estimate(normal): no exception", True)
except Exception as e:
    check("show_cost_estimate(normal): no exception", False, str(e))

# Error case
try:
    show_cost_estimate({'error': 'estimate gas failed'})
    check("show_cost_estimate(error): no exception", True)
except Exception as e:
    check("show_cost_estimate(error): no exception", False, str(e))

# ── show_report ──
try:
    show_report({'status': 'success', 'tx_hash': '0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890', 'block': 12345678, 'gas_used': 21000, 'gas_price_gwei': 25.5, 'gas_cost_eth': 0.0005355, 'total_cost_eth': 0.1005355}, 'ethereum')
    check("show_report(success): no exception", True)
except Exception as e:
    check("show_report(success): no exception", False, str(e))

try:
    show_report({'status': 'failed', 'tx_hash': '0xabc', 'message': 'Transaction reverted'})
    check("show_report(failed): no exception", True)
except Exception as e:
    check("show_report(failed): no exception", False, str(e))

try:
    show_report({'status': 'pending', 'tx_hash': '0xabc'})
    check("show_report(pending): no exception", True)
except Exception as e:
    check("show_report(pending): no exception", False, str(e))

# ── Summary ──
print(f"\n{'='*50}")
print(f"display.py: {errors} failures" + (" ✅" if errors == 0 else " ❌"))
print(f"{'='*50}")
sys.exit(errors)
