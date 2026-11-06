# Z2 Root Privileged Code — controlled PS-only maintenance

Status: **implementation and Host-only tests only**. No Z2 deployment, DUT, OpenOCD, FPGA reload or MMIO action is authorized by this document.

## Why this maintenance exists

Runtime Site Admission no longer requires a dmesg FPGA Manager history record (PR #1326); its protected Python source and the packaged OpenOCD Site Admission entry must match this release. Refreshing the Bootstrap/Runtime alone does not replace `/opt/plasma/privileged/fpga-root`: the original `ppu-privileged-source-install.py` deliberately fails when it already exists.

A software source update **does not** need to reload the already-qualified FPGA. Keep the existing paired Image/JOURNAL so long as Boot, live FPGA Manager, hardware ABI and Site ownership checks continue to pass.

## Sequence: one explicit operator maintenance transaction

1. **Release preparation (outside Z2):** qualify the target Runtime factory, pinned Root code closure and new OpenOCD ARMv7 candidate/admission SHA. The target `ppu_privileged_source.py` verifier must include the exact five protected source files. Preserve the existing selected engine for rollback. Confirm latest merged commit and corresponding installer/engine checksums. Host-only CI is not a physical qualification.
2. **Read-only baseline (before touching a service):** identify current Boot ID, root-owned IMAGE Journal SHA256, FPGA Manager `operating`, current verified Root Code Manifest SHA256, Engine record and Site 2 REST status. Confirm Site 2 has no Seal, current Job, admission record or OpenOCD owner. An existing Seal requires its normal recovery process and must not be deleted.
3. **Controlled maintenance window:** prevent new Job admission; deliberately stop `plasma-server`, `plasma-site-worker`, `plasma-bootstrap`, `plasma-package-control` via their approved service controls. Confirm each service is `loaded/inactive/dead`. This is deliberate user-visible PPU downtime, not a normal online Runtime update. Do not stop/restart unreviewed services, run `pkill`, delete a seal or perform FPGA reset.
4. **Factory refresh:** install/verify the newly reviewed factory Bootstrap scripts and full Root closure at the fixed `/opt/plasma/bootstrap` path. It is a source staging operation; do not reactivate Jobs yet. Make sure the installed upgrade command belongs to this release.
5. **Controlled Root activation:** under the existing operator root channel, run the fixed command:

   ```bash
   sudo /opt/plasma/python/3.12.13/bin/python3 \
     /opt/plasma/bootstrap/ppu-privileged-source-install.py \
     upgrade <EXACT_CURRENT_ROOT_CODE_MANIFEST_SHA256>
   ```

   Replace the placeholder with the **verified existing** `.plasma-privileged-code.json` SHA256, never a Git commit or FPGA BIN digest. The tool refuses non-root, invalid/mismatched digest, loaded/active services, unverified current IMAGE/Boot, non-operating FPGA Manager, OpenOCD/admission owners, missing locks, untrusted old/new code or a previous unfinished maintenance transaction. No custom path is accepted by the CLI. A successful receipt is `UPGRADED_NOT_EXECUTED`. The previous fully verified root stays under `/opt/plasma/privileged/fpga-root.previous`.
6. **Verify without target I/O:** run the installed `ppu_privileged_source.py` verifier; prove the new Code Manifest SHA256 equals the upgrade receipt. Confirm the Root Journal SHA256 and Boot ID are unchanged and FPGA Manager still `operating`. No FPGA Image reload or DUT Flash is part of this step.
7. **Install/select the compatible Engine and Runtime:** use the standard SHA-verified side-by-side OpenOCD Engine install/selection mechanism for the candidate whose `plasma_swd_site_admission.py` matches merged code, and install/activate the matching C-3 Runtime Adapter. Perform engine selection while the Runtime's Job admission gate remains closed; avoid implicit service restart until all components are consistent. The existing engine must be retained for rollback. **The Root upgrade command by itself does not do this.**
8. **Service return and read-only readiness:** start the four reviewed services in dependency order under normal maintenance controls, verify their actual MainPID and health. Run the source-pinned `plasma_site2_path2_preflight.py` from a clean checkout matching deployed source. A clean observation proves readiness only in observed fields, not a DUT PASS. Then the non-DUT `plasma_site2_admission_diagnose.py` may be authorized separately for one bounded `admit 2` + automatic `revoke 2` and verifies no residual admission record. This is NOT a Flash test.

## Rollback (not normal job execution)

For a failed PS-only software activation, stop all four services and prove no owners. Use the verified *previous* Root manifest SHA256 from the upgrade receipt:

```bash
sudo /opt/plasma/python/3.12.13/bin/python3 \
  /opt/plasma/bootstrap/ppu-privileged-source-install.py \
  rollback <EXACT_PREVIOUS_ROOT_CODE_MANIFEST_SHA256>
```

The tool atomically returns `fpga-root.previous` to the active path (or recovers when the active directory was missing after interruption), and retains the rejected tree as `fpga-root.rejected`. Do not delete a `.next` or `.rejected` directory without a separate verified recovery plan. Restore previous compatible Runtime/Engine **before** restarting services. An unknown admission/FPGA/OS state must remain unavailable rather than be forced to PASS.

## Acceptance statuses

| Gate | Claim |
| --- | --- |
| Host-only tests + CI | Software implementation PASS only if observed |
| Root upgrade receipt | `UPGRADED_NOT_EXECUTED` with fixed code SHA, old SHA and unchanged journal |
| Engine/Runtime integration | Independently verified by installed selection/runtime identities |
| Site 2 read-only preflight | `NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS` only; physical Site lock remains unverified |
| Site 2 admission diagnosis | `ADMITTED` and `revoke=PASS` (or no residue), not physical Flash |
| STM32F103C8T6 Flash | **NOT_RUN** until separately authorized real DUT operation |

The upgrade does **not** assert hardware ABI identity by itself. Root Site Admission and the native PS owner retain that responsibility when subsequently authorized to run.
