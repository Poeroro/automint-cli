"""Unit tests: display.py"""
import sys, os, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from src.display import (
    show_banner, show_detect_result, show_eligibility,
    show_cost_estimate, show_report, show_wallets
)

errors = 0

def check(name, cond, detail=""):
    global errors
    if cond:
        print(f"  OK  {name}")
    else:
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))
        errors += 1

def no_crash(name, fn):
    try:
        fn()
        check(name, True)
    except Exception as e:
        check(name, False, str(e))

# ── show_banner ──
no_crash("show_banner", show_banner)

# ── show_detect_result ──
no_crash("show_detect_result(normal)", lambda: show_detect_result({
    'name': 'Test NFT', 'contract': '0xBd3531dA5CF5857e7CfAA92426877b022e612cf8',
    'chain': 'ethereum', 'chainId': 1,
    'tiers': [{'name': 'Public', 'price': 0, 'status': 'active',
               'methodSig': '0x1249c58b', 'maxMint': 5}]
}))
no_crash("show_detect_result(error)",        lambda: show_detect_result({'error': 'Broke'}))
no_crash("show_detect_result(empty tiers)",  lambda: show_detect_result({'name': 'T', 'tiers': []}))
no_crash("show_detect_result(free tier)",    lambda: show_detect_result({
    'name': 'Free', 'chain': 'ethereum', 'chainId': 1, 'contract': '0x' + '0' * 40,
    'tiers': [{'name': 'Freemint', 'price': 0, 'status': 'active', 'methodSig': '0xd18e81b3', 'maxMint': 0}]
}))
no_crash("show_detect_result(scheduled)", lambda: show_detect_result({
    'name': 'Scheduled NFT', 'contract': '0x1234', 'chain': 'ethereum', 'chainId': 1,
    'tiers': [{'name': 'Allowlist', 'price': 0.1,
               'status': f'scheduled:{int(time.time()) + 86400}',
               'methodSig': '0x3af32abf', 'maxMint': 2}]
}))
no_crash("show_detect_result(multi-tier)", lambda: show_detect_result({
    'name': 'Multi', 'chain': 'base', 'chainId': 8453, 'contract': '0x' + '0' * 40,
    'tiers': [
        {'name': 'OG',       'price': 0,     'status': 'active',    'methodSig': '0xa28c555d', 'maxMint': 1},
        {'name': 'Allowlist','price': 0.003, 'status': f'scheduled:{int(time.time()) + 3600}',
         'methodSig': '0x3af32abf', 'maxMint': 2},
        {'name': 'Public',   'price': 0.005, 'status': 'active',    'methodSig': '0xa0712d68', 'maxMint': 5},
    ]
}))

# ── show_eligibility ──
no_crash("show_eligibility(mixed)", lambda: show_eligibility([
    {'name': 'Public',    'price': 0,    'eligible': True,  'reasons': ['balance OK'], 'maxMint': 5},
    {'name': 'Allowlist', 'price': 0.1,  'eligible': False, 'reasons': ['not whitelisted'], 'maxMint': 2},
    {'name': 'Freemint',  'price': 0,    'eligible': True,  'reasons': ['free mint OK'], 'maxMint': 0},
], '0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf', 1.5, 'ETH'))

no_crash("show_eligibility(BNB)", lambda: show_eligibility([
    {'name': 'Public', 'price': 0.5, 'eligible': True, 'reasons': ['balance OK'], 'maxMint': 3},
], '0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf', 2.0, 'BNB'))

no_crash("show_eligibility(merkle tier)", lambda: show_eligibility([
    {'name': 'Allowlist', 'price': 0.003, 'eligible': False,
     'reasons': ['merkle proof required'], 'maxMint': 2, 'requiresMerkle': True},
], '0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf', 0.5, 'ETH'))

# ── show_cost_estimate ──
no_crash("show_cost_estimate(normal)", lambda: show_cost_estimate({
    'price_eth': 0.1, 'price_wei': 100_000_000_000_000_000,
    'gas_units': 21_000, 'gas_price_gwei': 25.5,
    'gas_cost_eth': 0.0005355, 'total_eth': 0.1005355, 'total_wei': 100_535_500_000_000_000
}))
no_crash("show_cost_estimate(free)",  lambda: show_cost_estimate({
    'price_eth': 0, 'price_wei': 0,
    'gas_units': 80_000, 'gas_price_gwei': 5.0,
    'gas_cost_eth': 0.0004, 'total_eth': 0.0004, 'total_wei': 400_000_000_000_000
}))
no_crash("show_cost_estimate(error)", lambda: show_cost_estimate({'error': 'estimate gas failed'}))

# ── show_wallets ──
no_crash("show_wallets(single)", lambda: show_wallets([
    {'address': '0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf',
     'balance_eth': 0.5,
     'best_tier': {'name': 'Public', 'price': 0.005}}
], 'ETH'))
no_crash("show_wallets(no eligible tier)", lambda: show_wallets([
    {'address': '0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf',
     'balance_eth': 0.001, 'best_tier': None}
], 'ETH'))
no_crash("show_wallets(free tier)", lambda: show_wallets([
    {'address': '0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf',
     'balance_eth': 0.0, 'best_tier': {'name': 'Freemint', 'price': 0}}
], 'ETH'))

# ── show_report ──
TX = '0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890'
no_crash("show_report(success/eth)",  lambda: show_report({
    'status': 'success', 'tx_hash': TX, 'block': 12_345_678,
    'gas_used': 21_000, 'gas_price_gwei': 25.5,
    'gas_cost_eth': 0.0005355, 'total_cost_eth': 0.1005355
}, 'ethereum'))
no_crash("show_report(success/base)", lambda: show_report({
    'status': 'success', 'tx_hash': TX, 'block': 5_000_000,
    'gas_used': 60_000, 'gas_price_gwei': 0.5,
    'gas_cost_eth': 0.00003, 'total_cost_eth': 0.00303
}, 'base'))
no_crash("show_report(failed)",   lambda: show_report(
    {'status': 'failed', 'tx_hash': TX, 'message': 'Transaction reverted'}, 'ethereum'))
no_crash("show_report(pending)",  lambda: show_report(
    {'status': 'pending', 'tx_hash': TX}, 'ethereum'))
no_crash("show_report(error)",    lambda: show_report(
    {'status': 'error', 'message': 'RPC not connected'}, 'ethereum'))
no_crash("show_report(unknown chain)", lambda: show_report({
    'status': 'success', 'tx_hash': TX, 'block': 1,
    'gas_used': 21_000, 'gas_price_gwei': 10.0,
    'gas_cost_eth': 0.00021, 'total_cost_eth': 0.00521
}, 'unknownchain'))

# ── Summary ──
print(f"\n{'='*50}")
print(f"display.py: {errors} failures" + (" OK" if errors == 0 else " FAIL"))
print(f"{'='*50}")
sys.exit(errors)
