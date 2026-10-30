# Independent SWD IP Artifact Completion — Gate 1A

2026-10-30. **Host-only artifact format PASS; engineering deployment BLOCKED.** Baseline: `main a22c9cb04a9ea1361a39d2504fc83f510898390e`, Draft #1216 `1ab6c5870ba7ac0fe78e9b8b6597d2ad2f5ab31a`, Draft #1189 `ab79b04efb2c38401103876043e39d4745284163`. No Z2, FPGA or DUT operation occurred.

## Locked input and conversion

Owner-pinned [Vivado Run 40893512347](https://github.com/physicslu/plasma/actions/runs/40893512347), [Artifact 12905788568](https://github.com/physicslu/plasma/actions/runs/40893512347/artifacts/12905788568), ZIP SHA256 `931682a44c83b9f0058ad26c22241830eeb4e8edcde731bce19a5caedd592230`. The Receipt source SHA is exact #1189, Vivado 2026.1 and Board Files SHA `e02d6a3866b5465218f777168cdc51344ac94e07`. Independent hashes matched the Receipt for BIT `ac89d58b41bbfa1eafd4b51a389b7953186fc8e2ed8b1629bfc0a92f51797e88`, HWH `5309c05beb8a17c9b13e8e2ba3d3c23d8264ca4adc38649bab6391e896577eb6` and all seven build reports.

The Host-only conversion used Vivado 2026.1 Bootgen with BIF `all: { system_wrapper.bit }` and command `bootgen -arch zynq -image candidate.bif -process_bitstream bin -w off`. Exit 0 produced a 4,045,568-byte `system_wrapper.bit.bin`, SHA256 `d3b65a818c03ef1f73a3f0026357d6ed6a9fd903f2f041bc09b89d6b6ba3b773`. Independent byte inspection matched the complete 4,045,564-byte BIT payload after 32-bit word byte swapping, followed by the exact NOP word `00000020`. This is a real format conversion. The BIN remains a local Host-only output; it is not a Git release asset or deployed firmware.

The [Root-schema Image Manifest](plasma-image-manifest.host-only.json), SHA256 `b3a3643f46ac6eb861c288ae20dc78abe62852281709f1a5d94705acc1856669`, passes `plasma.fpga.image.v1` parser and negative contract tests. It encodes Site 1 fixed ID `0x00050001` at `0x43C01000`, Site 2 fixed ID `0x00050002` at `0x43C02000`, and reads an 8 KiB aperture from Site 1. Its `abi_version` is the encoded identity word `0x00050001` because this RTL has no separate ABI register. The two HWH Site apertures are each 4 KiB. Actual Z2 UIO mapping, Root source pin, live identities and Golden hash must be checked before use. The Golden SHA in this Host-only manifest is historical candidate data, not current-boot proof. The [candidate evidence manifest](candidate-manifest.json) keeps current Boot, Golden and driver backup fields null.

## Timing and driver findings

The exact-source routed report has setup WNS `+0.345 ns`, hold `+0.028 ns` and DRC pass for constrained paths. `check_timing.rpt` has **2 missing input and 4 missing output delays** (`TIMING-18`); external timing qualification remains false. The XDC binds four PMOD signals to Y18/Y19/W14/Y14 at LVCMOS33 but provides no off-board min/max. [The #1189 project timing audit](https://github.com/physicslu/plasma/blob/ab79b04efb2c38401103876043e39d4745284163/pl/projects/z2-swd-independent/external-timing-audit.md) derives the available FPGA-only margin for the 12.5 MHz N=4 candidate, but target tCO/setup/hold, cable flight, skew and board uncertainty are not established. [AMD TIMING-18 guidance](https://docs.amd.com/r/2021.2-English/ug906-vivado-design-analysis/TIMING-18-Missing-Input-or-Output-Delay) requires board/application I/O delay constraints. No unsupported numbers were inserted in XDC, so no new Vivado implementation run was necessary; the locked run is the current exact-source timing evidence. A source-backed target and cable budget plus new exact-source build are required to close this blocker.

The native C mapping expects a pre-opened `/dev/mem` FD and an injected authorization callback. Host-only tests establish ABI v5 register/address and ARMv7 source/build behavior; injected Root/Boot/Image/voltage facts do not prove live authority. No trusted Z2 device-backed Owner/MMIO provider or PS-local OpenOCD adapter was observed. The protected Root Entry only admits `download|test|restore` plus source SHA. Existing engineering `ppu-deploy` does not admit this IP. None of these boundaries was bypassed.

## Evidence and readiness

| Item | Result | Evidence / condition |
| --- | --- | --- |
| Exact source, BIT/HWH/Board/reports | PASS — Host-only | Run 40893512347 and hashes above |
| BIT → BIN and Root Manifest format | PASS — Host-only | Bootgen exit 0, byte inspection, parser and positive/negative tests |
| ABI v5 source contract | PASS — Host-only | #1189 [source CI Run 40893017601](https://github.com/physicslu/plasma/actions/runs/40893017601); focused local tests |
| External SWD I/O timing | BLOCKED | TIMING-18 ×6; no justified target/cable min/max |
| Z2 Owner, UIO, current Boot and Golden | NOT_VERIFIED | No device access in Gate 1A |
| Deployable PS driver/adapter and safe install | BLOCKED | No trusted live provider or reviewed install transaction |
| FPGA load, DPIDR and recovery | NOT_RUN | Separate physical Gate required |

**READY_FOR_Z2_READONLY_CHECK = YES** only for a separately approved, bounded Gate 1B inventory in the [Runbook](../../deployment/swd-independent-engineering-gate1.md). **READY_FOR_ENGINEERING_DEPLOYMENT = NO.** The inventory must stop on unknown current state, mismatched UIO/Root/Golden or active/conflicting owner. It grants no file staging, MMIO, FPGA load, DUT action or service restart.
