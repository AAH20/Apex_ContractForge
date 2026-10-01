"""Profile-specific code generation, with source-bound manifests and proof-gated narrowing."""
import hashlib
import json
from importlib.resources import files
from pathlib import Path
from . import __version__
from .contract import digest, validate
from .ir import build, emit, operation, ref
from .proofs import require_counter_proof

MUTATIONS = ("wrap_exposure32", "retire_unsent", "event_only_window", "ignore_epoch",
             "unstable_output", "terminal_over_recovery", "ignore_exposure_limit")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def generate(contract, backend, variant="baseline", mutation=None):
    validate(contract)
    if backend not in {"cpp", "sv"} or variant not in {"baseline", "narrow-counters"}:
        raise ValueError("unsupported backend or variant")
    if mutation is not None and mutation not in MUTATIONS:
        raise ValueError("unknown negative-control mutation")
    proof = require_counter_proof() if variant == "narrow-counters" else None
    ir, guards, exposure_sum = build(contract)
    if variant == "narrow-counters":
        ir["rate_bits"], ir["window_bits"] = 7, 6
    if mutation == "ignore_epoch":
        guards["invalid_fields"] = operation("or", *[x for x in guards["invalid_fields"].args if x.op != "ne"])
    ir["guards"] = {name: value.json() for name, value in guards.items()}
    ir["negative_control_mutation"] = mutation
    replacements = {name.upper(): emit(expr, backend, mutation)[1:-1] for name, expr in guards.items()}
    total = emit(exposure_sum, backend, mutation)
    replacements["EXPOSURE_REJECT"] = "false" if backend == "cpp" else "1'b0"
    if mutation != "ignore_exposure_limit":
        limit = "static_cast<unsigned __int128>(s.max_exposure)" if backend == "cpp" else "{1'b0, max_exposure}"
        replacements["EXPOSURE_REJECT"] = f"({total} > {limit})"
    replacements.update({
        "RATE_DECL": "uint8_t" if variant == "narrow-counters" else "uint32_t",
        "WINDOW_DECL": "uint8_t" if variant == "narrow-counters" else "uint32_t",
        "RATE_RANGE": "6:0" if variant == "narrow-counters" else "31:0",
        "WINDOW_RANGE": "5:0" if variant == "narrow-counters" else "31:0",
        "TERMINAL_SENT": "true" if backend == "cpp" else "1'b1",
        "WINDOW_GATE": "true" if backend == "cpp" else "1'b1",
        "RECOVERY_GATE": "e.recover" if backend == "cpp" else "recover",
        "STALL_MUTATION": "",
        "EXPOSURE_UPDATE": "s.exposure + s.order_qty" if backend == "cpp" else "exposure + order_qty",
    })
    if mutation != "retire_unsent":
        replacements["TERMINAL_SENT"] = "s.pending[slot].sent" if backend == "cpp" else "(sent[k] || (out_valid && out_ready && out_order_id==identities[k]))"
    if mutation == "event_only_window":
        replacements["WINDOW_GATE"] = "(e.valid && ready)" if backend == "cpp" else "(in_valid && in_ready)"
    if mutation == "terminal_over_recovery":
        replacements["RECOVERY_GATE"] = "(e.recover && !e.terminal_valid)" if backend == "cpp" else "(recover && !terminal_valid)"
    if mutation == "unstable_output":
        replacements["STALL_MUTATION"] = "if(s.out_valid && !e.out_ready) ++s.out_price;" if backend == "cpp" else "if(out_valid && !out_ready) out_price<=out_price+1;"
    if mutation == "wrap_exposure32":
        replacements["EXPOSURE_UPDATE"] = "static_cast<uint32_t>(s.exposure + s.order_qty)" if backend == "cpp" else "((exposure + order_qty) & 64'hffffffff)"
    template = files("apex_forge").joinpath(f"templates/core.{backend}.in").read_text()
    for key, value in replacements.items():
        template = template.replace("@@" + key + "@@", value)
    if "@@" in template:
        raise RuntimeError("unresolved code-generation placeholder")
    lineage = {"variant": variant, "mutation": mutation, "negative_control": mutation is not None,
               "stateful_retiming": False, "rate_logical_bits": ir["rate_bits"], "window_logical_bits": ir["window_bits"],
               "rtl_declared_counter_bits_saved": 51 if variant == "narrow-counters" else 0,
               "physical_area_reduction": None, "proof": proof}
    return template, ir, lineage


def compile_to(contract, output, backend="both", variant="baseline", mutation=None):
    if backend not in {"cpp", "sv", "both"}:
        raise ValueError("unsupported backend")
    directory = Path(output)
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("output must be absent or empty")
    backends = ("cpp", "sv") if backend == "both" else (backend,)
    products = {b: generate(contract, b, variant, mutation) for b in backends}
    directory.mkdir(parents=True, exist_ok=True)
    generated = []
    for b, (source, ir, lineage) in products.items():
        name = "core.cpp" if b == "cpp" else "core.sv"
        (directory / name).write_text(source)
        generated.append({"path": name, "sha256": sha(directory / name)})
    template_hashes = {b: hashlib.sha256(files("apex_forge").joinpath(f"templates/core.{b}.in").read_bytes()).hexdigest() for b in backends}
    manifest = {"compiler_version": __version__, "contract_sha256": digest(contract), "generated": generated,
                "template_sha256": template_hashes, "ir": ir, "lineage": lineage}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
