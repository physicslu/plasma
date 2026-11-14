# ADR-0009 — PLASMA Open Programming Platform (OPP)

- Status: Accepted policy (owner decision 2026-11-14); implementation pending; repository adoption subject to Gate 2.
- Scope: product positioning, modular hardware and platform boundaries. No execution contract change.

## Context

PLASMA currently uses PYNQ-Z2 as its reference PPU. Building a proprietary Linux motherboard adds DDR, BGA, supply-chain and inventory costs without directly improving IC programming. The owner chooses an open platform model with user-supplied host boards and optional validated programming hardware.

## Decision

PLASMA is the Open Programming Platform (OPP), an open universal IC programming platform based on open software, programmable hardware and standardized interfaces. Open4th Lab remains the brand. Open Programming Framework (OPF) remains the software framework within OPP; existing package names, APIs, Bundle v3 and identifiers are not renamed.

OPP comprises OPF (including provider/profile contracts), Control Station, PPU Runtime, programming engines, hardware interface specifications, DIB and adapters, and qualification evidence. Catalog admission and physical qualification remain separate.

### Modular hardware

- Open Host: users may purchase supported Zynq or Raspberry Pi boards independently. Other Linux hosts are future candidates.
- Open Engine: Zynq uses integrated PL; Raspberry Pi may use an external FPGA engine. Third-party implementations are permitted subject to compatibility qualification.
- Open Interface: standardize Host-to-Engine logical ABI and Engine-to-DIB electrical interface independently.
- Open Provider: retain extensible programming providers and evidence-based admission.
- Open Hardware: publish interface specifications and pursue open hardware designs; exact licenses and publication scope require separate decisions.

Open4th Lab may sell validated FPGA engine boards, power/interface boards and socket adapters independently or as kits. Users need not purchase a proprietary Linux motherboard. Commercial hardware purchase must not become an authorization requirement; ADR-0008 Local Owner Mode remains applicable.

### Interface boundaries

Host-to-Engine: reuse FPGAInterface/WordPort concepts, versioned ABI, identity and capability discovery; AXI/MMIO is the current reference, SPI and USB are candidates. No claim of transport interchangeability without validation.

Engine-to-DIB: define connector, pinout, electrical levels, timing, power, fault, interlock, reset and safe-state requirements. Board-specific adapters may be necessary. Power Control IP is independent of communication IP; site coordination enforces power readiness and fault handling. DIB owns analog regulation, level shifting, discharge and independent hardware protection. Host loss and FPGA reset/configuration must be addressed by explicit fail-safe mechanisms. At least 12 V VPP is a design target, not a qualified capability; device-specific limits apply.

## Current execution boundary

This ADR does not move live OpenOCD to SWPC or Manager. Existing AGENTS.md, PS-local WordPort, Z2 PL, PPU ownership, Site locks, Bundle v3 and safety contracts remain normative. A future non-Zynq PPU must preserve autonomous local execution and receive separately approved architecture, implementation and CI changes before becoming supported. No change to current wire protocols or deployment authorization.

## Migration and consequences

1. Define Engine-to-DIB requirements and compatibility model.
2. Develop independent Power IP on the existing Zynq reference platform.
3. Prototype and electrically qualify a DIB, initially one Site then two.
4. Validate real programming and fault behavior on Zynq.
5. Evaluate external FPGA and SPI transport using Raspberry Pi; synthesize, measure throughput and qualify the complete configuration.
6. Publish versioned interfaces, compatibility evidence and hardware designs under separately selected licenses.

Each implementation phase requires its own bounded Gate 1 and Gate 2. FPGA vendor, exact board, connector, voltage/current ranges, cost, licenses and SKU names remain undecided. Raspberry Pi, external FPGA, 12 V VPP and multi-Site concurrent operation are NOT_VERIFIED by this decision. Existing single-Site evidence is not generalized. No RTL, code, deployment or hardware operation is authorized by this documentation change.

## References

- [OPF architecture](../architecture/opf-architecture.md)
- [Local Owner Mode](0008-local-owner-mode.md)
- [Independent SWD engine](0006-independent-swd-engine-and-future-gpio-bus.md)
- [Operating contract](../../AGENTS.md)
