# Hardware, economic and commercial gates

V0 executes normalized-event functional replay on a host and in Icarus. It does not operate a physical SmartNIC, FPGA board, exchange adapter or custom chip. Host execution time is not exported as trading latency.

| Candidate | Qualification obligations |
|---|---|
| Linux CPU and NIC | Exact inventory, topology/affinity, power policy, driver/backend, compatible boundaries |
| AMD Alveo U200/U250 | Board part, shell reservations, licensed tools/IP, SLR placement, clock/reset domains, timing closure |
| Cisco Nexus K3P-S | FDK access, exact firmware, resources, timestamp resolution and independent measurement |
| AMD Alveo UL3524 A-UL3524-P16G-PQ-G | Qualified shell and full path; transceiver figures cannot stand in for application latency |
| Corundum shell | Selected application interface, MAC/core clock crossings, ingress capacity and frame validation |
| Exegy nxFramework | Authorized RTL/HLS sandbox adapter and exact platform qualification |
| DPU/SoC SmartNIC | Host, firmware, DMA and interconnect crossings included in the boundary |
| eFPGA | Licensed target macro, tool flow, timing envelope, isolation and reconfiguration policy |
| Hybrid or custom ASIC | IP/PDK rights, cell/macro libraries, physical design, test, packaging, yield and sourced volume scenarios |

Initial board selection should depend on confirmed access to the tools, shell and external measurement equipment. No SKU is purchased by this project and availability/prices are not assumed.

Primary references: [AMD U200/U250](https://docs.amd.com/r/en-US/ds962-u200-u250/FPGA-Resource-Information), [Cisco K3P-S](https://www.cisco.com/c/en/us/products/collateral/interfaces-modules/nexus-smartnic/datasheet-c78-743827.html), [AMD UL3524](https://www.amd.com/en/products/accelerators/alveo/ul3524/a-ul3524-p16g-pq-g.html), [Corundum application interfaces](https://docs.corundum.io/en/latest/modules/mqnic_app_block.html), [Exegy nxFramework](https://www.exegy.com/products/nxframework/), [Achronix Speedcore](https://www.achronix.com/product/speedcore).

## Measurements

Preserve frame-integrity policy and define timing boundaries before comparing systems. A strict integrity gate can require a full frame before irreversible action. Component p99 values cannot be added to obtain end-to-end p99. Report offered, accepted, rejected, emitted, dropped, duplicate and unresolved counts with contract-specific conservation rules. Batch averages do not establish per-operation tails.

[STAC's network-I/O working group](https://docs.stacresearch.com/nio) distinguishes software-harness N1 from hardware-replay/timestamp T0. This repository does not contain or execute an official STAC harness. Other families require their own workloads and qualification boundaries.

## Economics

Economic evaluation remains in [Apex_PerfAtlas](https://github.com/AAH20/Apex_PerfAtlas), rather than a duplicated unqualified model. For hardware h, use fixed engineering/IP/tool/qualification costs F, delivered unit cost U, deployed quantity N and explicit lifecycle operating, colocation and support costs:

`TCO_h = F_h + N * U_h + sum_t(operating_h,t + colocation_h,t + support_h,t)`.

The simplified ASIC break-even quantity is `ceil((F_ASIC - F_FPGA)/(U_FPGA - U_ASIC))` only for a positive denominator and equal or incorporated other costs. Real decisions require sourced yield, packaging/test, respin, volume, refresh, support and uncertainty scenarios. Quote entries need currency, date, validity, volume, inclusions/exclusions and source. No project-specific unit price or NRE is fabricated here.

DUV/EUV describes manufacturing layer technology, not an independent application-latency predictor. [ASML](https://www.asml.com/en/products/euv-lithography-systems) describes EUV and DUV use across chip layers. Colocation can shorten physical paths and simplify connectivity; feeds, ports and permissions remain separate requirements. See [Nasdaq colocation](https://www.nasdaqtrader.com/Trader.aspx?id=colo) and [Equinix financial infrastructure](https://www.equinix.com/industries/financial-services). Avoid double-counting bundled power or inferring trading profit directly from nanoseconds.

## Reviewable private engagement

A first engagement should freeze a named workload, counterpart-approved tools/data access, baseline, oracle, exact platform, measurement boundary and acceptance criteria. Deliver candidate implementations, qualification results, unresolved limits and a reproducible report. Subsequent work can cover a board adapter, regression maintenance or a licensed platform. Private inputs remain local unless disclosure is explicitly authorized. OSS evidence cannot guarantee contract size, hardware access, a partnership or a benchmark win.
