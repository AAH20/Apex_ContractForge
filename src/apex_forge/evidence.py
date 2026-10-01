"""Read-only retained-trace consistency checks and a simulation-only Atlas exporter."""
import gzip
import json
import subprocess
import re
from datetime import datetime, timezone
from pathlib import Path
from contextlib import ExitStack
from .compiler import MUTATIONS, sha, generate
from .contract import load, digest
from .oracle import Reference, normalize_row, parse_event
from .proofs import require_counter_proof


def write_manifest(root):
    artifacts = []
    resolved = root.resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name in {"evidence-manifest.json", "run.json"}:
            continue
        if not path.resolve().is_relative_to(resolved):
            raise ValueError("artifact escapes evidence root")
        artifacts.append({"path": str(path.relative_to(root)), "sha256": sha(path)})
    manifest = {"schema_version": "0.1.0", "identity_scope": "byte identity and local consistency; no authenticated custody", "artifacts": artifacts}
    (root / "evidence-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def validate_evidence(root):
    root = Path(root); errors = []; base = root.resolve()
    try:
        manifest = json.loads((root / "evidence-manifest.json").read_text())
        seen = set()
        for entry in manifest["artifacts"]:
            relative = entry["path"]; target = (root / relative).resolve()
            if relative in seen or Path(relative).is_absolute() or not target.is_relative_to(base):
                raise ValueError("duplicate or escaping artifact")
            seen.add(relative)
            if not target.is_file() or sha(target) != entry["sha256"]:
                raise ValueError("artifact hash mismatch: " + relative)
        present = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p.name not in {"evidence-manifest.json", "run.json"}}
        if seen != present:
            raise ValueError("unbound or missing evidence artifact")
        contract = load(root / "contract.json")
        report = json.loads((root / "qualification.json").read_text())
        if report["status"] != "passed" or report["contract_sha256"] != digest(contract):
            raise ValueError("invalid qualification status or contract binding")
        if report["physical_latency_ns"] is not None or report["pareto_improvement"] != "not_measured":
            raise ValueError("simulation evidence cannot carry physical performance claims")
        if report["rtl_stateful_equivalence"] != "not_proved":
            raise ValueError("local counter obligations cannot establish full RTL equivalence")
        proofs = json.loads((root / "proofs.json").read_text())
        required = {"reset_initialization", "counter_invariant_inductive_step", "rate_7bit_preserves_value", "window_6bit_preserves_value"}
        obligations = proofs["obligations"]
        if {x["id"] for x in obligations} != required or len(obligations) != 4 or any(x["status"] != "proved_under_assumptions" for x in obligations):
            raise ValueError("missing, duplicated or unresolved local proof obligation")
        regenerated_proof = require_counter_proof(proofs["timeout_ms"])
        if proofs != regenerated_proof:
            raise ValueError("retained proof does not match regenerated obligations, assumptions and solver")
        # Regenerate source from the supported contract; never execute customer-supplied code.
        for variant in ("baseline", "narrow-counters"):
            metadata = json.loads((root / "generated" / variant / "manifest.json").read_text())
            if metadata["contract_sha256"] != digest(contract) or metadata["lineage"]["negative_control"]:
                raise ValueError("generated candidate identity mismatch")
            for backend, suffix in (("cpp", "cpp"), ("sv", "sv")):
                expected, expected_ir, expected_lineage = generate(contract, backend, variant)
                if (root / "generated" / variant / f"core.{suffix}").read_text() != expected:
                    raise ValueError("generated source does not match frozen compiler semantics")
                if metadata["ir"] != expected_ir or metadata["lineage"] != expected_lineage:
                    raise ValueError("generated manifest does not match source semantics and proof scope")
                generated = {x["path"]: x["sha256"] for x in metadata["generated"]}
                if generated.get(f"core.{suffix}") != sha(root / "generated" / variant / f"core.{suffix}"):
                    raise ValueError("generated manifest source hash mismatch")
        variants = ("baseline-cpp", "baseline-sv", "narrow-counters-cpp", "narrow-counters-sv", "reference-rtl")
        reference = Reference(); count = 0
        with ExitStack() as stack:
            inputs = stack.enter_context(gzip.open(root / "stimulus.txt.gz", "rt"))
            streams = {name: stack.enter_context(gzip.open(root / "traces" / f"{name}.txt.gz", "rt")) for name in ("oracle", *variants)}
            for line in inputs:
                expected = normalize_row(reference.step(parse_event(line)))
                for name, stream in streams.items():
                    actual = normalize_row([int(x) for x in stream.readline().split()])
                    if actual != expected:
                        raise ValueError(f"retained {name} trace mismatch at cycle {count}")
                count += 1
            if any(stream.readline() for stream in streams.values()):
                raise ValueError("extra retained observation rows")
        if count != report["cycles_per_backend"] or report["backend_count"] != 5 or report["matching_backend_transitions"] != count * 5:
            raise ValueError("qualification cycle accounting mismatch")
        compact = json.loads((root / "traces/atlas-trace.json").read_text())
        if len(compact) != count:
            raise ValueError("Atlas trace length mismatch")
        with gzip.open(root / "traces/oracle.txt.gz", "rt") as oracle:
            if any(row != [int(x) for x in line.split()][:10] for row, line in zip(compact, oracle)):
                raise ValueError("Atlas trace does not match retained oracle")
        mutations = report["mutations"]
        if len(mutations) != len(MUTATIONS) * 2 or {(m["mutation"], m["backend"]) for m in mutations} != {(m, b) for m in MUTATIONS for b in ("cpp", "sv")}:
            raise ValueError("missing or duplicate negative control")
        for item in mutations:
            if item["status"] != "detected": raise ValueError("undetected negative control")
            replay = (root / item["replay"]).resolve()
            if not replay.is_relative_to(base): raise ValueError("counterexample replay escapes root")
            model = Reference(); row = None; cycle = -1; value = None
            for cycle, line in enumerate(replay.read_text().splitlines()):
                value = parse_event(line); row = model.step(value)
            counter = item["counterexample"]
            if cycle != counter["cycle"] or row != counter["expected"] or value != counter["event"]:
                raise ValueError("counterexample oracle or replay binding mismatch")
            if normalize_row(counter["actual"]) == normalize_row(row):
                raise ValueError("counterexample does not demonstrate divergence")
    except (OSError, ValueError, KeyError, TypeError, EOFError, json.JSONDecodeError, AssertionError, RuntimeError) as error:
        errors.append(str(error))
    return errors


