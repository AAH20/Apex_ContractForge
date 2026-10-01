# Frozen Tick-compatible semantics

The accepted JSON contract is `contracts/tick-compatible.json`. V0 accepts its exact canonical scalar values and fields; the schema uses `const` intentionally. It is a profile compiler, not a general-purpose language implementation. Packaged and repository copies are checked in tests.

## Types and capacity

Sequence and identity are u64; instrument is u16; price, quantity, epoch and rate limit are u32; configured exposure limit is u64. State has eight instrument prices, sixteen pending identities and one output. Comparison is unsigned. Invalid field values are rejected before compilation/replay.

The quantity guard widens both operands and the limit to 65 bits. Reachable exposure is at most sixteen u32 quantities, so this agrees with the original Tick expression on reachable states while making the arithmetic intent explicit. The C++ lowering uses unsigned `__int128`; the supported compiler requirement is explicit.

## Phase order

1. Sample pre-transition readiness: authority active, no recovery or terminal event, and output empty or downstream ready.
2. If reset is asserted, restore local initial state and skip normal processing. The observation retains sampled pre-state readiness; that signal is not a quote-acceptance assertion during reset.
3. Otherwise complete an existing output handshake and mark its pending identity transmitted.
4. Advance the rate window, rolling the count to zero at 64 cycles.
5. Process recovery; otherwise terminal; otherwise a valid quote when the sampled readiness permits it.
6. Observe post-transition state and output. Inactive output fields are normalized to zero. Unoccupied stale ledger payloads are ignored; live entries are compared by identity, quantity and transmitted status.

For quotes, field/integrity validation precedes duplicate detection. A valid in-sequence quote advances expected sequence and the stored price even when its strategy or risk decision rejects an order. Successful admission reserves all relevant state together. A matching terminal in the same cycle as output handoff can retire that newly transmitted obligation.

## Time and counter narrowing

The inductive counter invariant is `0 <= window < 64` and `rate <= window + 1`. The proof permits an unconstrained Boolean reservation flag, which is a conservative superset of the actual admission conditions. Rollover precedes any reservation; recovery resets both counters.

These assumptions permit a 6-bit window and 7-bit rate counter without changing their values. C++ uses u8 storage for each narrowed counter; the logical width declaration is not a C++ object-size or packing claim. RTL declarations save 51 source-level bits relative to two 32-bit declarations. Actual synthesis may already infer smaller structures.

Changing the physical frequency changes the real duration of the 64-cycle window. No wall-clock period is declared in this simulation contract. Retiming, rate-window redesign, protocol decoding, terminal session binding and partial fills are outside v0.

## Authority and external obligations

Reset holds new-admission authority and clears local state. Recovery needs held authority, zero local exposure, no output remaining after the handshake phase, a newer epoch and positive quantity, exposure/rate limits and starting sequence. The reference permits already reserved output to handshake during hold; the compiler preserves that policy.

External frame integrity and post-reset reconciliation are trusted adapter responsibilities. Clearing the local ledger cannot establish that an external order no longer exists. The existing terminal interface carries no epoch. A production-oriented replacement needs separately versioned semantics and evidence.
