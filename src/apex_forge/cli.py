"""Explicit qualification commands; missing tools and unresolved obligations fail closed."""
import argparse
import json
import sys
from pathlib import Path
from .contract import load, digest
from .compiler import compile_to
from .proofs import require_counter_proof
from .qualification import qualify
from .evidence import export_atlas, validate_evidence


def main(argv=None):
    parser = argparse.ArgumentParser(prog="apex-forge")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check"); check.add_argument("contract", nargs="?")
    compile = commands.add_parser("compile"); compile.add_argument("contract", nargs="?")
    compile.add_argument("--output", required=True, type=Path)
    compile.add_argument("--backend", choices=["cpp", "sv", "both"], default="both")
    compile.add_argument("--variant", choices=["baseline", "narrow-counters"], default="baseline")
    commands.add_parser("prove-counters")
    qualification = commands.add_parser("qualify")
    qualification.add_argument("--output", required=True, type=Path)
    qualification.add_argument("--steps", type=int, default=2000)
    qualification.add_argument("--seeds", default="17,29,53")
    validation = commands.add_parser("validate-evidence"); validation.add_argument("directory", type=Path)
    exporter = commands.add_parser("export-atlas"); exporter.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            contract = load(args.contract); result = {"supported": True, "contract_sha256": digest(contract), "scope": "frozen Tick-compatible profile only"}
        elif args.command == "compile":
            result = compile_to(load(args.contract), args.output, args.backend, args.variant)
        elif args.command == "prove-counters": result = require_counter_proof()
        elif args.command == "qualify":
            seeds = tuple(int(x) for x in args.seeds.split(",")); report = qualify(args.output, seeds, args.steps, progress=lambda message: print(message, file=sys.stderr, flush=True))
            result = {key: report[key] for key in ("status", "cycles_per_backend", "backend_count", "matching_backend_transitions", "scenario_count", "counter_narrowing", "physical_latency_ns", "pareto_improvement")}
        elif args.command == "validate-evidence":
            errors = validate_evidence(args.directory); result = {"consistent": not errors, "errors": errors, "authenticated_custody": False}
            print(json.dumps(result, indent=2)); return 2 if errors else 0
        else:
            record = export_atlas(args.directory); result = {"record": str(args.directory / "run.json"), "method": record["measurement"]["method"], "physical_latency_ns": None}
        print(json.dumps(result, indent=2, allow_nan=False)); return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, AssertionError) as error:
        print(json.dumps({"error": str(error)})); return 2


if __name__ == "__main__":
    raise SystemExit(main())
