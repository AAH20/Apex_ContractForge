import copy
import json
from pathlib import Path
import pytest
from apex_forge.contract import load, validate, digest
from apex_forge.compiler import generate, compile_to
from apex_forge.ir import operation, ref, const, build


def test_schema_and_packaged_contract_match():
    import jsonschema
    root = Path(__file__).resolve().parents[1]
    contract = load()
    assert json.loads((root / "contracts/tick-compatible.json").read_text()) == contract
    jsonschema.Draft202012Validator(json.loads((root / "contracts/contract.schema.json").read_text())).validate(contract)


@pytest.mark.parametrize("change", ["unknown", "capacity", "boolean_as_number", "time", "profile", "reference"])
def test_semantic_changes_cannot_keep_frozen_profile(change):
    value = copy.deepcopy(load())
    if change == "unknown": value["custom"] = True
    elif change == "capacity": value["bounds"]["pending_entries"] = 17
    elif change == "boolean_as_number": value["time"]["advance_on_idle_and_stall"] = 1
    elif change == "time": value["time"]["advance_on_idle_and_stall"] = False
    elif change == "profile": value["semantic_profile"] = "unqualified"
    else: value["reference"]["commit"] = "0" * 40
    with pytest.raises(ValueError): validate(value)


def test_pure_ir_rejects_mixed_width_comparison_and_unknown_operation():
    with pytest.raises(ValueError): operation("eq", ref("exposure"), ref("quantity"))
    with pytest.raises(ValueError): operation("execute_python", ref("price"))
    with pytest.raises(ValueError): const(-1, 32)
    with pytest.raises(ValueError): const(1 << 32, 32)
    ir, _, total = build(load())
    assert total.bits == 65 and ir["stateful_commit_schedule"].startswith("fixed")


def test_codegen_identity_and_no_overwrite(tmp_path):
    contract = load()
    metadata = compile_to(contract, tmp_path / "generated")
    assert metadata["contract_sha256"] == digest(contract)
    for filename in ["core.cpp", "core.sv"]:
        assert "@@" not in (tmp_path / "generated" / filename).read_text()
    with pytest.raises(ValueError): compile_to(contract, tmp_path / "generated")
    assert len(metadata["generated"]) == 2


def test_narrowing_requires_every_proof_result(monkeypatch):
    import apex_forge.proofs as proofs
    monkeypatch.setattr(proofs, "prove_counter_narrowing", lambda timeout_ms: {"obligations": [{"status": "unknown"}]})
    with pytest.raises(RuntimeError, match="not proved"):
        generate(load(), "sv", "narrow-counters")


def test_empty_proof_set_cannot_pass(monkeypatch):
    import apex_forge.proofs as proofs
    monkeypatch.setattr(proofs, "prove_counter_narrowing", lambda timeout_ms: {"obligations": []})
    with pytest.raises(RuntimeError, match="not proved"):
        generate(load(), "cpp", "narrow-counters")


def test_no_retiming_or_physical_savings_claim():
    source, ir, lineage = generate(load(), "sv", "narrow-counters")
    assert ir["rate_bits"] == 7 and ir["window_bits"] == 6
    assert "reg [6:0] rate_count" in source and "reg [5:0] window_count" in source
    assert "parameter integer" not in source
    assert lineage["rtl_declared_counter_bits_saved"] == 51
    assert lineage["physical_area_reduction"] is None and not lineage["stateful_retiming"]
