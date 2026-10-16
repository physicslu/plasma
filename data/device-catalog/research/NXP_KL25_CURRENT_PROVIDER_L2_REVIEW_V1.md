# NXP MKL25Z128VLK4 — Current OpenOCD Provider Qualification Review v1

**ADR-0002 Gate 1; source-only. Status: `CANDIDATE`, not `SUPPORTED`.**
Repository base `2a4c8e4605257b885ad6f4e2383ac0359033df8b`.
One and only one commercial Exact ICPN is reviewed in this increment: **`MKL25Z128VLK4`**.
Other 11 KL25 exact orderable parts retain their existing L1 status.
No new IC identity or Production source is added.

## Authoritative separation

- Current PLASMA provider: OpenOCD **v0.12.0**, source `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`, target `tcl/target/kl25.cfg`, `kinetis` flash driver.
- Historical exact-ICPN Software Executor evidence: OpenOCD `56b8d93fbe61a78dc903d770820d6d896b6d8134`, different `klx.cfg` and `kinetis.c` blobs. **Not transferable.**
- Previous KL25 Gate 5.8 verdict: **`REJECTED_REVIEW`**, even for the one prototype. This is **not** an approved current Provider Programming Profile.
- Source evidence is locked to the existing Git blob SHA-1 of each retained artifact, and manufacturer exact identity remains the Production Catalog authority. The new adapter is **not** an alternate Canonical Catalog engine.
- The vendor-neutral `ProgrammingQualificationRegistry` derives exclusive L0/L1/L2 maturity, and the `CatalogPromotionFramework` only reports existing states and blockers.

## Missing gates before SUPPORTED

| Evidence gate | Existing retained evidence | Current approved provider verdict |
|---|---|---|
| SWD/transport and Tcl dependency | `kl25.cfg` retained; `klx.cfg` changed and transport selection now uses `swj-dp.tcl` | **Not independently requalified** |
| Silicon identity, revision, Flash geometry | Exact NXP material and 128-KiB profile/prototype research exist | **Current probe/SDID and variant applicability not demonstrated** |
| FCF security / sector writes | `kinetis_write` may synthesize/rewrite Flash Configuration Field on a write touching the entire containing sector | **[0x400,0x800) whole-sector exclusion required; current operation qualification absent** |
| Read/Verify/Program/Erase | Legacy prototype admitted operation names and constraints retained | **No present-version operation-level SUPPORTED evidence** |
| Runtime / HIL | No versioned, exact-device HIL/configuration proof | **Not executed or attested** |

The retained FCF protection is a *software planning safeguard*, not a proof of actual erase/program behavior. Existing `test_kl25_openocd_plan.py` tests reject PROGRAM overlap at `0x400`, `0x410`, `0x7FC`, and an ERASE of the `0x400` sector, but these synthetic tests cannot qualify silicon ID, driver IAP semantics, security-state behavior, or readback.

Do not use legacy `REJECTED_REVIEW` or a source CFG match to bypass any gate. Real Flash erase, mass erase, security unprotect, hidden FCF rewrite, and destructive recovery are not authorized.

## Resulting Provider contract

`plasma_web.nxp_kl25_qualification.NxpKl25QualificationProvider` is a bounded, read-only adapter over the frozen negative and partial evidence. It publishes:

- exact `NXP/MKL25Z128VLK4`, `software_state=CANDIDATE`, `reviewed=true`;
- pinned Provider `openocd-upstream` and exact source/target/driver fields;
- `READ / VERIFY / PROGRAM / ERASE` all `UNKNOWN` (none qualified);
- no executable Programming Profile, no runtime attestation or hardware qualification;
- explicit `qualification_gaps`, immutable external evidence custody checks.

The resulting *common* Catalog maturity remains **NXP L0=212 / L1=29 / L2=0 / L3=0**. Only one Level-1 blocker changes category, from `MAPPED_ROUTE_NOT_PROVIDER_QUALIFIED` to `PROVIDER_QUALIFICATION_INCOMPLETE`. NXP Job Picker still has zero selectable ICPNs, and `execution_authorized=false`. Existing ST L2=65 must remain unchanged.

## Boundary of this PR

Full-source installations with required NXP review evidence expose this reviewed candidate. Slim installations without the complete optional review-only evidence do not invent that reviewed record; the underlying source-backed Catalog route still projects L1. Explicit full roots and partially present evidence fail closed by the runtime evidence-root contract.

Offline tests inspect the canonical projection, one exact ICPN (not 12), source Git blob tampering, prior Gate verdict, current-provider delta and FCF guard assumptions. No deployment, Z2, PL, Socket, adapter or DUT operation. Any future `SUPPORTED` qualification needs a separate explicit source-lock, operation-level proof and owner-approved Gate 1 scope; this negative-control adapter cannot auto-promote based on fixture changes.
