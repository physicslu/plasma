# PLASMA Fixed Image Driver Architecture — M1 Gate 1 Review / Acceptance Plan

**Status:** Gate 1 architecture/test deliverables only; M1 Architecture Freeze **NO-GO until explicit architectural review**. No real MMIO, FPGA Manager writes/reloads, deployment, hardware execution or PR merge in this scope.

## Architecture decision / explicit boundary

Product: first generation on PYNQ-Z2 **Zynq-7020** (XC7Z020), **one Universal Fixed FPGA Image** during Linux runtime, no normal A/B switching. A target IC/algorithm switch uses semantic Profile/Protocol selection without Linux or network restart. An observed fail to fit timing/LUT/BRAM at 2 then 8 actual Sites is a trigger to reopen an architecture decision; selecting the future 7010 SKU now is premature.

**First v1 minimum physical protocols**: SWD and SPI as eligible future RTL implementations. JTAG/I2C/ICSP are **reserved** but explicitly not represented as already working. The proposed ABI is "complete" only for the defined minimum PIO command set and resource conventions; no claims of arbitrary IC programming, DMA, IRQ or live code.

## M1 deliverable ledger

| Review ID | Evidence and acceptance | Gate 1 code state | M1 disposition |
| --- | --- | --- | --- |
| A1 | ADR-0003 states fixed-image choice, no normal reload, measurable fallback criteria | Proposed amendment | PENDING owner/RTL review |
| A2 | Machine-checkable 64-KiB ABI with 8 Site slots; exact RO/WO/Sequence/FIFO/Error/Command maps | Gate 1 JSON + offline checker | REVIEW CANDIDATE; RTL absent |
| A3 | Board Descriptor→UIO unique binding and resource translation, rollback of ambiguous discovery, no `uioN` hardcode | Host-only `select_uio_resource` + driver design | Real UIO adapter NOT RUN |
| A4 | One PPU Hardware Broker distinct from logical Execution Owner; 1..8 Site leases, same exact IC, per-site payload and fault isolation | Host-only `admit_host_transaction` + ownership design | Deployment/IPC integration NOT RUN |
| A5 | Dedicated Host-only fault/negative regression; no real-char-device access in workflow | New CI workflow on GitHub-hosted runner | PENDING CI |
| A6 | Board safety / Power-OE-NRST independent contract and recovery / ownership test design | Documentation only | Electrical HIL NOT RUN |
| A7 | RTL/PS feasibility: two true SWD/SPI physical Site engines + 8-Site resource estimate, timing/BRAM/FIFO and bus ordering | Not authorized in Gate 1 | Required before M1 final acceptance |
| A8 | Close/replace stale single-site `FPGAInterface` placeholder only after ABI and actual backend qualification | Explicitly deferred | NOT IMPLEMENTED |

**M1 architectural decision should NOT require dynamic FPGA reconfiguration physical proof** if that functionality is intentionally excluded from v1; the original K0/K2 isolation hazards remain live for firmware updates/recovery and a possible later A/B switching ADR. Do not pretend they are fully solved. Real UIO live read/write and external DUT programming are subsequent independent HIL admissions, not mandatory proof for a document-only Gate 1.

## Critical design questions and falsifiable alternatives

1. **Protocol engine count**: eight independent site ingress ports with shared hardware engines vs eight physical engines. Prove with RTL diagrams and measured arbitration budget; never assume parallel Job acceptance implies eight simultaneous pin clocks.
2. **Host data movement**: PIO-only v1 with bounded Site FIFO (1..256 words, max 8192 bits) versus future DMA. For two and eight physical Sites, measure CPU%, throughput, P50/P95/P99 and cross-Site latency. If PIO fails throughput, produce a DMA ABI v2 design rather than silently add DMA registers.
3. **UIO versus custom driver**: a broker plus device permissions coordinates cooperative processes but does not enforce exclusivity over other privileged processes, Kernel clients or DMA. Escalate to a Kernel driver on concrete evidence that non-cooperating or privileged concurrent owners cannot be eliminated by service isolation.
4. **Power/Reset**: physical safe electrical output independent of PL is required. Site safety software sequencing alone cannot prove reliable voltage, power-good or NRST behavior.
5. **Kernel source**: Issue #1004 provides boot-bound readonly snapshot only; exact matching Kernel binary/source/patchset unknown. This does not block drafting an offline fixed ABI, but blocks any claim that a live Kernel resource transition was qualified.

## Stage-gated follow-through (each substantive implementation requires scoped Gate 1)

**Stage F1 — Owner architecture review / M1 Freeze candidate:** approve or revise the ABI registers and commands; RTL feasibility/resource bound; access policy and safety split; settle SPI/SWD first-slice scope and board descriptor/clock timing. Move `Proposed` to `Accepted` only on full technical justification.

**Stage F2 — Host Driver to RTL vertical slice:** implement only reviewed fixed-image Identity + one SWD Site, error and transaction sequencing in RTL, verifying with Cocotb and the real production SWD driver contract. GPIO safe default independently reviewed. No host test pretends to be HIL.

**Stage F3 — Authorized real Z2 hardware proof:** align approved bitstream SHA/clock/Board Descriptor, conduct controlled two-Site hardware MMIO and UIO admission after safety/recovery is qualified, check real ABI readback/restore and source identity. No unapproved /dev/uio today.

**Stage F4 — Scale:** enable SPI Site functionality, compare shared engine vs dedicated, measure 2→4→8 real capacity, RTL timing and per-Site isolation. Product cost-down 7010 only after measured 7020 utilization and IO/timing bounds.

## Exact Gate 1 acceptance (this PR only)

- Latest-`main` independent Draft PR with ADR-0003 amendment, ABI JSON + explanatory doc, UIO and Broker/8 Site contracts.
- Host-only validator and adversarial tests for structure, reserved addresses, UIO renumber/drift/overlap, exact IC, epoch/generation, stale leases, supported commands, FIFO bounds, non-reload.
- GitHub-hosted CI with **no privileged/self-hosted hardware runner** and no hardware execution.
- All unproven RTL, Kernel, electrical, full 8-Site HIL and M1 acceptance claims explicitly **NO-GO / NOT RUN**.
- Gate 2 merge request is separate; no automatic merge or deployment.
