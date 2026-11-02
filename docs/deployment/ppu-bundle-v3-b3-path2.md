# HISTORICAL — PLASMA Bundle v3 B3 Smoke-only Path 2 (PR #1241)

> **Start here:** [PPU deployment start page](ppu-deployment-start-here.md) explains how this route relates to the other PPU deployment routes.

> **Term note:** in this document **B1/B2/B3/B4 are Bundle stages** — B1 upload/commit, B2 admission, B3 install/verify, B4 activation (incl. previous-version backup). Not the FPGA/UIO or governance meanings; see [glossary](../glossary.md#b1b2b3).

> **Archived evidence only. DO NOT run these historical commands on a current PPU.**
> The Smoke-only Path 2 scripts and pinned factory policy have been retired
> by [Generic Bundle v3 B3 Gate 1](ppu-bundle-v3-generic-assets-gate1.md).
> These records explain PR #1241 physical evidence but are NOT current
> product deployment instructions or a current claim of hardware readiness.


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

## Reuse of the existing physical baseline

- The physical Z2 Factory Bootstrap / Runtime baseline and the previously
  successful B1 Upload/Commit and B2 Admission tests are historical evidence.
  An unchanged hardware/network/credential environment does not require
  repeating their negative/fault-injection acceptance suites.
- **New code still needs to be installed once.** The original factory
  Bootstrap can remain healthy while lacking the B3 `install_only` handler.
  Treat enabling that new handler through the **existing** factory installer
  as a versioned incremental B3 software update, not a fresh factory
  provisioning or device re-enrollment. Preserve existing pairing, device
  target, Factory Recovery, and Runtime. No second SSH writer.
- The **new smoke ZIP requires one B1 upload and one B2 Admission** in
  the same current transaction because the B3 guard binds `upload_id`,
  `source_commit`, `archive_sha256`, target and local policy. An old
  unrelated ZIP Receipt cannot authorize this new archive; this is transaction
  integrity, not repeating qualification.
- If the installed Bootstrap lacks `capabilities.bundle_v3_b3_install`,
  or source/ZIP hashes do not match the approved candidate, stop and report
  the exact version/deployment blocker. Do not silently repin or proceed.

## Incremental B3 capability refresh (without Factory requalification)

Real Z2 Bundle v3 B1/B2 already passed on SWPC Runner
[Run #41375651779](https://github.com/physicslu/plasma/actions/runs/41375651779)
with `qualification=B1_B2_V3_PASS_B3_B4_NOT_RUN`. The first B3 attempt
[Run #41375559026](https://github.com/physicslu/plasma/actions/runs/41375559026)
stopped **before B1** with `B3_FACTORY_INSTALLER_NOT_INSTALLED`,
`exit_code=69`, `b3=NOT_RUN`. This is a missing software capability,
not a Factory environment or B1/B2 failure.

Use **the existing Factory Bootstrap Installer** to install only the new
B3 scripts and exact source/SHA policy. The new `--refresh-only` option
requires an existing installed Bootstrap and preserves its systemd unit,
state, pairing token, target profile, Runtime and active deployment pointers.
It does not create a new Bootstrap service or restart the existing one.
After its verified receipt, the Path 2 operator may restart only
`plasma-bootstrap.service` once to load the approved software delta,
then verify `/v1/status` exposes matching
`bundle_v3_b3_install`, `bundle_v3_b3_source_commit` and
`bundle_v3_b3_archive_sha256`. This is a controlled *software capability
refresh*, not requalification or re-enrollment.

The approved Path 2 script is
`scripts/ppu_path2_b3_factory_refresh.py` (exact owner PR HEAD,
`--host`, `--device-id`, `--source-sha`). It first verifies Z2 identity,
existing SSH/Bootstrap enrollment and no running/recovery deployment;
generates the exact source-bound Bundle ZIP and private policy; uses the
existing trusted SSH identity to transfer only a SHA256-checked source
archive to a unique temporary directory; verifies all source hashes on
the device; calls the **same Installer** with `--refresh-only`; restarts
only the Bootstrap unit; and checks the resulting trusted capability pin.
Missing credentials, different device/source, archive mismatch or
untrusted paths fail closed. It never executes B1/B2/B3, FPGA or DUT by
itself; keep the subsequent Smoke installation in a separate operator
step with its own Run/Job/Receipt.

## Path 2 execution

Use the existing owner Issue #981 Work Order, `execution_path=path2-cli`,
`capability=operator-cli`, `scope=guarded-hardware`, `pr_number=1241`,
`source_sha=<exact open PR HEAD>`; script:
`scripts/ppu_path2_bundle_v3_b3_acceptance.py`. Example source-bound arguments:

```text
--host <Z2_HOST>
--device-id <PPU_DEVICE_ID>
--source-sha <exact current PR #1241 HEAD>
```

The script uses existing enrolled SWPC→Z2 SSH and pinned host key, keeps the
Bootstrap token in memory, and checks the actual device, safe state, installed
B3 capability, the **single positive upload/commit of the new smoke ZIP**,
its matching canonical v3 B2 Admission Receipt, same-upload B3 Receipt +
Journal correlation, and explicit unprivileged Python Smoke output. The
previous B1/B2 qualification baseline is **reused**; negative chunk-SHA,
baseline fault injection, prior factory reinstall and the full admission
acceptance suite are **not repeated**. The exact runner Run/Job and
archive SHA must be retained.

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
