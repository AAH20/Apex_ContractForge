"""Strict semantic-profile frontend. Unknown semantics cannot inherit a profile ID."""
import hashlib
import json
from importlib.resources import files
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def default_contract():
    return json.loads(files("apex_forge").joinpath("data/tick-compatible.json").read_text())


def load(path=None):
    contract = default_contract() if path is None else json.loads(Path(path).read_text())
    validate(contract)
    return contract


def validate(contract):
    # v0 supports one fully specified profile, not arbitrary executable source.
    # Exact equality includes JSON scalar types (bool is not an integer here).
    if canonical(contract) != canonical(default_contract()):
        raise ValueError("unsupported or altered contract: v0 supports only the frozen Tick-compatible profile")
    return digest(contract)
