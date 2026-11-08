# PLASMA OPF S2 safety-control audit and S1-C Site 2 physical Flash acceptance

**Date:** 2026-11-08 (Asia/Taipei)  
**Baseline:** `main@91a4a12c0c89ffbea34152023b9d62948fb98a0f` (merged #1347 S1-C).  
**Scope authorized:** S2 source-level and existing CI evidence audit; **one** physical Site 2 `STM32F103C8T6` Flash/Readback/SAFE_OFF through the *new* S1-C Runtime path, subject to observed safety admission.  
**Execution surface observed:** connected GitHub repository and prior GitHub-hosted CI. The execution environment **does not expose the owner-authorized SWPC/Z2 SSH, lab gateway, or hardware operator channel**. No device inspection, hardware command or deployment occurred as part of this report.

## Outcome separation — do not conflate three kinds of evidence

| Scope | Result | Evidence |
| --- | --- | --- |
| S2 source-level control audit | **SOURCE AUDIT COMPLETE — P0 FAIL-CLOSED GAP IDENTIFIED AND FIX STAGED** | Files and safety controls below; the staged Runtime patch below must pass CI and Gate 2 before real HIL |
| Existing Host-only regression | **PASS ON MERGED S1-C HEAD** | #1347 exact-head GitHub workflows: 9/9 success; Python PS 3,193 passed, 12 skipped, 4,592 subtests passed (run 42447228369) |
| S1-C new-path Site 2 physical Flash | **NOT_RUN — execution-channel blocker** | No authorized live SWPC/Z2 session or physical receipts available in this environment |
| Deployed new Runtime identity | **NOT_VERIFIED** | Git `main` does not establish Z2 installed release Git SHA |
| Real voltage, PL/ABI identity, Root/native admission, DUT state | **NOT_VERIFIED** | Require authenticated live observation |
| Prior Site 2 real Flash | **Historical PASS only (#1338)** | Does not qualify this *new* S1-C installed runtime |

## S2 review — authoritative scope rather than indiscriminate lock deletion

| Invariant | Source authority / observed implementation | Existing Host-only evidence | Audit disposition |
| --- | --- | --- | --- |
| One PPU-wide Job owner, multi-Site same-owner allowance | `software/python/plasma_server/site_manager.py` `PPUExecutionLease`, `_reserve_execution_job`, `_release_execution_job` | `test_ppu_execution_ownership.py`, `test_ppu_stage_c1_execution_scope.py` | **PRESENT; KEEP**. PPU-wide ownership is separate from physical per-Site locking |
| Asset activation/Runtime restart excluded while Jobs queued/running | `site_manager.py` `_execution_lock`, `acquire_runtime_quiesce`, `acquire_asset_set_quiesce` | `test_runtime_activation.py` | **PRESENT; KEEP**. Held Asset lease is released on control socket EOF |
| Root-only C-2 Package Action authority | `plasma_server/runtime_control.py` `_peer_uid`, `_package_action` | `test_opf_s1_programming_package_job.py`, `test_ppu_stage_c_production_integration.py` | **PRESENT; KEEP**. No public Job metadata can create `TrustedProviderAction` |
| Site session authority and stale Runtime fencing | `scripts/ppu_site_worker.py` `_control`, `_drop_if_runtime_restarted`, `_execute`; Runtime PID, Job lease, UID/PGID and per-Site lock | `test_ppu_stage_c3_site_worker.py` | **PRESENT; KEEP**. The C-3 Session is not a second PPU ownership policy |
| Live FPGA identity / reloading guard | `ppu_site_worker.py` identity recheck before/after transport, `ppu_opf_reference_openocd.py` same-boot/paired image verification, native `ps_owner` admission | `test_ppu_stage_c3_site_worker.py`, `test_c3_rest_flash_cycle.py` | **PRESENT IN SOURCE; physical PL/Root proof NOT_RUN**. Keep native fence; do not move it into portable OPF Core |
| Image/target/geometry identity | C-3 `bind_image` hash/size/profile checks, PPU image/target conflict guard; Active Set selection and Reference Provider contract | `test_c3_rest_flash_cycle.py`, `test_opf_4a_openocd_reference.py` | **PRESENT; KEEP**. CompilerRegistry is offline evidence only, not a Runtime route |
| Deadline, cancellation and child cleanup | `site_worker.py` single Job deadline, C-3 session expiration/close and per-Site operation lock; native adapter process lifecycle | `test_ppu_stage_c3_site_worker.py`, `test_ppu_stage_c_production_integration.py` | **PRESENT; KEEP**. For unknown hardware outcome, no automatic resubmission |
| SAFE_OFF, sealed marker and operator recovery | `ppu_site_worker.py` seals on `TransportUnknown`, missing SAFE_OFF, FPGA identity mutation or readback mismatch; persisted `siteN.sealed` marker | `test_ppu_site_adapter_evidence.py`, `test_ppu_stage_c_production_integration.py` | **PRESENT IN SOURCE; physical negative-path evidence NOT_RUN**. Existing seal cannot be deleted as a test convenience |
| One Flash Job and authenticated success | `scripts/plasma_program.py` one POST and no retry after ambiguous response; validates result SHA, bytes, one attempt and SAFE_OFF | `test_c3_rest_flash_cycle.py`, #1347 CI | **PRESENT IN SOURCE; S1-C physical outcome NOT_RUN** |

### P0 — Unclassified C-3 Adapter crash did not persist SEALED (fix staged)

At the baseline `scripts/ppu_site_worker.py::SiteWorkerCore._execute`, an unexpected exception from `adapter.run()` returned `SOFTWARE_EXCEPTION:<type>` without a persistent `site<N>.sealed`, despite the possibility that SWD/MMIO had begun. The original `test_unknown_hardware_outcomes_and_software_errors` explicitly allowed a second Adapter operation after that simulated crash. A Python exception does **not** prove SAFE_OFF.

**Remediation in this Draft PR:** unexpected Adapter exceptions now seal the specific Site as `UNCLASSIFIED_ADAPTER_EXCEPTION` and return `OUTCOME_UNKNOWN_SITE_SEALED`; the regression now checks that no second Adapter access occurs and the marker exists. The separate verified-safe `TransportFailed` and pre-hardware `TransportDenied` handling remains unchanged. **Host-only CI: PENDING on this new HEAD.** Existing tests cover persisted seals across Worker restart; real DUT safety is NOT_RUN. The fix is **not** in `main` until independent Gate 2 approval and shall not be treated as an already-deployed guard.

**Residual:** filesystem failure while creating a persistent seal also needs independent fail-closed/recovery evidence; it cannot be tested on a live DUT merely by forcing disk failure.

**Key S2 architecture finding:** PPU-wide Lease, C-3 per-Site Session, and native FPGA Reload/PS Owner fences are **distinct trust boundaries**. Removing any as a presumed duplicate is not defensible without demonstrated equivalent safety and HIL. Do not reimplement a second general Router, Executor or Lock. S2 **source audit is complete**; S2 safety *rationalization/removal* is **NOT IMPLEMENTED** because no duplication has been proven safe to delete.

## Hardware admission gates for the one Site 2 attempt

All are **mandatory** and must be observed live immediately before the only POST:

1. Authenticate the current SWPC/Z2 target from the owner-local paired configuration; never infer hostname or use repo secrets. Pin public host key. Verify PPU ID and Bootstrap device ID.
2. Verify Z2 installed Runtime `git_sha` includes S1-C merged #1347. **Preferred exact candidate for this run: `91a4a12c0c89ffbea34152023b9d62948fb98a0f`**. If another SHA is installed, establish its equivalence before any Flash; do not claim this new path passed from old binaries.
3. Verify Bootstrap `bootstrap_ready` / `runtime_active`, Gateway `/api/health/ready`, PPU execution lease empty, Runtime activation not held; Site 2 enabled, `openocd`, `STM32F103C8T6`, idle, no queue/current Job.
4. Verify one immutable **Active** Bundle v3, its firmware SHA/size, Programming Profile, platform OpenOCD Reference Provider, installed C-3 engine SHA/ABI, target/geometry and trusted PS-local transport. No cross-Bundle fallback.
5. Verify current boot ID and FPGA Image journal/ABI pairing, qualified native Owner/reload fence, no Site 2 `SEALED` or unclosed admission record; no stray OpenOCD child. No restoration, FPGA reload, site recovery or service restart is implied by this approval.
6. Verify actual DUT power and SWD/electrical conditions through the qualified observation path. A manually typed `voltage_qualified` flag is **not** proof.
7. Submit **one** `flash_cycle` Job only; do not resubmit on timeout, interrupted connection or unknown status. Pin Job ID; collect terminal Result plus Root/C-3 evidence.
8. PASS requires `state=success`, correct Job/Site/Target/Provider/Profile, exact firmware SHA and size, `attempts=1`, `readback_sha256==image_sha256`, `bytes_verified==image_size`, `safe_off=true`, post-Job Site idle, no seal/admission residue and no OpenOCD child. Missing evidence is **FAIL_OR_INCOMPLETE** or **OUTCOME_UNKNOWN**, never PASS.

## Safest operator-side single-Job procedure (NOT EXECUTED)

Use the current canonical `scripts/plasma_program.py` with an owner-verified, locally stored **Bundle v3 with no FPGA Image**. It is preferable to the historical `plasma_site2_single_flash_path2.py` because that earlier acceptance script pins a specific historical engine SHA/old admission and does not prove the new installed Runtime.

On the *authorized SWPC integration host* with source exactly matching the tested candidate, first perform **read-only** diagnosis. The placeholders below must be filled from owner-local trusted records; do not commit values:

```bash
# Verify source and worktree without changing device state.
git status -sb
git rev-parse HEAD

# Read-only preflight. Supply an existing signed/verified Active-compatible Bundle.
python3 scripts/plasma_program.py diagnose \
  --bundle "$VERIFIED_BUNDLE_V3" --site 2 \
  --host "$PAIRED_Z2_HOST" --device-id "$BOOTSTRAP_DEVICE_ID" \
  --source-sha "91a4a12c0c89ffbea34152023b9d62948fb98a0f"
```

If the diagnosis, live identity checks and Runtime SHA `==91a4a12c0c89ffbea34152023b9d62948fb98a0f` are **all verified** and Site 2 is safely idle, perform exactly **one** authorized Job:

```bash
python3 scripts/plasma_program.py flash \
  --bundle "$VERIFIED_BUNDLE_V3" --site 2 \
  --host "$PAIRED_Z2_HOST" --device-id "$BOOTSTRAP_DEVICE_ID" \
  --runtime-sha "91a4a12c0c89ffbea34152023b9d62948fb98a0f" --source-sha "91a4a12c0c89ffbea34152023b9d62948fb98a0f" \
  --approved-once
```

The operator-side credential comes from the owner-local approved store or `--owner-token-file` with 0600 permissions, never from GitHub/chat logs. If deployed Runtime mismatch is detected, **STOP** with `HIL_NOT_RUN_RUNTIME_VERSION_MISMATCH`: the separate `runtime-deploy` mode uses the trusted Bootstrap Coordinator and immutable CI Kit, but **no deployment has been performed or implicitly authorized by this report**. If a seal exists, use **read-only** recovery diagnosis and stop; do not delete it. The `--approved-once` flag is **not a bypass** of Runtime/C-3/Root admission.

## HIL evidence required for closure

Record: actual target PPU/device IDs (redacted as appropriate), installed Runtime SHA, verified Active Bundle SHA, Engine SHA/ABI, Boot ID correlation, FPGA Image ID/ABI, Site 2 preflight, real voltage/safety observation, generated Job ID, exactly-one submit count, terminal Job/Result, readback digest/bytes, SAFE_OFF, post-Job no-seal/no-admission/no-child, and any Recovery state. Preserve only nonsecret evidence.

**Current blockers:** (1) P0 patch not yet validated by exact-head CI, merged or installed; (2) no authorized SWPC/Z2 device execution channel in this ChatGPT/GitHub-only context. Until operator-side live receipts exist, **S1-C Site 2 real Flash remains NOT_RUN**. This Draft PR is a verifiable audit/handoff; it is **not** a physical execution report, proof of device availability, Gate 2 approval, or authorization to merge/deploy.
