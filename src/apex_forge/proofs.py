"""Local SMT obligations; deliberately no complete stateful RTL proof claim."""


def prove_counter_narrowing(timeout_ms=5000):
    try:
        import z3
    except ImportError as error:
        raise RuntimeError("z3-solver is required; a missing proof dependency cannot silently pass") from error
    w, r = z3.BitVecs("window rate", 32)
    accept, recover = z3.Bools("accept recover")
    rollover = w == 63
    next_w = z3.If(recover, z3.BitVecVal(0, 32), z3.If(rollover, z3.BitVecVal(0, 32), w + 1))
    effective = z3.If(rollover, z3.BitVecVal(0, 32), r)
    next_r = z3.If(recover, z3.BitVecVal(0, 32), z3.If(accept, effective + 1, effective))
    invariant = z3.And(z3.ULT(w, 64), z3.ULE(r, w + 1))
    obligations = {
        "reset_initialization": z3.Not(z3.And(z3.ULT(z3.BitVecVal(0, 32), 64), z3.ULE(z3.BitVecVal(0, 32), 1))),
        "counter_invariant_inductive_step": z3.And(invariant, z3.Not(z3.And(z3.ULT(next_w, 64), z3.ULE(next_r, next_w + 1)))),
        "rate_7bit_preserves_value": z3.And(invariant, z3.ZeroExt(25, z3.Extract(6, 0, next_r)) != next_r),
        "window_6bit_preserves_value": z3.And(invariant, z3.ZeroExt(26, z3.Extract(5, 0, next_w)) != next_w),
    }
    results = []
    for name, bad in obligations.items():
        solver = z3.Solver(); solver.set(timeout=timeout_ms); solver.add(bad)
        outcome = solver.check()
        item = {"id": name, "status": "proved_under_assumptions" if outcome == z3.unsat else "counterexample" if outcome == z3.sat else "unknown",
                "query_smt2": solver.to_smt2()}
        if outcome == z3.sat:
            item["counterexample"] = str(solver.model())
        elif outcome == z3.unknown:
            item["reason"] = solver.reason_unknown()
        results.append(item)
    return {"solver": "Z3", "solver_version": z3.get_version_string(), "timeout_ms": timeout_ms,
            "scope": "32-bit local counter transition and inductive invariant; accept/recover are unconstrained Boolean inputs",
            "assumptions": ["window starts at zero", "rate starts at zero", "window advances every non-reset cycle",
                            "at most one reservation per cycle", "rollover precedes reservation", "recovery resets both counters"],
            "rtl_stateful_equivalence": "not_proved", "physical_timing": "not_measured", "obligations": results}


def require_counter_proof(timeout_ms=5000):
    report = prove_counter_narrowing(timeout_ms)
    required = {"reset_initialization", "counter_invariant_inductive_step", "rate_7bit_preserves_value", "window_6bit_preserves_value"}
    obligations = report["obligations"]
    if len(obligations) != 4 or {x.get("id") for x in obligations} != required or any(x.get("status") != "proved_under_assumptions" for x in obligations):
        raise RuntimeError("counter narrowing blocked: required SMT result is not proved")
    return report


def same_proof(left, right):
    """Compare expanded query ASTs; printer-local let names are not semantic identity.

    Structural equality is intentional: comparing logical equivalence would accept
    any substituted unsatisfiable query, including a trivial assertion of false.
    """
    import z3
    if {k: v for k, v in left.items() if k != "obligations"} != {k: v for k, v in right.items() if k != "obligations"}:
        return False
    if len(left["obligations"]) != len(right["obligations"]):
        return False
    try:
        for a, b in zip(left["obligations"], right["obligations"]):
            if {k: v for k, v in a.items() if k != "query_smt2"} != {k: v for k, v in b.items() if k != "query_smt2"}:
                return False
            parsed_a, parsed_b = z3.parse_smt2_string(a["query_smt2"]), z3.parse_smt2_string(b["query_smt2"])
            if len(parsed_a) != len(parsed_b) or not all(z3.eq(x, y) for x, y in zip(parsed_a, parsed_b)):
                return False
    except z3.Z3Exception:
        return False
    return True
