"""Merkle proof fetcher for allowlist contracts."""

import os
import json
import requests


_PROOF_APIS = [
    'https://api.highlight.xyz/v1/allowlist/{contract}/{address}/proof',
    'https://apps.api.manifoldxyz.dev/public/allowlist/proof/{contract}/{address}',
]

_PROOF_CACHE_DIR = os.path.join('.cache', 'proofs')
os.makedirs(_PROOF_CACHE_DIR, exist_ok=True)


def _cache_key(contract: str, address: str) -> str:
    return os.path.join(_PROOF_CACHE_DIR, f'{contract}_{address}.json')


def _read_proof_cache(contract: str, address: str) -> list | None:
    path = _cache_key(contract, address)
    try:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _write_proof_cache(contract: str, address: str, proof: list) -> None:
    try:
        with open(_cache_key(contract, address), 'w') as f:
            json.dump(proof, f)
    except OSError:
        pass


def fetch_merkle_proof(contract: str, address: str) -> list:
    """Try to fetch Merkle proof for (contract, address).

    Priority: cache → MERKLE_PROOF env → known launchpad APIs.
    Returns list of bytes32 hex strings, or [] if unavailable.
    """
    cached = _read_proof_cache(contract, address)
    if cached is not None:
        return cached

    env_proof = os.getenv('MERKLE_PROOF', '').strip()
    if env_proof:
        proof = [p.strip() for p in env_proof.split(',') if p.strip()]
        _write_proof_cache(contract, address, proof)
        return proof

    for template in _PROOF_APIS:
        url = template.format(contract=contract, address=address)
        try:
            resp = requests.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
            if resp.status_code != 200:
                continue
            data = resp.json()
            raw_proof = (
                data.get('proof') or
                data.get('merkleProof') or
                data.get('data', {}).get('proof') or
                []
            )
            if raw_proof and isinstance(raw_proof, list):
                proof = [p if p.startswith('0x') else '0x' + p for p in raw_proof]
                _write_proof_cache(contract, address, proof)
                return proof
        except Exception:
            continue

    return []
