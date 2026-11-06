# PPU Bundle v3 — Generic Asset Set B3 (Gate 1)

**Evidence lineage:** PR #1245 merged the generic staging installer on
2026-11-02 (Host-only). PR #1308 unified B2/B3 under the single
`DeploymentCoordinator`. P4-02 extends that implementation with an explicit
Install/Activate contract. These are versioned code milestones, **not**
physical Z2/FPGA qualification.

## One trusted deployment path

```text
Console -> Bootstrap B1 upload/commit
        -> Bootstrap B2 admission (bundle.admit)
        -> Bootstrap B3 {"kind":"bundle","upload_id":"…",
                         "mode":"activate"|"stage_only","fpga_load":boolean,
                         "authorization":{owner-operation}}
        -> DeploymentCoordinator (existing deployment.lock + journal)
        -> existing Z2 Installer Core, verified Bundle v3 ZIP only
        -> /opt/plasma/assets/staged/<archive_sha256>/
        -> standard activate: connection-held Runtime Job quiescence lease
        -> /opt/plasma/assets/active.json (atomic replace + fsync)
```

The B3 request must refer to the **current** B2 admission: the same
upload, full archive SHA256, target and verified Package
qualification. The owner authorization is **fresh and B3-specific**;
`bundle.admit` is not installation authority. No Bundle field grants execution.

A locally authored ZIP needs neither `source_commit` nor Publisher metadata,
signature, GitHub upload or successful publisher CI. Optional `source_commit`
is untrusted provenance only and never compared to engineering HEAD. B2/B3
identity and reconciliation use exact archive SHA256 and transaction IDs;
absent source provenance appears as `null` in receipts. The device engine
`install-bundle` CLI takes no `--source-commit`; its required artifact SHA256,
target, API correlation, explicit mode and FPGA load selection remain.
Engineering Runtime Release and trusted Dispatcher source pins are unchanged.
See the [canonical manifest contract](../architecture/ppu-canonical-bundle-packages.md).

| Explicit B3 contract | Required B3 authority | Result |
| --- | --- | --- |
| `mode: "stage_only", fpga_load: false` | `bundle.install` | Verified staging only; `active_asset_set: null` |
| `mode: "activate", fpga_load: false` with **no** FPGA Package | `bundle.activate` | Verified staging then atomic Active selection under the trusted Runtime lease; no FPGA reload |
| `mode: "activate", fpga_load: true` with FPGA Package | `bundle.activate-fpga-load` | Existing protected Root load, Identity PASS, then Active publication while lease remains held |
| `activate` FPGA Bundle with `fpga_load: false`; `stage_only` with `fpga_load: true`; absent/invalid flags | Denied | No implicit load privilege, no false activation success |

Each successful receipt records `mode`, `ready: false`, the exact
archive SHA, Coordinator journal transaction and one of
`bundle_staged_only`, `bundle_install_and_activate`,
`bundle_install_and_fpga_load`. For standard activation, the receipt
includes an `active_asset_set` identity and generation; exceptional staging
must never claim Active. No route executes a Parser, native binary, Runtime
Job or DUT operation as a side effect.

The factory provisions `ppu-bundle-install-policy.json` with schema
`plasma.ppu.b3-install-policy.v2`, mode `development`,
`modes: ["activate", "stage_only"]`, and only `actions:["install","verify"]`.
The factory policy is **not** a public HTTP field and does not authorize
privileged FPGA operations.

## Failure and recovery

- Archive, SHA, target, owner authorization and optional FPGA static
  qualification are revalidated fail-closed at B3.
- The existing Runtime control socket owns the connection-held Job
  quiescence gate. Busy/queued/cancelling Jobs and denied or lost leases must
  prevent Active publication. An idle snapshot supplied by Console is not a
  lease.
- Identity FAIL retains the loaded FPGA Image **without** automatic
  Golden Restore; unknown physical or pointer-publish results enter
  `recovery_required`. The old `active.json` does not prove old hardware
  was restored.
- The existing guarded recovery path is the only recovery authority. Do not
  add another Journal, lock, Hardware Manager or READY state machine.
- `GET /v1/assets` reports verified **Active identity only**, with
  `ready:false`. Before a Job, independent FPGA Image/ABI, Site readmission,
  hardware ownership and ProgrammingQualification must still be proven.

## Evidence limits

This Gate 1 contract is validated by Host-only positive/negative tests and
GitHub-hosted CI. Z2 factory refresh, FPGA reload, real Runtime race tests and
DUT HIL are **NOT_RUN** without separate operator approval.
