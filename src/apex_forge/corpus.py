"""Named adversarial scenarios and reproducible randomized valid-domain events."""
import random
from .oracle import Reference, event

U32 = (1 << 32) - 1
U64 = (1 << 64) - 1


def scenarios():
    start = lambda **kw: event(recover=1, **kw)
    quote = lambda seq=1, **kw: event(valid=1, seq=seq, **kw)
    term = lambda identity=1, **kw: event(terminal_valid=1, terminal_id=identity, **kw)
    return {
        "strategy_and_quantity": [start(), quote(price=101), quote(2, qty=0)],
        "stall_and_unsent_terminal": [start(), quote(out_ready=0), event(out_ready=0), term(out_ready=0), event(out_ready=0), event(), term()],
        "same_cycle_tx_and_terminal": [start(), quote(), term()],
        "duplicate_terminal": [start(), quote(), event(), term(), term()],
        "corrupt_duplicate_priority": [start(), quote(), quote(1, frame_ok=0)],
        "gap_and_hold": [start(), quote(3), quote(1), start(epoch=2), quote(epoch=2)],
        "epoch_validation": [start(), quote(epoch=0)],
        "idle_window_rollover": [start(rate_limit=1), quote(), *[event() for _ in range(64)], quote(2)],
        "wide_quantity_accounting": [start(qty=U32, limit=U64, rate_limit=100), *[quote(i, qty=U32) for i in range(1, 4)], term(1), term(2), term(3)],
        "ledger_capacity_and_reuse": [start(limit=100, rate_limit=100), *[quote(i) for i in range(1, 18)], term(1), quote(18)],
        "sequence_exhaustion": [start(seq=U64), quote(U64)],
        "reset_with_unknown_obligation": [start(), quote(), event(reset=1), start(epoch=2), quote(epoch=2)],
        "conflicting_recovery_and_terminal": [event(recover=1, terminal_valid=1, valid=1)],
        "exposure_limit": [start(qty=3, limit=3), quote(qty=3), quote(2, qty=3)],
        "invalid_recovery_and_strategy": [start(qty=0), start(), quote(qty=1, price=99), quote(2, price=101)],
    }


def random_events(seed, steps):
    rng = random.Random(seed)
    reference = Reference()
    for _ in range(steps):
        m = reference.model
        if rng.randrange(170) == 0:
            value = event(reset=1, out_ready=rng.randrange(2))
        elif m.hold and m.exposure == 0 and m.output is None:
            value = event(recover=1, epoch=m.epoch + 1, seq=max(1, m.expected), qty=rng.choice([1, 2, 3]),
                          limit=rng.choice([2, 8, 32]), rate_limit=rng.choice([1, 4, 16]))
        elif m.pending and rng.random() < .32:
            value = event(terminal_valid=1, terminal_id=rng.choice(list(m.pending)), epoch=m.epoch,
                          out_ready=int(rng.random() > .25))
        else:
            value = event(valid=int(rng.random() > .15), seq=m.expected, epoch=m.epoch,
                          price=rng.choice([0, 99, 100, 101]), qty=rng.choice([0, 1, 2, 3]),
                          instrument=rng.randrange(8), out_ready=int(rng.random() > .3))
            fault = rng.randrange(24)
            if fault == 0: value["frame_ok"] = 0
            elif fault == 1: value["seq"] = max(0, m.expected - 1)
            elif fault == 2: value["seq"] = m.expected + 1
            elif fault == 3: value["instrument"] = 8
            elif fault == 4: value["epoch"] = max(0, m.epoch - 1)
        reference.step(value)
        yield value


def write_trace(path, seeds, steps, randomized=True):
    from .oracle import FIELDS
    count = 0
    cases = []
    with path.open("w") as output:
        def write(name, values):
            nonlocal count
            first = count
            for value in [event(reset=1)]:
                output.write(" ".join(str(value[k]) for k in FIELDS) + "\n"); count += 1
            for value in values:
                output.write(" ".join(str(value[k]) for k in FIELDS) + "\n"); count += 1
            cases.append({"name": name, "start_cycle": first, "cycles": count - first})
        for name, values in scenarios().items():
            write(name, values)
        if randomized:
            for seed in seeds:
                write(f"random-seed-{seed}", random_events(seed, steps))
    return count, cases
