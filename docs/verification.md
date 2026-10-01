# Verification and evidence boundaries

## Independent reference

The dictionary oracle and original RTL are pinned byte-for-byte from Apex_Tick. Their hashes and source revision are part of the contract. Generated C++ and generated RTL share the typed guard lowering, so their mutual agreement alone is insufficient; the independent oracle remains the comparison authority. The RTL template has shared ancestry with the original RTL, which makes the independently expressed dictionary model especially important.

Each qualification compares complete observations across five executions: generated C++ baseline, generated RTL baseline, generated C++ narrow counters, generated RTL narrow counters, and original Tick RTL. It checks public outputs and normalized internal state, including prices, counters, configuration and the live ledger. This is stricter than matching order outputs alone.

## Corpus and mutations

Fifteen named scenarios cover strategy/field rejection, stalls, unsent terminals, same-cycle handoff/retirement, duplicate terminals, corruption priority, sequence gaps, epoch faults, idle rollover, u32-wide quantities, ledger exhaustion/reuse, sequence exhaustion, reset with an unknown external obligation, conflicting controls and exposure caps. Seeded randomized valid-domain events supplement these cases.

Seven negative controls are executed on both generated backends: wrapping exposure to u32, retiring an unsent identity, advancing time only on accepted events, ignoring epoch, changing stalled payload, reversing recovery/terminal priority and ignoring the exposure cap. Every control must diverge. Its replay is the prefix ending at the first observed mismatch in that fixed corpus, not a globally minimal counterexample. V0 does not claim detection of all conceivable faults or the proposed twenty-mutation roadmap target.

## Local SMT scope

Four Z3 queries cover initial counter state, an inductive counter transition, rate value preservation at seven bits and window value preservation at six bits. SMT queries, solver version, timeout, assumptions and outcomes are retained. An unknown or timeout blocks the narrowing operation. No full stateful RTL equivalence or liveness claim follows from these local obligations.

## Evidence consistency

`validate-evidence` checks all artifact hashes and paths, regenerates the supported sources, replays retained oracle and five backend traces, checks cycle accounting and checks negative-control replay bindings. It executes no artifact-supplied native program. The check establishes local consistency; metadata and hashes do not authenticate physical execution, identity or independent custody.

Atlas export is count-only simulation evidence. The traffic population is replay cycles, including idle and reset, not network messages. An artificial testbench clock is not a physical timing result. No physical latency, power, LUT reduction or measured Pareto improvement is emitted.

## Future assurance gates

Full stateful refinement needs an explicit state relation, assumptions about environment and reset, and correctly scoped proof results. Retiming additionally requires temporal refinement of acceptance, terminal events, configuration and time. Liveness requires fairness or bounded-ready assumptions.

Physical qualification requires exact shell/IP versions, constraints, clock/reset domain checks, implementation reports and calibrated external replay. Official STAC comparisons require the relevant authorized specifications and harnesses.

Primary tool references: [Z3 bit-vectors](https://microsoft.github.io/z3guide/docs/theories/Bitvectors/), [XLS tools](https://google.github.io/xls/tools/), [CIRCT scheduling](https://circt.llvm.org/docs/Scheduling/), [SymbiYosys](https://symbiyosys.readthedocs.io/en/latest/), [Verilator](https://verilator.org/guide/latest/overview.html). XLS/CIRCT/SymbiYosys/Verilator adapters are not implemented in v0; Icarus and Z3 are the actual qualification tools.
