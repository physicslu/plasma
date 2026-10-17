# KL25 Current OpenOCD Source Review v2 — Evidence, Not Software Qualification

**Gate 1 scope:** Source-only inspection for exact NXP `MKL25Z128VLK4`.
**Provider:** OpenOCD 0.12.0, source `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`.
**Outcome:** `CANDIDATE` (Catalog L1). L2 remains 0, no programmable route or hardware execution is admitted.

This review supplements the historical `NXP_KL25_CURRENT_PROVIDER_L2_REVIEW_V1.md` and version-pins source observations in `nxp-kl25-current-source-review-v2.json`. Sources are pinned by upstream Git blob hashes and function/line ranges. A source inspection witness is **not** an installed-binary attestation, an observed silicon revision, or a live Flash test. Git blob identifiers alone cannot prove behavioral equivalence across compiled releases.

## Pinned upstream observations

| Location at pinned commit | Positive evidence | Unproven requirement |
|---|---|---|
| `tcl/target/kl25.cfg` → `klx.cfg` | Script identifies KL family and includes the common target | No actual KL25 probe |
| `klx.cfg`, `swj-dp.tcl` | `swj_newdap` is conditional on selected session SWD/JTAG | SWD session transport, adapter wiring and expected DPIDR are not independently attested |
| `klx.cfg` `reset-init` | Device watchdog can be disabled by event handler | Even READ-oriented OpenOCD startup can change target state; no claim of zero side effects |
| `kinetis.c` `kinetis_probe_chip` | Probes SIM SDID, SIM FCFG1/FCFG2; derives sector/bank information | Exact SDID/revision, FCFG readbacks and dynamic geometry on target are not measured |
| `kinetis.c` `kinetis_fill_fcf` | Builds generated security/protection field and has `assert(bank_iter->prot_blocks)` | No proof the assertion path is impossible for all live bank configurations |
| `kinetis.c` `kinetis_write` | Any write overlapping FCF sector can set `set_fcf` and write generated FCF | Must reject **every** PROGRAM overlap with `[0x400,0x800)` |
| `kinetis.c` `kinetis_erase` | Erase of FCF-containing sector can synthesize and write FCF | Must reject FCF sector ERASE; no mass erase or security-operation qualification |

The FCF physical bytes are `[0x400,0x410)`. That is **not** the complete mutation risk boundary: the flash sector is `[0x400,0x800)` (1 KiB). A `PROGRAM` starting at `0x410` may cause implicit FCF activity even though the 16-byte FCF payload itself is not addressed.

## Offline safety and integration

The review record is immutable evidence: the KL25 Provider adapter checks its own Git blob, upstream blob locks, precise exact-ICPN, current release, historical rejected verdict, FCF geometry, eight source observations and every non-admission flag. Any drift fails closed. The new test probes:
- Mutation of evidence into `SUPPORTED` or into an asserted SWD PASS.
- FCF restriction changes and upstream flash driver blob substitution.
- Payload ranges touching the first, middle, last or both sides of the FCF sector; adjacent disjoint ranges remain syntactically compilable, subject to **other** gates.
- Canonical `job_selectable=false`, `execution_authorized=false`, `installed_runtime_attested=false` and `software_state=CANDIDATE`.

Do **not** conflate successful offline plan compilation with execution authorization. The legacy prototype's `Gate 5.8=REJECTED_REVIEW` is unchanged. The four required operations (`READ`, `VERIFY`, `PROGRAM`, `ERASE_SECTOR`) all remain `NOT_QUALIFIED`.

## Remaining requirements for a separate software L2 admission decision

1. Independently demonstrate that the chosen adapter and OpenOCD session strictly use SWD, compatible debug DP/MDM behavior, and a version-locked Tcl/flash-driver runtime.
2. Obtain exact-chip revision/SDID and FCFG1/FCFG2 trace under safely authorized conditions and reconcile 128-KiB manufacturer geometry and bank/sector details.
3. Prove read, verify, program and required erase behavior on the actual current Provider revision, including hidden auto-erase and FCF/security paths, without unsafe side effects.
4. Review electrical/session/target-reset effects and explicit protection/mass-erase exclusions.
5. Establish an operation-level Software Qualification record with independent reviewer sign-off. Do not automatically promote from this v2 source witness. Any actual HIL is a separate owner-authorized scope; no HIL is authorized here.

## Approval scope and regression

No PL, FPGA, HIL, Socket, Site, DUT, deployment, OpenOCD execution or merge without owner Gate 2. NXP canonical remains L0=212 / L1=29 / L2=0 / L3=0, ST L2=65 and Microchip L1=1015 on the examined baseline. Updating evidence never authorizes Job/Batch or physical operations.