def capture_provenance(root):
    repository = Path(__file__).resolve().parents[2]
    try:
        top = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=repository, text=True, stderr=subprocess.DEVNULL).strip()
        if Path(top).resolve() != repository.resolve():
            raise subprocess.CalledProcessError(1, "git rev-parse --show-toplevel")
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=repository, text=True))
    except subprocess.CalledProcessError:
        commit, dirty = None, None
    value = {"repository_url": "https://github.com/AAH20/Apex_ContractForge", "commit": commit, "dirty": dirty,
             "recorded_at": datetime.now(timezone.utc).isoformat(),
             "revision_scope": "working source revision at qualification start; null revision means unavailable"}
    (root / "provenance.json").write_text(json.dumps(value, indent=2) + "\n")


def export_atlas(root):
    root = Path(root)
    errors = validate_evidence(root)
    if errors: raise ValueError("evidence invalid: " + "; ".join(errors))
    if (root / "run.json").exists(): raise ValueError("Atlas run.json already exists")
    report = json.loads((root / "qualification.json").read_text())
    provenance = json.loads((root / "provenance.json").read_text())
    if not isinstance(provenance["commit"], str) or not re.fullmatch(r"[0-9a-f]{40}", provenance["commit"]) or type(provenance["dirty"]) is not bool:
        raise ValueError("Atlas measured records require an available source revision and dirty-state observation")
    provenance.pop("revision_scope")
    provenance["config_sha256"] = sha(root / "config.json"); provenance["sources"] = []
    artifacts = []
    roles = {"inventory.json": "platform_inventory", "build.json": "implementation", "contract.json": "workload",
             "config.json": "configuration", "stimulus.txt.gz": "stimulus_schedule", "traces/atlas-trace.json": "cycle_transition_trace"}
    for index, path in enumerate(sorted(p for p in root.rglob("*") if p.is_file())):
        relative = str(path.relative_to(root))
        identity = {"inventory.json": "inventory", "build.json": "build", "stimulus.txt.gz": "stimulus"}.get(relative, f"artifact-{index}")
        artifacts.append({"id": identity, "role": roles.get(relative, "qualification_artifact"), "location": relative,
                          "sha256": sha(path), "visibility": "public"})
    cycles = report["cycles_per_backend"]
    record = {"schema_version": "0.1.0", "run_id": "apex-forge-functional-" + sha(root / "config.json")[:16],
              "status": "valid", "claim_kind": "measured", "provenance": provenance,
              "workload": {"id": "apex.forge.tick.functional", "version": "0.1.0", "kind": "synthetic",
                           "spec_sha256": sha(root / "contract.json"), "input_sha256": sha(root / "stimulus.txt.gz"),
                           "rights": "public_redistributable", "semantics": "Normalized integer transition replay against independent Tick oracle; counts are stimulus cycles",
                           "frame_integrity_policy": "validate_before_action"},
              "platform": {"inventory_artifact": "inventory", "implementation_artifact": "build", "transport_backend": "normalized_event_replay", "backend_status": "simulated"},
              "evidence": {"implementation": "rtl_simulation", "environment": "simulator", "validation": "none", "validation_receipt": None},
              "measurement": {"method": "simulation", "start_boundary": "first normalized stimulus cycle", "stop_boundary": "last observed transition",
                              "clock_artifact": None, "calibration_artifact": None, "resolution_ns": None, "uncertainty_artifact": None,
                              "warmup_policy": "none; functional replay", "sampling_policy": "every cycle including idle, stalls and reset",
                              "sample_count": cycles},
              "traffic": {"schedule_artifact": "stimulus", "offered_count": cycles, "accepted_count": cycles, "completed_count": cycles,
                          "rejected_count": 0, "dropped_count": 0, "duplicate_output_count": 0, "wrong_output_count": 0, "unresolved_count": 0},
              "metrics": [{"id": "simulation.matched_transitions", "value": cycles, "unit": "count", "statistic": "total",
                           "population": "normalized functional stimulus cycles per checked backend, not network packets or orders", "direction": "context"}],
              "artifacts": artifacts,
              "limitations": ["Finite native and RTL functional replay; no FPGA deployment, physical latency, power or Pareto improvement measured.",
                              "Traffic accounting describes replay cycles, including resets and idle cycles; it does not describe accepted trading events.",
                              "Four local SMT obligations do not prove complete stateful RTL equivalence or physical timing.",
                              "Fifty-one fewer declared RTL counter bits are a source-level result, not measured LUT, area or latency savings.",
                              "frame_ok and host reconciliation are trusted external responsibilities; no MAC/PHY, wire decoder or exchange session is implemented.",
                              "Artifact hashes and local replay checking do not authenticate custody or independent review."]}
    (root / "run.json").write_text(json.dumps(record, indent=2) + "\n")
    return record
