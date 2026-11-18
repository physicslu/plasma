# PPU PR 1 — physical PYNQ-Z2 package admission (operator-reported)

**Status:** Real SWPC-to-Z2 network test reported PASS by the device operator on 2026-10-30. This document captures operator-provided console excerpts, **not** a downloaded machine-attested receipt or GitHub-hosted HIL run. Admission-only is not installation, runtime upgrade, FPGA programming, or DUT qualification.

## Tested boundary

- Source: SWPC Linux client; destination: physical PYNQ-Z2 embedded Linux ARMv7 (LAN `192.168.2.99`) with existing Bootstrap service on private commissioning HTTP port 18081.
- Software baseline: PR [#1219](https://github.com/physicslu/plasma/pull/1219), merged as `8bc6bda951f5fe5e41de189c3fad9bf4d632b408`; operator manually staged and installed updated `ppu-bootstrap-service.py` plus `ppu_unified_deployment.py`.
- Transport: private-lab HTTP with existing device-local bearer credential; TLS, publisher authenticity, and deployment authorization are **not production-qualified**. Credential values were not supplied or recorded here.
- Operator checked: `/v1/health` HTTP 200; ZIP upload/chunk transfer; upload commit; manifest admission; receipt read.
- Pre-existing Runtime services reported `active`. No Site idle measurement or independent FPGA/IO qualification was taken during this admission-only test.

## Operator-provided receipt excerpt

```text
=== 1. Upload ===
Upload ID: 539b0c08dafd4ecbafa9ddeb7940a96a
=== 2. Transfer ===
=== 3. Commit ===
Archive SHA256: ebaf67464c13e8bc75d9588c4d7c6c6d1545fab0c889e6862d1ef7116ffff58e
=== 4. Submit / Admission ===
=== 5. Read Receipt ===
Transaction ID: 4542a3dacbcd41fda512e1415d0cb0ab
State: admitted
Stage: package_admission_only
Install Qualified: False
Execution Permitted: False

PASS: REAL SWPC -> Z2 PACKAGE ADMISSION
```

This proves the operator reported a real-network successful upload and admission result. It does **not** establish that an immutable raw ZIP and signed service log were preserved or independently correlated here; do not elevate this transcript to production signing or full HIL evidence.

## Factory install integration gap / Path 3 task

The real Z2 initially lacked both `/opt/plasma/bootstrap/ppu_unified_deployment.py` and `/etc/plasma/ppu-package-target.json`, and its previous Bootstrap service lacked `admit_package()`. Manual placement of the two Python files and root-owned profile enabled the above live admission. The existing `scripts/ppu-bootstrap-installer.py` copies only the four files in `REQUIRED_SCRIPTS`, omitting `ppu_unified_deployment.py`, so a fresh factory installation would not reproduce this result.

**Scope for the independent Path 3 Draft PR:**
1. Update the **existing** Bootstrap factory-install file list to include `ppu_unified_deployment.py` (no new process, daemon, Installer layer, deploy engine, or API).
2. Extend the **existing Host-only installer regression tests** so a fresh factory install contains the dependency and accepts a safe generic package using the installed service scripts; include negative failure on a missing dependency and ensure no installer, Runtime, FPGA, or DUT side effects.
3. Keep existing Runtime behavior and factory recovery unchanged. If package target-profile installation/provisioning is needed for fresh-device admission, document its device-owned, root-private, owner-approved provisioning boundary; do not hardcode the board identity or silently write a target profile in the generic factory installer.
4. Verify applicable Python Host-only CI and repository contracts; report exact PR HEAD and GitHub Actions results. **Draft only; no merge, deployment, real SWPC/Z2 access, FPGA or DUT operations.**
5. PR #1214 is **closed/unmerged**; do not cherry-pick, copy or incorporate its changes.

**Remaining gap:** actual installed-from-factory software package receipt and target-profile provisioning remain unqualified until a later operator-authorized physical test. This PR is a reproducibility/installation-contract fix only.
