"""Unit tests: detect.py"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from src.detect import detect, detect_onchain, scrape_opensea_collection, build_calldata, NO_ARG_SIGS, MERKLE_SIGS

errors = 0

def check(name, cond, detail=""):
    global errors
    if cond:
        print(f"  OK  {name}")
    else:
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))
        errors += 1

# ── build_calldata ──
# no-arg
r = build_calldata('0x1249c58b', 3)
check("build_calldata(no-arg): no qty appended", r == '0x1249c58b')

# uint256
r = build_calldata('0xa0712d68', 5)
check("build_calldata(uint256): length=10+64", len(r) == 10 + 64, f"len={len(r)}")
check("build_calldata(uint256): qty encoded", r.endswith('5'), r)

# merkle
proof = ['0x' + 'ab' * 32]
r = build_calldata('0x7bc9200e', 2, proof)
check("build_calldata(merkle): starts with sig", r.startswith('0x7bc9200e'))
check("build_calldata(merkle): longer than no-proof", len(r) > 10 + 64 + 64)

# merkle sig without proof falls back to uint256 only
r_noproof = build_calldata('0x7bc9200e', 2, None)
check("build_calldata(merkle, no proof): fallback to qty only",
      r_noproof == '0x7bc9200e' + '0' * 63 + '2')

# qty=1 encoding
r = build_calldata('0xa0712d68', 1)
check("build_calldata qty=1: last char is 1", r[-1] == '1')

# ── detect: invalid inputs ──
check("detect(''): error",           detect('').get('error'))
check("detect('bad'): error",        detect('bad').get('error'))
check("detect('0x123'): error",      detect('0x123').get('error'))  # too short

r = detect('0x' + 'a' * 40, '')
check("detect(contract, no chain): error",          r.get('error'))
check("detect(contract, no chain): mentions --chain", '--chain' in r.get('error', ''))

r = detect('0x' + 'a' * 40, 'invalidchain')
check("detect(contract, bad chain): error",        r.get('error'))
check("detect(contract, bad chain): says Unknown", 'Unknown' in r.get('error', ''))

# ── detect: OpenSea URL parsing ──
r = detect('https://opensea.io/collection/pudgypenguins')
check("detect(OS URL): no error",     not r.get('error'), r.get('error', ''))
check("detect(OS URL): has contract", bool(r.get('contract')))
check("detect(OS URL): checksummed",  r.get('contract', '') != r.get('contract', '').lower())
check("detect(OS URL): has chain",    bool(r.get('chain')))
check("detect(OS URL): has name",     bool(r.get('name')))
check("detect(OS URL): tiers list",   isinstance(r.get('tiers'), list))
check("detect(OS URL): chainId=1",    r.get('chainId') == 1)
check("detect(OS URL): no traceback", 'Traceback' not in str(r))

# URL variant without /collection/
r2 = detect('https://opensea.io/pudgypenguins')
check("detect(OS URL no /collection/): no error or same result",
      not r2.get('error') or 'Invalid' in r2.get('error', ''))

# ── detect: contract address ──
r = detect('0xBd3531dA5CF5857e7CfAA92426877b022e612cf8', 'eth')
check("detect(contract, eth): no error",  not r.get('error'), r.get('error', ''))
check("detect(contract, eth): contract",  bool(r.get('contract')))
check("detect(contract, eth): checksum",  r.get('contract') == '0xBd3531dA5CF5857e7CfAA92426877b022e612cf8')
check("detect(contract, eth): chainId=1", r.get('chainId') == 1)

# ── detect_onchain ──
r = detect_onchain('0xBd3531dA5CF5857e7CfAA92426877b022e612cf8', 'ethereum')
check("detect_onchain(Pudgy): no error", not r.get('error'), r.get('error', ''))
check("detect_onchain(Pudgy): has name", bool(r.get('name')))
check("detect_onchain(Pudgy): has symbol", bool(r.get('symbol')))
check("detect_onchain(Pudgy): tiers is list", isinstance(r.get('tiers'), list))
check("detect_onchain(Pudgy): chainId=1", r.get('chainId') == 1)
check("detect_onchain(Pudgy): contract checksummed",
      r.get('contract') == '0xBd3531dA5CF5857e7CfAA92426877b022e612cf8')

# tiers structure
for tier in r.get('tiers', []):
    check(f"  tier '{tier['name']}': has methodSig", bool(tier.get('methodSig')))
    check(f"  tier '{tier['name']}': methodSig is 0x...", tier.get('methodSig', '').startswith('0x'))
    check(f"  tier '{tier['name']}': has status",    'status' in tier)
    check(f"  tier '{tier['name']}': price >= 0",    tier.get('price', -1) >= 0)
    check(f"  tier '{tier['name']}': requiresMerkle is bool",
          isinstance(tier.get('requiresMerkle'), bool))

# ── detect_onchain: unknown chain ──
r = detect_onchain('0xBd3531dA5CF5857e7CfAA92426877b022e612cf8', 'nonexistent')
check("detect_onchain(unknown chain): has error", bool(r.get('error')))

# ── scrape_opensea_collection ──
r = scrape_opensea_collection('pudgypenguins')
check("scrape(pudgypenguins): no error",    'error' not in r, r.get('error', ''))
check("scrape(pudgypenguins): has contract", bool(r.get('contract')))
check("scrape(pudgypenguins): checksummed",
      r.get('contract', '') != r.get('contract', '').lower())
check("scrape(pudgypenguins): chain=ethereum", r.get('chain') == 'ethereum')
check("scrape(pudgypenguins): has name",       bool(r.get('name')))

r = scrape_opensea_collection('this-slug-definitely-does-not-exist-zzzzz')
check("scrape(bad slug): has error", 'error' in r)

# ── Summary ──
print(f"\n{'='*50}")
print(f"detect.py: {errors} failures" + (" OK" if errors == 0 else " FAIL"))
print(f"{'='*50}")
sys.exit(errors)
