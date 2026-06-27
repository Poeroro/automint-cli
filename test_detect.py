"""Unit tests: detect.py"""
# ruff: noqa: E402
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from src.detect import detect, detect_onchain, scrape_opensea_collection

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
check("  error says invalid input", 'Invalid input' in r.get('error',''))

r = detect("")
check("detect('') returns error", r.get('error'))

r = detect("0x123")  # malformed address
check("detect('0x123') returns error", r.get('error'))

# ── detect: contract without chain = error (no more auto-detect) ──
r = detect("0x1234567890123456789012345678901234567890", "")
check("detect(contract, no chain) error — chain required", r.get('error'))
check("  error says --chain required", '--chain' in r.get('error',''))

# ── detect: contract with chain ──
r = detect("0x1234567890123456789012345678901234567890", "eth")
check("detect(contract, chain='eth') no error", not r.get('error'), str(r.get('error')))
check("  has contract address", bool(r.get('contract')))

# ── detect: OpenSea URL (scrape, not API) ──
r = detect("https://opensea.io/collection/pudgypenguins")
check("detect(OS URL) no error", not r.get('error'), str(r.get('error')))
check("  has contract", r.get('contract'))
check("  contract is checksummed", r.get('contract','') != r.get('contract','').lower())
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

# ── scrape_opensea_collection ──
r = scrape_opensea_collection("pudgypenguins")
check("scrape_collection no error", 'error' not in r, str(r.get('error','')))
check("  has contract", r.get('contract'))
check("  contract is checksummed", r.get('contract','') != r.get('contract','').lower())
check("  chain is ethereum", r.get('chain') == 'ethereum')

# ── scrape_opensea_collection: invalid slug ──
r = scrape_opensea_collection("this-slug-definitely-does-not-exist-12345")
check("scrape_collection(bad slug) has error", 'error' in r)

# ── Summary ──
print(f"\n{'='*50}")
print(f"detect.py: {errors} failures" + (" ✅" if errors == 0 else " ❌"))
print(f"{'='*50}")
sys.exit(errors)
