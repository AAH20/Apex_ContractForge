import pytest
from apex_forge.oracle import Reference, event, normalize_row, validate_event
from apex_forge.corpus import U32, U64, scenarios, random_events
from apex_forge.proofs import require_counter_proof


def model():
    value = Reference(); value.step(event(recover=1)); return value


def test_unsent_terminal_does_not_release_and_payload_stays_stable():
    value = model(); first = value.step(event(valid=1, out_ready=0))
    stalled = value.step(event(out_ready=0))
    terminal = value.step(event(terminal_valid=1, terminal_id=1, out_ready=0))
    assert first[2:6] == stalled[2:6] == terminal[2:6]
    assert terminal[7] == 1 and terminal[9] == 9


def test_same_cycle_transmit_terminal_retires_once():
    value = model(); value.step(event(valid=1))
    first = value.step(event(terminal_valid=1, terminal_id=1))
    second = value.step(event(terminal_valid=1, terminal_id=1))
    assert first[7] == 0 and first[9] == 8
    assert second[7] == 0 and second[9] == 9


def test_invalid_fields_take_priority_over_duplicate_sequence():
    value = model(); value.step(event(valid=1))
    row = value.step(event(valid=1, frame_ok=0))
    assert row[6] == 1 and row[9] == 1


def test_idle_cycles_roll_rate_window():
    value = Reference(); value.step(event(recover=1, rate_limit=1)); value.step(event(valid=1))
    for _ in range(64): value.step(event())
    row = value.step(event(valid=1, seq=2))
    assert row[9] == 5 and row[7] == 2


def test_quantity_sum_exceeds_u32_without_wrapping():
    value = Reference(); value.step(event(recover=1, qty=U32, limit=U64))
    value.step(event(valid=1, qty=U32))
    row = value.step(event(valid=1, qty=U32, seq=2))
    assert row[7] == 2 * U32


def test_reset_holds_authority_and_clears_local_knowledge():
    value = model(); value.step(event(valid=1))
    row = value.step(event(reset=1))
    assert row[6] == 1 and row[7] == 0 and normalize_row(row)[1] == []


def test_conflicting_control_priority_is_recovery_first():
    value = Reference(); row = value.step(event(recover=1, terminal_valid=1, valid=1))
    assert row[6] == 0 and row[9] == 0 and row[1] == 0


def test_full_domain_local_counter_proofs():
    result = require_counter_proof()
    assert len(result["obligations"]) == 4
    assert all(x["status"] == "proved_under_assumptions" for x in result["obligations"])
    assert result["rtl_stateful_equivalence"] == "not_proved"


@pytest.mark.parametrize("value", [event(), event(valid=1)])
def test_invalid_trace_domains_are_rejected(value):
    value["seq"] = -1
    with pytest.raises(ValueError): validate_event(value)
    value["seq"] = 1; value["frame_ok"] = True
    with pytest.raises(ValueError): validate_event(value)


def test_all_named_scenarios_preserve_oracle_invariants():
    assert len(scenarios()) == 15
    for values in scenarios().values():
        reference = Reference()
        for value in values: reference.step(value)
    assert list(random_events(17, 100)) == list(random_events(17, 100))
