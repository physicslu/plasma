# PLASMA Catalog L3 — independent PPU Ready / Socket Ready (Gate 1)

**Date:** 2026-11-09
**Owner decision:** L3 requires one approved physical HIL configuration on *either*
`PPU_SITE` or `SOCKET_ADAPTER`. Both routes are L3; there is no `Both Ready` tier.
**Scope:** ADR-0002, canonical qualification, read-only Manager-owned Selector,
independent versioned physical evidence, UI badges, Host-only regressions.
**Excluded:** DUT/PPU operation, SWPC deployment, firmware/RTL modifications,
Socket fabrication, electrical-certification claims, PR merge.

## Source of truth and current result

The canonical `ProgrammingQualificationRegistry` alone derives the Catalog
Level. A source-backed L2 `SUPPORTED` ICPN may enter L3 only if its reviewed
physical-compatibility manifest contains one or more configurations validated
as real HIL `PASSED`. `CatalogPromotionFramework` remains a read-only observer.

The two independent qualification flags are `ppu_ready` and `socket_ready`;
`verified_configurations[]` preserves individual identities and limitations.
The L3 count is unique Exact ICPN, not two per part if both routes pass.
Neither flag overrides `execution_authorized=false`, live Site admission, or
`hardware_runtime_ready`.

**First qualification** — `STMicroelectronics / STM32F103C8T6`:

- L2 `SUPPORTED` OpenOCD software qualification is unchanged.
- L3 configuration ID:
  `st-stm32f103c8t6-z2-site2-direct-swd-20261109-v1`.
- Type: `PPU_SITE`, `connection_mode=DIRECT_WIRE`, `socket=null`.
- PYNQ-Z2 prototype, `z2-hil`, device
  `ppu-device-7ed4b30913a9bf6101da5a7a`, **Site 2 only**.
- Package LQFP/48, target `STM32F103C8T6`, SWD,
  `z2-abi5-swd-openocd5088`, `plasma_swd:5`.
- Installed Runtime source: `a1b1c6f3b1424ce38d1de7e597ef22d0ef4460f2`;
  FPGA Image identity from separately archived post-S5 audit:
  `z2-independent-swd-v5-d0add58c`.
- Two archived physical Jobs: `job-20261109-042428-113dd980` and
  `job-20261109-044035-b8cbd4da`; each did one full Flash cycle,
  verified 18,768/18,768 bytes with exactly matching firmware and Readback
  SHA256, `attempts=1`, `safe_off=true`, Manager outcome `PASS`.
- Physical receipts are replay-checked by the read-only evidence loader:
  raw SHA256, Job/Site/ICPN/ABI/Engine/Target, full Readback, one attempt,
  SAFE_OFF, paired Manager journal and Bootstrap Runtime/Device ID.
- The canonical record is in
  `release/physical-compatibility/l3-configurations-v1.json`. Underlying
  evidence is fixed in
  `docs/evidence/console-bundle-programming-hil-2026-11-09/`.

## L3 scope, optional observations, and execution safety

The PPU Ready badge means **this particular archived PPU/Site direct-SWD
configuration** successfully performed the scoped HIL operations. It does
**not** mean every PPU, Site, current boot, FPGA load, wiring harness or
voltage is qualified. Specifically:

- No Socket exists or was tested: `Socket Ready = false / NOT_TESTED`.
- Independent analog target voltage/current measurement is **not required**
  for L3; this run truthfully retains `electrical_measurement=NOT_TESTED`.
- Physical wiring-harness Revision is **not required** for L3; this run
  truthfully retains `physical_wiring_revision=NOT_RECORDED`. The PPU hardware
  revision is also unrecorded, so this HIL claim is bound to the observed
  physical instance and historical Job runs.
- The Bootstrap state after these runs reports `pl_qualification=not_qualified`;
  this L3 operation result must not be recast as FPGA Image release qualification.
- These runs did not independently observe post-Flash USB CDC behavior,
  complete an eight-Site test or exercise physical fault injection.
- Any new Job still must pass current route, FPGA identity, supply/safety,
  Site Lease, SAFE_OFF and UNKNOWN recovery checks.

## Socket track (independent; NOT_TESTED today)

The `SOCKET_ADAPTER` track shall require a real fixture model and revision
plus corresponding physical Job receipts attesting the Socket identity.
Reusing the direct-wire PPU receipt and inventing a fixture model is rejected.
No Socket qualification record is included in this change. If a future
configuration passes both tracks, display both badges without a third label
and count the exact ICPN once.

## Acceptance and next gate

1. Blue Pill appears with Catalog Level 3, `PPU Ready=true`,
   `Socket Ready=false`, `execution_authorized=false`.
2. The public IC Selector supports `levels=3` and the same canonical
   server-side pagination/count rule; L2+L3 total remains unchanged.
3. Negative tests reject unknown/unsupported ICPNs, unversioned Socket
   evidence, mismatched receipt SHA, false SAFE_OFF, mismatched identity.
4. Source/provider qualification and other vendor counts do not regress.
5. Build/CI tests are distinct from the existing historical DUT receipts;
   no new hardware operation is implied.

**Gate 2** is required to merge the independent Draft PR. Deployment and
new physical HIL are not in this Gate 1 scope.
