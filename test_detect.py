"""Unit tests: detect.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from src.detect import detect, detect_onchain, resolve_collection

errors = 0

def check(name, cond, detail=""):
    global errors
    if cond:
        print(f"  ✅ {name}")
    else:
        print(f"  ❌ {name} — {detail}")
        errors += 1

# ── detect: invalid inputs ──
r = detect("not-a-url")
check("detect('not-a-url') returns error", r.get('error'))
check("  error message mentions input", 'Invalid input' in r.get('error',''))

r = detect("")
check("detect('') returns error", r.get('error'))

r = detect("0x123")  # malformed address (not 40 hex chars)
check("detect('0x123') returns error", r.get('error'))
check("  error says invalid input", 'Invalid input' in r.get('error',''))

# ── detect: valid contract address format but wrong length ──
r = detect("0x1234567890123456789012345678901234567890", "")  # valid hex but no chain
check("detect(40-char hex, no chain) error", r.get('error'))

r = detect("0x1234567890123456789012345678901234567890", "eth")  # valid format with chain
check("detect(40-char hex, chain='eth') no error", not r.get('error'), str(r.get('error')))
check("  has contract address", bool(r.get('contract')))

# ── detect: OpenSea URL ──
r = detect("https://opensea.io/collection/pudgypenguins")
check("detect(OS URL) no error", not r.get('error'), str(r.get('error')))
check("  has contract", r.get('contract'))
check("  contract is checksummed (mixed case)", r.get('contract','') != r.get('contract','').lower() and r.get('contract','') != r.get('contract','').upper())
check("  chain detected", r.get('chain'))
check("  name detected", r.get('name'))
check("  tiers is list", isinstance(r.get('tiers'), list))

# ── detect_onchain: known contract ──
r = detect_onchain("0xBd3531dA5CF5857e7CfAA92426877b022e612cf8", "ethereum")
check("detect_onchain(Pudgy, eth): no error", not r.get('error'), str(r.get('error')))
check("  has name", r.get('name'))
check("  has symbol", r.get('symbol'))
check("  has tiers", len(r.get('tiers', [])) > 0)
check("  contract is checksummed", r['contract'] == '0xBd3531dA5CF5857e7CfAA92426877b022e612cf8')
check("  chainId=1", r.get('chainId') == 1)

# ── detect_onchain: unknown chain ──
r = detect_onchain("0xBd3531dA5CF5857e7CfAA92426877b022e612cf8", "nonexistent")
check("detect_onchain(unknown chain) error", r.get('error'))

# ── resolve_collection ──  
r = resolve_collection("pudgypenguins")
check("resolve_collection no error", 'error' not in r)
check("  has contract", r.get('contract'))
check("  has name", r.get('name'))
check("  chain is ethereum", r.get('chain') == 'ethereum' or r.get('chain') == 'ethereum')

# ── resolve_collection: invalid slug ──
r = resolve_collection("this-slug-definitely-does-not-exist-12345")
check("resolve_collection(bad slug): no error (just empty)", 'error' not in r)
check("  contract is None", r.get('contract') is None)

# ── Summary ──
print(f"\n{'='*50}")
print(f"detect.py: {errors} failures" + (" ✅" if errors == 0 else " ❌"))
print(f"{'='*50}")
sys.exit(errors)
