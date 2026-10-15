# NXP ADR-0002 Phase 2 — KL25 12 ICPNs and OpenOCD Provider Revision Audit (v1)

**Decision:** retain all **12** verified exact KL25 ICPNs as Phase 2 `CANDIDATE`. **Promote none to `SUPPORTED`**. This audit establishes why the existing one-device software prototype cannot be reused against the currently approved OpenOCD provider. It does **not** modify Production, IC Selector, runtime hardware admission, Job/Batch, PL/PPU or Phase 3 HIL.

## Decision-grade source comparison

| Artifact | Existing KL25 Software Executor prototype | Approved PLASMA OpenOCD |
| --- | --- | --- |
| Source commit | `56b8d93fbe61a78dc903d770820d6d896b6d8134` | `9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c` |
| `tcl/target/kl25.cfg` Git blob | `916edf6853c3f26a004d2ca5a2f0e08f43a24093` | Same; **byte-identical** |
| `tcl/target/klx.cfg` Git blob | `b4014ba5b6de75e236e0a6b8780cf6448c991c2` | `cd236b3395e42310f1475f3b64580758a7f3b9ea` — **changed** |
| `src/flash/nor/kinetis.c` Git blob | `266b447c04376b529c44ac11cd9fd6acc31e0e8c` | `7137b4aa078719af31122f8276494f006589e8ab` — **changed** |
| Transport definition in `klx.cfg` | Explicit `transport select swd` and `swd newdap` | `source [find target/swj-dp.tcl]` and `swj_newdap` |
| Additional approved-provider include | No equivalent direct `swj-dp.tcl` source at this location | `tcl/target/swj-dp.tcl`, Git blob `f2b233fb78133fd5e45395fd307674c16a65ed70` |
| Runtime/matching provider attestation | Historical Software Executor with fake-process tests | Release manifest: OpenOCD 0.12.0, `hardware_runtime_ready=false` |

The unchanged `kl25.cfg` **does not establish source or programming equivalence**. The changed Tcl dependency affects **how the SWD/JTAG transport is selected**, and the Flash driver differs by source blob. A concrete follow-up must review both implementations' chip-ID/FTFA/FCF/erase/write/security behavior before authorizing a new version-bound Programming Profile. `nxp-kl25-openocd-provider-delta-v1.json` freezes the observed upstream blobs and explicitly marks semantic equivalence *unverified*. The native upstream files were inspected at the above immutable commits; this report preserves their Git object references, not an installed binary attestation.

## Exact KL25 ICPNs

The source-locked NXP KL25 commercial table contains 12 validated complete order codes, each in Phase 1 `IDENTIFIED` and **Phase 2 `CANDIDATE`**:

| NXP exact commercial series | 32-pin HVQFN | 48-pin HVQFN | 64-pin LQFP | 80-pin LQFP | Flash |
| --- | --- | --- | --- | --- | --- |
| MKL25Z32 | `MKL25Z32VFM4` | `MKL25Z32VFT4` | `MKL25Z32VLH4` | `MKL25Z32VLK4` | 32 KiB |
| MKL25Z64 | `MKL25Z64VFM4` | `MKL25Z64VFT4` | `MKL25Z64VLH4` | `MKL25Z64VLK4` | 64 KiB |
| MKL25Z128 | `MKL25Z128VFM4` | `MKL25Z128VFT4` | `MKL25Z128VLH4` | **`MKL25Z128VLK4`** | 128 KiB |

Each individual ICPN's manufacturer identity, family, flash size and package are derived from the separately pinned `nxp-kl25-commercial-icpn.csv` dataset and checked against the **297-item Phase 1** and **28-item Phase 2 candidate** ADR-0002 canonical snapshot. The other **16 K32L2 candidates** are untouched.

## Reusing the previous KL25 work — strict scope

The existing KL25 Evidence/Admission foundation is **for exactly `MKL25Z128VLK4`**, not for all twelve variants.

- Original Gate 5.8 manufacturer review result was `REJECTED_REVIEW`; the subsequent post-review candidate process separately retained corrected evidence. Historical rejection must not be overwritten by the later candidate release.
- The old candidate Software Executor has **READ, VERIFY, PROGRAM and one explicitly bounded ERASE_SECTOR** operation; those are **software-only** operation-admission artifacts, not current-provider Phase 2 `SUPPORTED`.
- Existing old-backend constraints: **4-byte program starting alignment**, no implicit erase, Flash Configuration Field `0x400–0x40F` never programmed, and its **entire 1 KiB sector** not erased. Mass erase, MDM-AP erases, backdoor key, unprotect and security transitions remain blocked.
- The other 11 ICPNs cannot inherit that exact-device Programming Profile just because `kl25.cfg` is shared. Their silicon revision, flash geometry and security applicability remain independently required.
- The old prototype commit and currently approved provider **differ**, so even the single candidate requires a fresh reviewed backend lock and operation-scope applicability for the approved provider. **An exact commit string match by itself would also be insufficient** without the source semantic review.

## Phase 2 acceptance blockers and next engineering steps

1. Compare `kinetis.c` at **both source commits** for KL25 FTFA commands, FCF synthesis/rewrite behavior, SDID/FCFG1/FCFG2-derived geometry, erase/write/verify errors and security handling. Pin the reviewed differences in a new current-provider Backend Lock rather than silently mutating the old lock.
2. Review the change from explicit **SWD-only** transport to **SWJ transport based on the session**. Explicitly bind selected transport and actual interface/adapter selection to the PLASMA Job contract; do not assume SWD merely because a KL25 Target CFG was loaded.
3. For `MKL25Z128VLK4`, bind exact device silicon/revision, current-provider Flash map/security/FTFA command behavior, appropriately scoped manufacturer references, requested four operations, Programming Profile + Geometry Profile, and a separately reviewed source equivalence/migration decision. Rerun deterministic software tests on the approved provider version.
4. For the other eleven exact ICPNs, review per-variant applicability, geometry and security; **do not** promote them by inheritance.
5. Phase 3 hardware/Site/Socket/HIL is independent; keep `NOT_AUDITED`. Physical target validation is not fabricated from fake OpenOCD tests.

## Reproducible offline checks

```bash
python data/device-catalog/research/nxp_phase2_kl25_provider_lock_v1.py
python -m unittest discover -s data/device-catalog/research -p 'test_nxp_phase2_kl25_provider_lock_v1.py' -v
```

Tests reject source Git-blob mutation, fabricated vendor order codes, false Gate 5.8 review status, false revised backend lock, unsafe FCF operations, unreviewed SWD/SWJ transition, copied 128 KiB prototype operations to other exact devices, artificial `SUPPORTED` and HIL `PASSED`. The ADR-0002 `CANDIDATE=28`, `UNKNOWN=269` counts stay unchanged.

**This is a blocker-resolution and source-equivalence scoping PR, not a new authorization to flash an NXP device.**
