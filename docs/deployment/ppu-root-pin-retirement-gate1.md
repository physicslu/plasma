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

## Owner-operated single-machine replacement (PR #1252)

The reviewed, root-owned source tree under
`/opt/plasma/privileged/fpga-root` is provisioned and SHA256-verified **once
during controlled installation** (`ppu-privileged-source-install.py`).
The Root Entry does not rehash every reviewed Python source on each FPGA
operation. It only accepts a fixed command allowlist, fixed source path,
fixed interpreter and Linux root-owned non-writable path protections.
A Bundle cannot supply an executable path to the Root Entry.

The local Bundle admission file is a distinct exact SHA256 allowlist:
`plasma.ppu.bundle-authority.v2` under device service control, with no
Publisher/expiry/Git Commit Pin. FPGA image Target/ABI/Identity and
Owner Lock, per-Site SWD safeguards, Root recovery and Runtime quiescence
are **not removed**.

SWD ABI-v5 Admission still ties its short-lived session to the protected
Root source Manifest stat identity and the active FPGA journal; it no longer
rehashes the installed Python closure on admission. Native C per-MMIO
verification checks the record and root-private file identity, not a
publisher-signed or Git SHA40 source. The existing manifest SHA256 becomes
an identification value, not a second file-content integrity gate.

## Remaining Gate 1 / hardware issues

- New local Bundle authority v2 must be provisioned explicitly; no
  compatibility reader for v1 is permitted.
- Immutable code and mutable FPGA journal under
  `/var/lib/plasma/privileged/fpga-deployment-state.json` need an atomic
  Z2 install/rollback procedure. Production service, interpreter, Root
  Entry and state path must be reconciled together.
- Any Host-only test claiming Code Verified/Identity PASS is simulated
  evidence only, **not** a Z2 FPGA or IC operation.
- On-device UIDs, firmware manager, `/dev/mem`, systemd confinement,
  Site locks, ABI-v5 readback and Golden Recovery are **NOT_RUN**.
- Installed old Root tree cannot be removed from Z2 without separately
  authorized HIL/rollback proof.

The exact Source Commit Pin path in historical runbooks is retired as an
execution contract but preserved as historical evidence, not an active
fallback.
