"""Compile and execute native/RTL candidates against a pinned independent oracle."""
import gzip
import hashlib
import json
import platform
import shutil
import subprocess
import tempfile
from contextlib import ExitStack
from importlib.resources import files
from pathlib import Path
from .compiler import MUTATIONS, compile_to, sha
from .contract import load, digest
from .corpus import write_trace
from .oracle import Reference, normalize_row, parse_event
from .proofs import require_counter_proof


def run(command, timeout=180):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"tool failed ({result.returncode}): {command[0]}\n{result.stderr[-4000:]}\n{result.stdout[-1000:]}")
    return result.stdout


def compiler_path():
    clt = Path("/Library/Developer/CommandLineTools/usr/bin/clang++")
    if platform.system() == "Darwin" and clt.is_file():
        return str(clt)
    xcode = Path("/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang++")
    if platform.system() == "Darwin" and xcode.is_file():
        return str(xcode)
    value = shutil.which("clang++") or shutil.which("g++")
    if value is None:
        raise RuntimeError("clang++ or g++ is required; native qualification cannot silently skip")
    return value


def prepare_cpu(source, directory, cxx):
    binary = directory / "core.native"
    flags = ["-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror"]
    if platform.system() == "Darwin":
        sdk = Path(run(["xcrun", "--sdk", "macosx", "--show-sdk-path"]).strip())
        clt_sdk = Path("/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk")
        if not (sdk / "usr/include/c++/v1/array").is_file() and (clt_sdk / "usr/include/c++/v1/array").is_file():
            sdk = clt_sdk
        flags += ["-isysroot", str(sdk)]
        headers = sdk / "usr/include/c++/v1"
        if headers.is_dir():
            flags += ["-isystem", str(headers)]
    run([cxx, *flags, str(source), "-o", str(binary)])
    return binary, {"compiler": cxx, "flags": flags, "executable_sha256": sha(binary)}


def prepare_rtl(source, directory, module):
    if not shutil.which("iverilog") or not shutil.which("vvp"):
        raise RuntimeError("iverilog and vvp are required; RTL qualification cannot silently skip")
    tb = directory / "trace_tb.sv"
    tb.write_text(files("apex_forge").joinpath("templates/trace_tb.sv.in").read_text().replace("@@MODULE@@", module))
    binary = directory / "core.vvp"
    flags = ["-g2012", "-s", "core_tb"]
    run(["iverilog", *flags, "-o", str(binary), str(source), str(tb)])
    return binary, {"compiler": "iverilog", "flags": flags, "testbench_sha256": sha(tb), "executable_sha256": sha(binary)}


def execute(binary, backend, inputs, output):
    command = [str(binary), str(inputs), str(output)] if backend == "cpp" else ["vvp", str(binary), f"+input={inputs}", f"+output={output}"]
    run(command, timeout=600)


def compare_trace(inputs, observations, archive=None):
    reference = Reference(); count = 0; first = None
    archive_files = {}
    with ExitStack() as stack:
        stimulus = stack.enter_context(inputs.open())
        streams = {name: stack.enter_context(path.open()) for name, path in observations.items()}
        if archive:
            archive.mkdir(parents=True, exist_ok=True)
            # Gzip mtime=0 keeps retained trace bytes reproducible.
            for name in ["oracle", *streams]:
                raw = stack.enter_context((archive / f"{name}.txt.gz").open("wb"))
                archive_files[name] = stack.enter_context(gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename=""))
            atlas = stack.enter_context((archive / "atlas-trace.json").open("w")); atlas.write("[")
        for line in stimulus:
            value = parse_event(line); expected = reference.step(value)
            wanted = normalize_row(expected)
            if archive:
                archive_files["oracle"].write((" ".join(map(str, expected)) + "\n").encode())
                atlas.write(("," if count else "") + json.dumps(expected[:10], separators=(",", ":")))
            for name, stream in streams.items():
                raw_row = stream.readline()
                try:
                    actual = [int(x) for x in raw_row.split()]
                    equal = normalize_row(actual) == wanted
                except (ValueError, TypeError):
                    actual = raw_row.rstrip(); equal = False
                if archive:
                    archive_files[name].write(raw_row.encode())
                if not equal and first is None:
                    first = {"cycle": count, "backend": name, "event": value, "expected": expected, "actual": actual}
            count += 1
        for name, stream in streams.items():
            if stream.readline() and first is None:
                first = {"cycle": count, "backend": name, "reason": "extra observation rows"}
        if archive:
            atlas.write("]\n")
    return {"cycles": count, "status": "passed" if first is None else "mismatch", "first_counterexample": first}


