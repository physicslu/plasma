# PPU Hardware Package Baseline v1 — Path 2 guarded B1/B2

**Gate 1 / Candidate:** based on `main` c58621afe896e6a6f57fe712c27ffcbc06a6f0e8 with PR #1219/#1221/#1222/#1223 merged. Hardware run is NOT_RUN until an actual owner-sourced Issue #981 Work Order invokes the existing trusted-main dispatcher and its registered SWPC-plasma-codex runner.

## Hardware acceptance tiers — independent verdicts

- **B1 Receive:** independently pinned real PPU identity; real private LAN bootstrap; create upload, bad per-chunk SHA256 rejected 409, send good chunks, commit; Z2 returns committed archive digest/size/Upload ID equal to transferred bytes. **PASS cannot be inferred from CI.**
- **B2 v1 Integrity/Admission:** submit a data-only Python v1 ZIP over the same live API; verify exact source SHA, board/FPGA target, archive SHA, unique 32-hex transaction ID, `admitted`, `package_admission_only`, `install_qualified=false`, `execution_permitted=false`. Negative: corrupt manifest-listed per-file digest and independently wrong target must both yield 409 and no live deployment.
- **B2 v2 Bundle:** independently submit minimal 2-component Bundle v2 with a DAG (IC data -> programming profile). An old on-device verifier can reject this: **NOT_QUALIFIED** while B1 remains PASS. No assumption that merged #1222/#1223 was installed on Z2.
- **B3 / B4:** Install/Verify/Activate/Rollback NOT_RUN. FPGA Manager, DUT and other device state NOT_RUN.
- PPU identity mismatches, active deployment, recovery_required or absent credential cause **BLOCKED or NOT_RUN before mutation**; never fix by modifying Z2 Root config, resetting an active journal, or re-provisioning an unverified profile.

## Existing path — NO new dispatcher, runner, workflow or SSH

Approved Gate 1 work uses trusted `main` `.github/workflows/plasma-engineering-runtime-dispatch.yml` on owner Issue #981:

```
execution_path: path2-cli
capability: operator-cli
scope: guarded-hardware
script: scripts/ppu_path2_hardware_baseline.py
verification: exit-code (implicit)
timeout_seconds: 600 (may extend to 1800 if justified)
```

Pin candidate open PR `pr_number` and exact `source_sha`. No auto download/test flags. The SWPC non-root Runner itself must possess these **pre-existing, owner-enrolled** items; neither a GitHub Work Order nor the repository can create them:

1. Z2 real lab IP `192.168.2.99` is the built-in first-board pin; `PLASMA_PPU_COMMISSIONING_ALLOWED_IP` may instead specify an independently enrolled different literal private IPv4. No arbitrary Work Order URL, DNS, proxy or HTTP redirect is allowed.
2. `PLASMA_PPU_BOOTSTRAP_TOKEN_FILE` = absolute non-symlink regular file, owner = Runner effective UID, `0600`, existing device-bound credential (never embed token or file contents in GitHub).
3. An independently enrolled immutable `device_id` from the **physical** Z2 Bootstrap status. Its exact value goes in the Work Order `--device-id`. **Do not invent or assume** the device ID from machine name/IP.
4. The operator-provisioned real Z2 root-private `/etc/plasma/ppu-package-target.json`: exact platform/board/fpga_part; pass those three values as Work Order argv, which the PPU verifier compares against its own protected profile. No Root profile write.
5. An eligible Runner with actual same-LAN reachability to PPU :18081 and no unexpected active job. Commissioning HTTP Bearer is only acceptable within a physically controlled isolated laboratory link. **Not production TLS or signed publisher provenance.**

**First (read-only probe):** the same script accepts `--probe --host 192.168.2.99 --source-sha <PR-exact-HEAD>` without a token or deployment fields. It requests only `GET /v1/health` and `GET /v1/status`, and records the observed device ID, Bootstrap version/API version and Runtime state. `Exit 0` on probe is NOT B1/B2 PASS; it establishes the device/version observation that must be independently pinned in the subsequent owner Work Order. The API does **not** attest the exact installed verifier source SHA, so the script records `installed_verifier_source_sha=NOT_ATTESTED`. This probe never writes, uploads or sends a Bearer token.

Expected argv shape (replace all placeholders with verified facts; not a valid copy/paste command):

```
--host <approved-private-PPU-IP>
--device-id <enrolled-ppu-device-id>
--source-sha <PR-exact-HEAD>
--platform <operator-provisioned-platform>
--board <operator-provisioned-board>
--fpga-part <operator-provisioned-part>
```

These are script `argv` elements in the single owner-authored Issue #981 JSON Work Order (schema `plasma.development.work_order.v1`). A GitHub App/bot comment **does not** satisfy the existing `github.actor == physicslu` enforcement, even if the owner approved in ChatGPT; the Work Order must actually be posted from the authenticated owner account. Do not claim a real Path 2 Run until the trusted dispatcher/Runner produced a matching job ID.

The script records a single bounded `PLASMA_PPU_HARDWARE_BASELINE_JSON=...` stdout line; Path 2 writes actual process exit code, stdout and SHA256 to its existing evidence directory. Exit 0 proves **only B1 success**, not B2 or any physical installation. Review B1, B2-v1 and B2-v2 independently from the parsed JSON and the Runner GitHub Run/Job evidence.

The source is fixed and reproducible, outputs are NOT constant: real Upload/Transaction IDs vary each run, so `exit-code` verification is used; Runner still records observed stdout SHA256. Record exact Commit SHA, Runner, Workflow Run/Job ID, Bootstrap identity/status, package SHA256, upload ID, transaction ID and target. Sanitize all outputs: **never include Bearer secrets, credential filenames, HTTP bodies or device Root private keys.**

## Gate 1 criteria and stop rules

1. GitHub-hosted tests PASS for fixed ZIPs, B1 positive+negative, B2 v1/v2 positive+negative, mismatched identity/recovery, local credential mode and HTTP host pin; never call physical Z2 in CI.
2. Real SWPC Runner exact PR SHA and Work Order SHA accepted through current Issue #981 dispatcher with physical `operator-cli` scope and genuine Run/Job/Exit/Stdout SHA.
3. **B1 PASS** is a valid independent Hardware Baseline even when on-device Bundle v2 Admission is NOT_QUALIFIED. B2 v1/v2 judgments must reflect real receipts, not main-branch source.
4. If the CLI could not run, or the authenticated owner event / token / device profile is missing, mark `NOT_RUN`; if v2 fails due installed Z2 revision, mark v2 `NOT_QUALIFIED`. Do NOT deploy new Bootstrap automatically.
5. Draft PR, do not merge before owner Gate 2; no PPU deployment, install, activation, FPGA Manager, DUT or Factory Recovery modification.

**Known prior evidence:** 2026-10-30 PR #1219 physical Admission was operator-reported, not an independently captured Path 2 job; #1221 factory script updates were manually installed and no matching V2 physical run was established. This Gate 1 seeks a fresh reproducible actual-run record, not relabelling the operator transcript.
