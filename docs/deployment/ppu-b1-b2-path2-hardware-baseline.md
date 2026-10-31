# PPU Hardware Package Baseline v1 — Path 2 guarded-hardware

Gate 1 candidate, open Draft PR #1224; base `main` `c58621afe896e6a6f57fe712c27ffcbc06a6f0e8`. The real physical B1 and B2-v1 PASS evidence is in [Z2 Hardware Baseline receipts](../evidence/ppu-hardware-baseline-v1-2026-10-31/README.md). This is not device installation qualification.

## One PPU Bootstrap, two independent client entry points

- **Engineering Acceptance:** SWPC existing Path 2 (`operator-cli` / `guarded-hardware`) -> enrolled, pinned Z2 SSH for temporary, *read-only* access to the existing protected Bootstrap credential -> direct Z2 `http://192.168.2.99:18081/v1/` private commissioning API. The existing credential is held in SWPC worker process memory only; no Work Order, stdout, GitHub artifact, SWPC disk token, token rotation or persistent pairing is added. Requires enrolled `~/.config/plasma/z2-login-smoke.json` and independently pinned `z2-login-known_hosts`, existing sudo authorization; denial stops, never relax Linux OS permissions.
- **Product Control Station:** Console/BFF -> Plasma Manager device-bound credential store -> exact same Z2 Bootstrap `/v1/` API. Manager route is retained and its Host-only contracts tested, but is **not** a precondition for engineering B1/B2. Local Manager `:18280` lacks mutable real-Z2 registry; this is a separate product-enrollment gap, not an engineering Receive blocker.
- These are distinct trust paths to the same on-device service. Private HTTP is **not** production secure transport and a Bearer credential is not a signed Publisher or Master policy.

## Current exact hardware scope

| Baseline tier | Qualification check |
|---|---|
| B1 Package Receive | Physical Z2 device ID, upload ID, actual HTTP chunk bytes, bad SHA256 chunk denial, committed archive SHA256/size |
| B2-v1 Integrity/Admission | Actual Package v1 upload, recorded Transaction ID, stage `package_admission_only`, `execution_permitted=false`, `install_qualified=false`; wrong member digest and target rejected by Z2 |
| B2-v2 Bundle | Independent actual 2-component DAG Bundle v2 Admission. Must stay `NOT_QUALIFIED` if installed Z2 rejects or lacks required evidence |
| B3/B4 | Install/Verify/Activate/Rollback **NOT_RUN** |
| FPGA/DUT | All physical FPGA and target programming **NOT_RUN** |

## Work Order and execution

Use existing owner-authenticated GitHub Issue #981 Dispatcher and `SWPC-plasma-codex` (no new runner/workflow/supervisor), exact candidate PR HEAD:

```text
execution_path: path2-cli
capability: operator-cli
scope: guarded-hardware
script: scripts/ppu_path2_hardware_baseline.py
argv:
  --direct-bootstrap-ssh
  --host 192.168.2.99
  --device-id ppu-device-7ed4b30913a9bf6101da5a7a
  --source-sha <candidate PR exact HEAD>
  --platform linux-armv7
  --board pynq-z2
  --fpga-part xc7z020clg400-1
timeout_seconds: 180
```

Verify actual physical Z2 `device_id` and target against on-device evidence, never trust URL or uploaded Manifest alone. The prior physical positive receipt establishes these parameters for the first board, but exact installed verifier source SHA is `NOT_ATTESTED`. For new boards/targets first perform read-only discovery and re-pin.

The script uses data-only ZIP fixtures and `/v1/uploads` create/chunk/commit plus `/v1/deployments` **Admission only**. It does not write files into the installed product area, run commands on Z2 except read-only existing protected Bootstrap credential, invoke SSH Installer, deploy binaries, alter FPGA or touch DUT.

Runner exports sanitized `PLASMA_PPU_HARDWARE_BASELINE_JSON`, process Exit Code and Stdout SHA256. The evidence reviewer must evaluate B1, B2-v1 and B2-v2 independently; exit zero is not enough. The script's result `B1_B2_V1_PASS_V2_NOT_QUALIFIED` means only first two stages are proven on physical Z2.

## Fail-closed and limits

- Missing enrolled SSH, unknown host key, unapproved target IP/device ID, denied existing sudo/token file access -> `NOT_RUN` before first Package write.
- Unknown or `recovery_required` deployment state -> `BLOCKED` before upload. No unapproved recovery/installer operation.
- A rejected or malformed B2-v2 does not invalidate B1/B2-v1; label exact missing physical qualification, never invent a cause.
- Wrong SHA/target tests must get specific Z2 verifier `409` reason, not merely any upstream `409` such as busy, pairing denied or transport failure.
- Token is only transferred through trusted SSH to volatile SWPC process memory, then used as Bearer on the isolated lab network. Explicitly report `transport_security=PRIVATE_COMMISSIONING_HTTP_NOT_PRODUCTION_QUALIFIED`. No printing/credential file copying or token reuse for install qualification.
- Draft PR until Gate 2. Do not merge, deploy PPU software, activate Package, operate FPGA/DUT, or modify Factory Recovery.

See [real SWPC→Z2 Run #41154668038](https://github.com/physicslu/plasma/actions/runs/41154668038) for first live PASS and the [versioned evidence](../evidence/ppu-hardware-baseline-v1-2026-10-31/README.md).
