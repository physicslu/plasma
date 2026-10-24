# IC Selector Evidence Consistency — Gate A (read-only)

## Scope and non-authority

This change corrects the presentation of upstream OpenOCD evidence versus the PLASMA Production CFG binding. It is a read-only API/UI projection. No Catalog identity, ADR-0002 L0/L1/L2/L3, Programming Qualification, Runtime, Job, Batch, hardware eligibility or Production backend record may be modified or inferred from upstream evidence.

The original selector's third tag still has exactly three states, but is **explicitly named PLASMA CFG**: `mapped` (Production binding), `candidate` (independent Research candidate, not executable) and `no_mapping` (not bound). It is **not an upstream source-file existence indicator**. Missing independently attested upstream information is displayed as **not attested**, never **does not exist**.

## Separate source layers

| Dimension | Authoritative input | Meaning |
|---|---|---|
| Manufacturer identity | Immutable Production Catalog | The official exact commercial ICPN exists |
| Upstream OpenOCD CFG | `upstream_openocd_evidence.target_cfg` | File exists in pinned upstream source; not an installed runtime |
| Upstream Flash Driver | `upstream_openocd_evidence.flash_driver` | Source file exists and applies to the sourced Base Device |
| Upstream DEVID | `upstream_openocd_evidence.device_id` | Device ID from pinned driver table, **not** read from silicon |
| Production CFG binding | `backend.mapping_status`, `backend.target_config` | Executable routing association in PLASMA (separate permission gate) |
| Programming Qualification | `programming_qualification` | Level and exact-ICPN provider review, not inferred from upstream files |
| PPU/Socket/HIL | Independent physical evidence | Never inferred from L1, upstream source, or CFG mapping |

The Microchip source projection is limited to 1,015 admitted Product ICPNs. PIC32MX (893 commercial codes / 85 Base Devices) is pinned to upstream OpenOCD 0.12.0 `tcl/target/pic32mx.cfg`, `src/flash/nor/pic32mx.c` and the exact driver DEVID for the official MCP Base Device. SAM L10/L11 (122 exact codes) is pinned to `tcl/target/atsaml1x.cfg` but has **no proven upstream Flash Driver or DEVID**. The Microchip datasheet `DS60001513G` is applicable to SAM L10/L11, **not** to PIC32MX.

If a release lacks `upstream_openocd_evidence`, the UI reports lack of an independent upstream attestation instead of claiming a missing file. For ST and NXP, this Gate A does not synthesize any upstream data from a mapped Production CFG; existing binding state is still displayed separately.

## Required fail-closed tests

- All 1,015 exact Microchip codes have the expected immutable file/version pins; the 893 PIC32MX codes map through the fixed 85-entry DEVID table.
- SAML1X has no fabricated Flash Driver or DEVID.
- Microchip canonical qualification stays L1 `CANDIDATE`, `no_mapping`, Job/Execution denied.
- Distorted device IDs, source commits or mapping status fail closed.
- PIC32MX IC Information must not reference the SAML1X datasheet, and UI labels use current Level/Qualification instead of hardcoded L0/UNKNOWN.
- ST/NXP current Product/Job behavior is not modified.
- PR remains Draft. Gate B, deployment, actual hardware and merge are not authorized.

Neither GitHub-hosted CI nor source-pinned evidence constitutes a real-device programming qualification.
