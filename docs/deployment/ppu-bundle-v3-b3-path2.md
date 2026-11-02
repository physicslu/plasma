# PLASMA Bundle v3 B3 Install-only — Development Mode / Path 2

**Gate 1 scope (PR #1241):** existing Bootstrap API, single Coordinator,
single Lock and Journal, existing Z2 PS Installer Core. No B4, previous-version
backup, Runtime service restart, FPGA load or DUT operations.

## What is now implemented

1. **Factory Bootstrap** ships the reviewed Installer Core, the canonical
   v3 verifier and a private `ppu-b3-smoke-policy.json` pinning the **exact
   source commit, ZIP SHA256, device target, bundle name and actions**.
   The ZIP is built deterministically as a CI artifact and included in
   `SHA256SUMS`. This factory policy is NOT writable through HTTP.
2. The same device `POST /v1/uploads` accepts the ZIP, checks chunk and
   complete SHA256, and commits the archive (B1).
3. The existing `POST /v1/deployments` with `kind=bundle` returns a
   **data-only** canonical v3 Admission Receipt; it is not an install grant (B2).
4. **Only after matching B2 Admission** does an explicit
   `POST /v1/deployments` request with
   `{"kind":"bundle","upload_id":"<previously-admitted-id>","install_only":true}`
   enter B3. A device-local factory policy must match the **same ZIP**,
   source SHA and trusted target. The Bootstrap worker invokes the existing
   Coordinator CLI in `install-bundle` mode; that single Coordinator controls
   the existing exclusive Lock/Journal and rechecks the archive. The existing
   Z2 Installer Core stages and re-verifies only the three reviewed Packages.
5. Files install to `/opt/plasma/bundles/ppu-b3-smoke`, **not** a Runtime
   Active Pointer. A previous B3-owned directory may be directly replaced,
   with no retained old-version backup/B4. Unknown/unowned or symlinked
   destinations are rejected. Failure after a possible write is
   `recovery_required`, never silently retried.
6. **Only after real B3 PASS** can the reviewed Path 2 script explicitly
   run the Python Smoke payload as the unprivileged Z2 `nobody` user:
   `SMOKE_VERSION=0.1.0`, `ICPN=STM32F103C8T6`,
   `FLASH_BYTES=65536`, `PASS`. This is a fixture verification only,
   not IC programming or L2 qualification.

The existing `/v1/status` returns the non-secret
`capabilities.bundle_v3_b3_install` Boolean to indicate whether the
required factory scripts and local policy files are present. This Boolean
is a **preflight hint**, not cryptographic qualification: B3 rechecks all
trusted authorization and archive evidence.

## Path 2 execution

Use the existing owner Issue #981 Work Order, `execution_path=path2-cli`,
`capability=operator-cli`, `scope=guarded-hardware`, `pr_number=1241`,
`source_sha=<exact open PR HEAD>`; script:
`scripts/ppu_path2_bundle_v3_b3_acceptance.py`. Example source-bound arguments:

```text
--host 192.168.2.99
--device-id ppu-device-7ed4b30913a9bf6101da5a7a
--source-sha <exact current PR #1241 HEAD>
```

The script uses existing enrolled SWPC→Z2 SSH and pinned host key, keeps the
Bootstrap token in memory, and checks the actual device, safe state, installed
Factory B3 capability, B1 negative/positive SHA, canonical v3 B2 Receipt,
same-upload B3 Receipt + Journal correlation, and explicit unprivileged Python
Smoke output. The exact runner Run/Job and archive SHA must be retained.

**Do not dispatch B3 while Factory B3 is absent, B1/B2 have not passed,
the device has recovery_required, the SHA pin is mismatched, or the owner
PR HEAD is no longer the Work Order SHA.** A GitHub-hosted CI PASS never
satisfies these physical prerequisites.

## Qualification and restoration boundaries

- The Bootstrap factory source itself must first be installed and health
  verified on the paired Z2 through existing owner-controlled, reviewed
  factory update procedures. This PR does **not** create an alternate SSH
  file writer or a second installer.
- Only the smoke bundle in the root-owned factory policy is authorized for
  this Gate 1. General arbitrary Python/native-C/FPGA package execution is
  **NOT QUALIFIED**.
- The Bundle install tree is separate from `/opt/plasma/current`. Factory
  Recovery and product Runtime are untouched.
- On a failed B3 transaction, preserve evidence, stop on
  `recovery_required`, and require controlled diagnosis/recovery before
  another deployment. Do not reset/rotate credentials or remove guards.
- Retain explicit distinctions **Host-only PASS**, **B1/B2 physical PASS**,
  **B3 physical PASS**, **Smoke physical PASS** and **NOT_RUN**. Never infer
  support for FPGA, SWD, IC programming or eight Sites from this test.
