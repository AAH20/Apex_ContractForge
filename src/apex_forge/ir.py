"""Typed pure guards plus a fixed, documented ordered-effect program."""
from dataclasses import dataclass
from .contract import digest, validate

SYMBOLS = {
    "frame_ok": (1, "e.frame_ok", "frame_ok"),
    "input_epoch": (32, "e.epoch", "in_epoch"),
    "epoch": (32, "s.epoch", "epoch"),
    "instrument": (16, "e.instrument", "in_instrument"),
    "price": (32, "e.price", "in_price"),
    "quantity": (32, "e.qty", "in_qty"),
    "threshold": (32, "s.threshold", "threshold"),
    "order_quantity": (32, "s.order_qty", "order_qty"),
    "exposure": (64, "s.exposure", "exposure"),
    "max_exposure": (64, "s.max_exposure", "max_exposure"),
    "effective_rate": (32, "effective_rate", "effective_rate"),
    "rate_limit": (32, "s.rate_limit", "rate_limit"),
    "sequence": (64, "e.seq", "in_seq"),
    "expected": (64, "s.expected", "expected"),
    "next_id": (64, "s.next_id", "next_id"),
}


@dataclass(frozen=True)
class Expr:
    op: str
    args: tuple
    bits: int

    def json(self):
        return {"op": self.op, "bits": self.bits,
                "args": [a.json() if isinstance(a, Expr) else a for a in self.args]}


def ref(name):
    return Expr("ref", (name,), SYMBOLS[name][0])


def const(value, bits):
    if type(value) is not int or not 0 <= value < (1 << bits):
        raise ValueError("constant outside bit-vector domain")
    return Expr("const", (value,), bits)


def operation(op, *args):
    if op in {"or", "not"}:
        if not args or any(x.bits != 1 for x in args) or (op == "not" and len(args) != 1):
            raise ValueError("Boolean operation type mismatch")
        bits = 1
    elif op in {"eq", "ne", "lt", "gt", "ge"}:
        if len(args) != 2 or args[0].bits != args[1].bits:
            raise ValueError("comparison type mismatch")
        bits = 1
    elif op == "add_widened":
        if len(args) != 2:
            raise ValueError("addition arity mismatch")
        bits = max(x.bits for x in args) + 1
    else:
        raise ValueError("unsupported IR operation")
    return Expr(op, tuple(args), bits)


def zero_extend(value, bits):
    if bits <= value.bits:
        raise ValueError("zero extension must increase width")
    return Expr("zero_extend", (value,), bits)


def emit(expr, backend, mutation=None):
    if backend not in {"cpp", "sv"}:
        raise ValueError("unsupported backend")
    if expr.op == "ref":
        return SYMBOLS[expr.args[0]][1 if backend == "cpp" else 2]
    if expr.op == "const":
        value = expr.args[0]
        return f"UINT64_C({value})" if backend == "cpp" else f"{expr.bits}'d{value}"
    args = [emit(x, backend, mutation) for x in expr.args]
    if expr.op == "zero_extend":
        if backend == "cpp":
            return f"static_cast<unsigned __int128>({args[0]})"
        return "{" + f"{expr.bits - expr.args[0].bits}'d0, {args[0]}" + "}"
    if expr.op == "not":
        return f"(!{args[0]})"
    if expr.op == "or":
        return "(" + " || ".join(args) + ")"
    if expr.op == "add_widened":
        if mutation == "wrap_exposure32":
            raw = f"({args[0]} + {args[1]})"
            return f"static_cast<uint32_t>{raw}" if backend == "cpp" else f"({raw} & 64'hffffffff)"
        if backend == "cpp":
            return f"(static_cast<unsigned __int128>({args[0]}) + static_cast<unsigned __int128>({args[1]}))"
        widened = ["{" + f"{expr.bits - x.bits}'d0, {a}" + "}" for x, a in zip(expr.args, args)]
        return "(" + " + ".join(widened) + ")"
    symbol = {"eq": "==", "ne": "!=", "lt": "<", "gt": ">", "ge": ">="}[expr.op]
    return f"({args[0]} {symbol} {args[1]})"


def build(contract):
    validate(contract)
    eq = lambda name, value: operation("eq", ref(name), const(value, SYMBOLS[name][0]))
    invalid = [operation("not", ref("frame_ok")), operation("ne", ref("input_epoch"), ref("epoch")),
               operation("ge", ref("instrument"), const(8, 16)), eq("price", 0), eq("quantity", 0)]
    add = operation("add_widened", ref("exposure"), ref("order_quantity"))
    # Extend the limit explicitly so the typed guard compares equal widths.
    guards = {
        "invalid_fields": operation("or", *invalid),
        "duplicate_sequence": operation("lt", ref("sequence"), ref("expected")),
        "sequence_gap": operation("or", operation("ne", ref("sequence"), ref("expected")), eq("expected", (1 << 64) - 1)),
        "strategy_reject": operation("or", operation("gt", ref("price"), ref("threshold")), operation("lt", ref("quantity"), ref("order_quantity"))),
        "rate_reject": operation("ge", ref("effective_rate"), ref("rate_limit")),
        "exposure_reject": operation("gt", add, zero_extend(ref("max_exposure"), 65)),
        "identity_exhausted": eq("next_id", (1 << 64) - 1),
    }
    return {
        "ir_version": "0.1.0", "contract_sha256": digest(contract),
        "guards": {name: value.json() for name, value in guards.items()},
        "exposure_sum": add.json(),
        "effects": ["reset overrides normal transition", "sample readiness from pre-state", "complete previous output handshake",
                    "advance every-cycle window", "recovery else terminal else accepted quote", "observe post-state"],
        "rate_bits": 32, "window_bits": 32,
        "stateful_commit_schedule": "fixed; no retiming",
    }, guards, add
