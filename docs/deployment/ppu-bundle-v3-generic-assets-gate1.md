# PPU Bundle v3 — Generic Asset Set B3 (Gate 1)

> **Term note:** in this document **B1/B2/B3/B4 are Bundle stages** — B1 upload/commit, B2 admission, B3 install/verify, B4 activation (incl. previous-version backup). Not the FPGA/UIO or governance meanings; see [glossary](../glossary.md#b1b2b3).

**Status:** merged in main (PR #1245), 2026-11-02. Host-only CI / Test only.
**Baseline:** latest main plus owner-approved Single Active Asset Set architecture
([PR #1244](https://github.com/physicslu/plasma/pull/1244), merged).
**Hardware boundary:** no Z2 execution, FPGA reload, systemd restart or DUT programming
authorized by this PR.

## One product installation path

```text
Console / authenticated paired Controller (private commissioning lab)
  -> POST /v1/uploads (chunks, commit with SHA256)
  -> POST /v1/deployments  {"kind":"bundle","upload_id":"...","authorization":{bundle.admit}}  [B2]
  -> POST /v1/deployments  {"kind":"bundle","upload_id":"...","fpga_load":false,"authorization":{bundle.install}} [B3]
  -> existing Bootstrap DeploymentCoordinator lock and journal
  -> existing Z2 Installer Core, verified Bundle v3 ZIP only
  -> /opt/plasma/assets/staged/<archive_sha256>/
       b3-install.json
       manifest.json
       payload/packages/<package-id>/...
```

**No product installation API, filename, absolute destination or Package
allowlist is specific to Smoke, F1-B, a target ICPN, an FPGA type, or three
hardcoded Packages.** The legacy PR #1241 Smoke-only real-HIL control scripts
are retired from the executable product tree; their evidence remains preserved
in Git history. Tests may continue using a harmless Python Smoke fixture.

**All Packages remain inert Assets** (Python, Native C, FPGA Image BIN/HWH,
Programming Profile, firmware, etc.). B3 does not execute files, load PL,
change /opt/plasma/current, switch an Asset Set or operate DUT. B3 verifies
the exact archive content against B1/B2 metadata and canonical v3
Manifest/target/dependency contract. Every staged Set retains the verified canonical `manifest.json`,
with its own SHA256 included in the B3 receipt. Every staged Set is stored under its
complete archive SHA256, not its display name. Reuse of an existing digest
requires re-verifying every installed file and the exact file set; it must not
overwrite that path. This provides Staging only, **not** Active Set activation.

## Installation authority and trust levels

Device-side factory installs `ppu-bundle-install-policy.json` mode 0600
with schema `plasma.ppu.b3-install-policy.v1`, development mode,
`install_only=true` and fixed allowed actions `install,verify`.
B3 admission requires the existing authenticated Bootstrap request;
the immediately preceding device-local B2 record for the **same upload ID**;
a verified ZIP SHA256, source commit and **device-local target profile**; and
the same single DeploymentCoordinator lock/journal and correlated receipt.
The policy is **never an HTTP upload parameter**. No custom user executable
or FPGA image gains execution privilege just by arriving in a Bundle.

In the **controlled private lab** this grants B3 install-only to the paired
Console. It does **not** establish publisher authenticity, production
authorization, confidential network transport, or Master role binding.
Product deployment must not open this endpoint to public/untrusted clients.

## Future integration boundary — P1 / P2

- **P1:** Console compares exact intended complete Asset Set identity against
  PPU Active identity; if different, transfers a complete Set. A verified
  staged Set may be atomically activated only with all relevant Jobs idle
  and exclusive ownership. No cross-Bundle fallback, no mid-Job replacement.
- **P2:** Controller separately requests an FPGA configuration; an approved
  Hand-off passes only the selected Active Set BIN/HWH/FPGA Manifest to the
  **existing protected FPGA Root Loader**. No arbitrary path passed from
  Console to Root. Preserve Source Pin, Image ABI, FPGA Manager ownership,
  Site quiescence, Golden Restore, and electrical safeguards.
- A staged or Active Set is **not READY** merely because the Bundle digest is
  correct. Real FPGA configuration and real IC ProgrammingQualification are
  independent evidence gates.

No new API schema, B4 Activation, runtime FPGA load, Programming Runtime
provider or physical HIL acceptance is claimed by P0.
