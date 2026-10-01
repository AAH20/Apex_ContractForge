"""Wrapper around the independently maintained, pinned Apex_Tick dictionary oracle."""
from .reference.oracle import Oracle, stimulus

FIELDS = ("reset", "recover", "terminal_valid", "terminal_id", "valid", "frame_ok", "seq",
          "instrument", "price", "qty", "epoch", "limit", "rate_limit", "out_ready")
WIDTHS = (1, 1, 1, 64, 1, 1, 64, 16, 32, 32, 32, 64, 32, 1)


def event(**updates):
    value = {"reset": 0, **stimulus()}
    value.update(updates)
    validate_event(value)
    return value


def validate_event(value):
    if set(value) != set(FIELDS):
        raise ValueError("trace event has unknown or missing fields")
    for key, bits in zip(FIELDS, WIDTHS):
        if type(value[key]) is not int or not 0 <= value[key] < (1 << bits):
            raise ValueError(f"{key} outside u{bits} domain")


def parse_event(line):
    tokens = line.split()
    if len(tokens) != len(FIELDS) or any(not x.isascii() or not x.isdecimal() for x in tokens):
        raise ValueError("invalid unsigned stimulus row")
    value = dict(zip(FIELDS, map(int, tokens)))
    validate_event(value)
    return value


def normalize_row(row):
    if len(row) != 90:
        raise ValueError(f"observation has {len(row)} fields, expected 90")
    ledger = []
    for offset in range(26, 90, 4):
        occupied, sent, identity, quantity = row[offset:offset + 4]
        if occupied not in (0, 1) or sent not in (0, 1):
            raise ValueError("invalid ledger Boolean")
        if occupied:
            ledger.append((identity, quantity, sent))
    if len({x[0] for x in ledger}) != len(ledger):
        raise ValueError("duplicate live identity")
    return row[:26], sorted(ledger)


class Reference:
    def __init__(self):
        self.model = Oracle()

    def step(self, value):
        validate_event(value)
        m = self.model
        if value["reset"]:
            ready = int(not m.hold and not value["terminal_valid"] and not value["recover"] and (m.output is None or value["out_ready"]))
            self.model = m = Oracle()
            observed = {"ready": ready, "out_valid": 0, "order": (0, 0, 0, 0), "hold": 1, "exposure": 0, "expected": 1, "status": 0}
        else:
            observed = m.step(value)
        row = [observed["ready"], observed["out_valid"], *observed["order"], int(observed["hold"]), observed["exposure"], observed["expected"], observed["status"],
               m.epoch, m.threshold, m.order_qty, m.max_exposure, m.rate_limit, m.rate, m.window, m.next_id,
               *[m.book.get(i, 0) for i in range(8)]]
        entries = [(identity, item["qty"], int(item["sent"])) for identity, item in sorted(m.pending.items())]
        for identity, quantity, sent in entries:
            row.extend([1, sent, identity, quantity])
        row.extend([0, 0, 0, 0] * (16 - len(entries)))
        # These checks are additional oracle invariants, not a full formal proof.
        if m.exposure != sum(item["qty"] for item in m.pending.values()):
            raise AssertionError("oracle obligation accounting mismatch")
        if not (0 <= m.window < 64 and 0 <= m.rate <= m.window + 1):
            raise AssertionError("oracle counter invariant mismatch")
        return row
