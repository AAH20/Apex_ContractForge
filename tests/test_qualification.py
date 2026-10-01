import gzip
import json
import shutil
from pathlib import Path
import pytest
from apex_forge.compiler import MUTATIONS
from apex_forge.evidence import validate_evidence, write_manifest, export_atlas
from apex_forge.qualification import qualify
from apex_forge.cli import main


@pytest.fixture(scope="module")
def retained(tmp_path_factory):
    root = tmp_path_factory.mktemp("qualified") / "run"
    qualify(root, seeds=(17, 29), steps=100)
    return root


def clone(source, target):
    shutil.copytree(source, target); return target


def test_both_variants_and_reference_rtl_match(retained):
    report = json.loads((retained / "qualification.json").read_text())
    assert report["status"] == "passed" and report["backend_count"] == 5
    assert report["scenario_count"] == 15
    assert len(report["mutations"]) == len(MUTATIONS) * 2
    assert all(m["status"] == "detected" for m in report["mutations"])
    assert validate_evidence(retained) == []


def test_artifact_tampering_is_detected(retained, tmp_path):
    root = clone(retained, tmp_path / "run")
    (root / "proofs.json").write_text("{}")
    assert "hash mismatch" in validate_evidence(root)[0]


def test_rebound_false_counts_are_detected(retained, tmp_path):
    root = clone(retained, tmp_path / "run")
    path = root / "qualification.json"; report = json.loads(path.read_text())
    report["cycles_per_backend"] += 1; path.write_text(json.dumps(report)); write_manifest(root)
    assert "accounting mismatch" in validate_evidence(root)[0]


def test_rebound_false_trace_is_independently_rejected(retained, tmp_path):
    root = clone(retained, tmp_path / "run"); path = root / "traces/baseline-cpp.txt.gz"
    with gzip.open(path, "rt") as stream: rows = stream.readlines()
    row = rows[2].split(); row[7] = str(int(row[7]) + 1); rows[2] = " ".join(row) + "\n"
    with gzip.open(path, "wt") as stream: stream.writelines(rows)
    write_manifest(root)
    assert "trace mismatch" in validate_evidence(root)[0]


def test_unknown_proof_and_physical_claim_are_rejected(retained, tmp_path):
    root = clone(retained, tmp_path / "run")
    path = root / "proofs.json"; value = json.loads(path.read_text()); value["obligations"][0]["status"] = "unknown"
    path.write_text(json.dumps(value)); write_manifest(root)
    assert "proof obligation" in validate_evidence(root)[0]
    root2 = clone(retained, tmp_path / "other")
    path = root2 / "qualification.json"; value = json.loads(path.read_text()); value["physical_latency_ns"] = 3
    path.write_text(json.dumps(value)); write_manifest(root2)
    assert "physical performance" in validate_evidence(root2)[0]


def test_counterexample_binding_cannot_be_forged(retained, tmp_path):
    root = clone(retained, tmp_path / "run")
    path = root / "qualification.json"; value = json.loads(path.read_text()); value["mutations"][0]["counterexample"]["expected"][7] += 1
    path.write_text(json.dumps(value)); write_manifest(root)
    assert "replay binding mismatch" in validate_evidence(root)[0]


def test_atlas_export_is_simulation_only_and_non_overwriting(retained, tmp_path):
    root = clone(retained, tmp_path / "run"); record = export_atlas(root)
    assert record["measurement"]["method"] == "simulation" and record["measurement"]["resolution_ns"] is None
    assert record["metrics"][0]["unit"] == "count"
    with pytest.raises(ValueError, match="already exists"): export_atlas(root)
    assert main(["validate-evidence", str(root)]) == 0


def test_budget_and_seed_validation(tmp_path):
    for seeds, steps in [((17, 17), 10), ((), 10), ((-1,), 10), ((17,), 0), ((17, 29), 1_000_000)]:
        with pytest.raises(ValueError): qualify(tmp_path / "run", seeds, steps)


def test_output_does_not_overwrite_existing_evidence(retained):
    with pytest.raises(ValueError, match="absent or empty"): qualify(retained)


def test_export_cannot_label_unknown_source_as_valid_measured(retained, tmp_path):
    root = clone(retained, tmp_path / "run")
    path = root / "provenance.json"; value = json.loads(path.read_text()); value["commit"] = None
    path.write_text(json.dumps(value)); write_manifest(root)
    with pytest.raises(ValueError, match="available source revision"): export_atlas(root)


def test_rebound_trivial_proof_is_not_an_obligation(retained, tmp_path):
    root = clone(retained, tmp_path / "run")
    path = root / "proofs.json"; value = json.loads(path.read_text()); value["obligations"][0]["query_smt2"] = "(assert false)"
    path.write_text(json.dumps(value)); write_manifest(root)
    assert "regenerated obligations" in validate_evidence(root)[0]