def gzip_copy(source, destination):
    with source.open("rb") as stream, destination.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as target:
            shutil.copyfileobj(stream, target)


def qualify(output, seeds=(17, 29, 53), steps=2000, progress=lambda message: None):
    if type(steps) is not int or not 1 <= steps <= 1_000_000:
        raise ValueError("steps must be within 1..1000000")
    if not seeds or len(set(seeds)) != len(seeds) or any(type(x) is not int or not 0 <= x < (1 << 64) for x in seeds):
        raise ValueError("seeds must be distinct unsigned 64-bit integers")
    if len(seeds) * steps > 1_000_000:
        raise ValueError("randomized trace budget exceeds one million cycles")
    root = Path(output)
    if root.exists() and any(root.iterdir()):
        raise ValueError("output must be absent or empty")
    root.mkdir(parents=True, exist_ok=True)
    from .evidence import capture_provenance, write_manifest
    capture_provenance(root)
    progress("Checking local SMT obligations and pinned reference identity")
    contract = load(); proof = require_counter_proof(); cxx = compiler_path()
    reference_root = files("apex_forge").joinpath("reference")
    provenance = json.loads(reference_root.joinpath("provenance.json").read_text())
    for name, source in provenance["files"].items():
        if hashlib.sha256(reference_root.joinpath(name).read_bytes()).hexdigest() != source["sha256"]:
            raise RuntimeError("pinned independent reference hash mismatch")
    (root / "contract.json").write_text(json.dumps(contract, indent=2) + "\n")
    (root / "proofs.json").write_text(json.dumps(proof, indent=2) + "\n")
    config = {"seeds": list(seeds), "steps_per_seed": steps, "profile": contract["id"], "variants": ["baseline", "narrow-counters"]}
    (root / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    inventory = {"environment": "native functional replay and Icarus RTL simulation", "host_machine": platform.machine(),
                 "host_system": platform.system(), "python_version": platform.python_version(), "cpu_model": None,
                 "cxx_version": run([cxx, "--version"]).splitlines()[0],
                 "iverilog_version": run(["iverilog", "-V"]).splitlines()[0], "physical_board": None}
    (root / "inventory.json").write_text(json.dumps(inventory, indent=2) + "\n")
    builds = {}; manifests = {}; mutations = []
    with tempfile.TemporaryDirectory(prefix="apex-forge-") as temp:
        temporary = Path(temp); inputs = temporary / "inputs.txt"
        progress("Generating deterministic corpus and randomized stimulus")
        cycles, cases = write_trace(inputs, seeds, steps)
        gzip_copy(inputs, root / "stimulus.txt.gz")
        (root / "cases.json").write_text(json.dumps(cases, indent=2) + "\n")
        observations = {}
        for variant in ("baseline", "narrow-counters"):
            generated = root / "generated" / variant
            manifests[variant] = compile_to(contract, generated, variant=variant)
            for backend in ("cpp", "sv"):
                name = variant + "-" + backend
                progress(f"Building and executing {name}: {cycles} cycles")
                working = temporary / name; working.mkdir()
                source = generated / ("core.cpp" if backend == "cpp" else "core.sv")
                binary, metadata = prepare_cpu(source, working, cxx) if backend == "cpp" else prepare_rtl(source, working, "apex_forge_core")
                builds[name] = metadata
                result_path = working / "observations.txt"; execute(binary, backend, inputs, result_path)
                observations[name] = result_path
        working = temporary / "reference-rtl"; working.mkdir()
        progress(f"Executing pinned independent reference RTL: {cycles} cycles")
        source = working / "reference.sv"; source.write_bytes(reference_root.joinpath("apex_tick_core.sv").read_bytes())
        binary, builds["reference-rtl"] = prepare_rtl(source, working, "apex_tick_core")
        result_path = working / "observations.txt"; execute(binary, "sv", inputs, result_path)
        observations["reference-rtl"] = result_path
        progress("Comparing complete state observations across five backends")
        functional = compare_trace(inputs, observations, root / "traces")
        if functional["status"] != "passed":
            (root / "failure.json").write_text(json.dumps(functional, indent=2) + "\n")
            raise RuntimeError(f"functional qualification failed; inspect {root / 'failure.json'}")
        mutation_inputs = temporary / "mutations.txt"
        mutation_cycles, _ = write_trace(mutation_inputs, (), steps, randomized=False)
        gzip_copy(mutation_inputs, root / "mutation-stimulus.txt.gz")
        for mutation in MUTATIONS:
            progress(f"Checking negative control on both backends: {mutation}")
            generated = root / "negative-controls" / mutation
            compile_to(contract, generated, mutation=mutation)
            for backend in ("cpp", "sv"):
                name = mutation + "-" + backend
                working = temporary / name; working.mkdir()
                source = generated / ("core.cpp" if backend == "cpp" else "core.sv")
                binary, metadata = prepare_cpu(source, working, cxx) if backend == "cpp" else prepare_rtl(source, working, "apex_forge_core")
                result_path = working / "observations.txt"; execute(binary, backend, mutation_inputs, result_path)
                result = compare_trace(mutation_inputs, {backend: result_path})
                counterexample = result["first_counterexample"]
                if counterexample is None:
                    raise RuntimeError(f"negative control escaped detection: {name}")
                # A shortest prefix of this fixed replay reaches the first observed divergence.
                prefix = generated / f"counterexample-{backend}.txt"
                with mutation_inputs.open() as source_trace, prefix.open("w") as target:
                    for i, line in enumerate(source_trace):
                        if i > counterexample["cycle"]: break
                        target.write(line)
                item = {"mutation": mutation, "backend": backend, "status": "detected", "checked_cycles": mutation_cycles,
                        "counterexample": counterexample, "replay": str(prefix.relative_to(root)),
                        "minimality": "first divergent prefix of this corpus; not globally minimized"}
                mutations.append(item)
    build = {"contract_sha256": digest(contract), "manifests": manifests, "builds": builds, "reference": provenance,
             "scope": "functional CPU and RTL execution; executable hashes retained, temporary executables removed"}
    (root / "build.json").write_text(json.dumps(build, indent=2) + "\n")
    report = {"schema_version": "0.1.0", "status": "passed", "contract_sha256": digest(contract),
              "cycles_per_backend": cycles, "backend_count": len(observations), "matching_backend_transitions": cycles * len(observations),
              "scenario_count": len(cases) - len(seeds), "randomized_cycles": steps * len(seeds), "seeds": list(seeds),
              "functional": functional, "mutations": mutations, "counter_narrowing": {"rate_bits": [32, 7], "window_bits": [32, 6],
              "rtl_declared_bits_saved": 51, "physical_area_saved": None, "timing_improvement_ns": None},
              "formal_scope": "local counter invariant and value-preservation obligations only",
              "rtl_stateful_equivalence": "not_proved", "physical_latency_ns": None, "pareto_improvement": "not_measured"}
    (root / "qualification.json").write_text(json.dumps(report, indent=2) + "\n")
    write_manifest(root)
    from .evidence import validate_evidence
    progress("Replaying retained evidence independently")
    errors = validate_evidence(root)
    if errors:
        raise RuntimeError("evidence self-check failed: " + "; ".join(errors))
    return report
