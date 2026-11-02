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

## Open integration blockers — MUST NOT claim Gate 2 READY

- Complete the ABI-v5 SWD Site Admission and Native C per-word
  `root_source_commit` migration to a **full SHA256 code identity**
  before removing the old tree on a real Z2. Their existing Root Pin
  record cannot be silently reinterpreted as a new trust token.
- Complete Path 2 and HIL script command-argument migration and
  new privileged source installation integration, including
  executable file ownership/verity and rollback semantics.
- Prove Z2 on-device UIDs, ACLs, sysfs, `/dev/mem`, systemd sandbox,
  live FPGA Manager and current-boot Golden recovery. **NOT_RUN**.
- Do not remove the deployed old protected tree or change the running
  Root Entry on Z2 without a separate physical qualification and
  explicit deployment authorization.

A successful Host-only source verification is `VERIFIED_NOT_EXECUTED`,
not a real FPGA or Site-ready receipt.
