# PPU Root Pin retirement — PR #1252 Gate 1 expanded scope

Status: **HOST-ONLY DESIGN / MIGRATION CODE**, Z2 deployment and hardware validation **NOT_RUN**.
Owner-authorized Gate 1 change. No privilege escalation, real Root execution or FPGA load.

## Current dependency audit

- B3 HTTP `fpga_load=true` is implemented in current main as an exclusive
  Coordinator transaction and runs `systemd-run` with the fixed privileged
  `/usr/local/libexec/plasma/z2-path2-root-entry bundle-load <AssetSetSHA>`.
- The retired Path 2 Git pin is a root-owned source tree beneath
  `/root/plasma-path2-approved` with both a 40-hex commit and a
  source-SHA list; it also serves `download/test/restore`.
- SWD ABI-v5 Site Admission `scripts/z2/plasma_swd_site_admission.py`
  independently hard-codes the old root tree and file digest allowlist.
  `software/native/swd/plasma_swd_openocd5088_ps_owner.c` re-checks the
  old 40-hex commit pin on every MMIO transaction. Their records and
  simulator fixtures are **not** migrated by the first code-closure patch.
- Several operator/diagnostic/HIL scripts reference that tree explicitly,
  and historical evidence MUST NOT be rewritten as current PASS.

## Replacement contract

1. Source code is the **factory-reviewed fixed closure**, not arbitrary
   Bundle-supplied executable content. Only `pl/hil/fpga_image_root.py`,
   guard, admission and the necessary `plasma_interfaces` modules are
   allowed. A root-owned `.plasma-privileged-code.json` records their
   exact SHA256; no Git Source Commit Pin is accepted by the new entry.
2. `scripts/ppu_privileged_source.py` qualifies the whole installed tree
   at `/opt/plasma/privileged/fpga-root`: root-owned non-writable ancestry,
   no symlink/extra Python/bytecode, exact inventory and SHA. It does not
   authorize a Bundle, trust a writable Python interpreter, access FPGA,
   or grant OS privileges.
3. `scripts/ppu-privileged-source-install.py` is an explicit one-time,
   root-only **provisioning mechanism** for that closure from fixed factory
   inputs. It does not install onto Z2 in this PR, and must not silently
   replace a live FPGA owner's implementation. Existing installed root
   recovery/source remains untouched until separately qualified migration.
4. The fixed privileged Root Entry retains only the exact bounded
   `bundle-load <64-hex Asset Set SHA>` and `download/test/restore`
   operations. It verifies installed trusted code, calls the existing
   `pl.hil.fpga_image_root` hardware owner, retains FPGA lock, current
   image/ABI checks and Golden recovery. It does not accept a caller
   program path, arbitrary shell, Git commit pin or module name.
5. The product-wide `Bundle v3 Master Grant` still qualifies the source
   archive, and B3 still owns a separate exact FPGA image and runtime
   quiescence transaction. These are independent gates, not substitutes
   for privileged code integrity.

## Host-only SWD Site / Native C migration (implemented, not HIL)

The ABI-v5 Root Site Admission issuer now rechecks the protected code
closure and emits `plasma.swd.ps-admission.v2` with exact
`trusted_code_sha256` (64 hex) and root-private Manifest stat identity.
The Native C Owner parser and per-MMIO authorization verify the same
code identity/Manifest inode, size and mtime; `root_source_commit` and
`root_source_pinned` are no longer accepted on this updated code path.
The FPGA Root's mutable journal is moved to
`/var/lib/plasma/privileged/fpga-deployment-state.json`, outside
`/opt/plasma/privileged/fpga-root`. This is a source-only change;
physical Site Admission, Native C /dev/mem mapping, current-boot recovery
and the journal migration have **NOT_RUN** evidence.

## Remaining blockers — MUST NOT claim Gate 2 READY

- A complete, atomic and failure-safe migration procedure for the installed
  Root Entry, source and state/journal/Golden recovery on Z2 has not been
  deployed or qualified; preserving the previously loaded Image after
  journal relocation needs authentic on-device evidence.
- Source-pin dependencies remain in operator/historical HIL read-only
  diagnostics and helper scripts. Retain historical evidence but do not
  execute an obsolete Root path against the new verified entry.
- The exact Python runtime executable and factory provisioning privileges,
  root-owned `/opt/plasma` code ancestry, sysfs, `/dev/mem`,
  `ProtectHome`, Runtime quiesce and recovery on actual Z2 are **NOT_RUN**.
- Python / Native C real non-root Executors and end-to-end Action
  Journal/Receipt are **NOT_WIRED / NOT_QUALIFIED**.
- Do not delete the deployed old protected tree or activate the new Root
  Entry until a separately authorized device migration and rollback plan
  is proven.

Host-only `VERIFIED_NOT_EXECUTED` proves only source-closure checks,
not a production Site-ready or FPGA acceptance receipt.
