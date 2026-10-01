# Executable scope and release gates

| Gate | V0 status | Required next evidence |
|---|---|---|
| R0 frozen semantics and oracle | Implemented | New profiles require independent specifications and oracles |
| R1 C++ and RTL generation | Implemented for one profile | Broader typed language and backend qualification |
| Counter narrowing | Local obligations and functional runner implemented | No full RTL-equivalence claim |
| Negative controls | Seven transformations × two backends | Extend to the proposed twenty-mutation corpus |
| Retained functional evidence | See retained run and CI | Exact run populations are recorded, not inferred from targets |
| R2 measured optimization | Not measured | Reproducible Pareto improvement against a qualified baseline |
| R3 commercial FPGA | Not implemented | Shell, constraints, timing closure, decoder/serializer, calibrated replay |
| R4 private workload | Proposed | Authorized workload, frozen baseline and acceptance criteria |
| R5 second platform | Proposed | Independent replication and maintenance evidence |
| General search / XLS / CIRCT | Proposed | Semantic lowering, legal transformations and measured search loop |
| Exegy integration | Proposed | Authorized sandbox access, adapter and qualification |
| eFPGA / hybrid / ASIC | Proposed | Qualified IP/PDK, physical flow, test/package and sourced economics |

The architecture directory describes the broader proposal. It is not a diagrammatic claim that every component is running. The README's v0 execution diagram identifies the implemented path.

Research objectives include twenty known mutation controls, additional contract profiles, and a reproducible performance/area tradeoff. An exploratory 20% application-area or 10% CPU-tail improvement is a target, not an estimate or current result. The 51-bit source declaration change alone does not satisfy the measured-optimization gate.
