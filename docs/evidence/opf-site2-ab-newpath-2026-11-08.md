# PLASMA OPF S1-C/S2 — Bundle A/B Site 2 new-path hardware acceptance

**Date:** 2026-11-08 Asia/Taipei
**Current merged dispatcher main:** `e81c52656430d35cb090e7eca2d6748adf7f5599` (#1347 S1-C, #1350 S2 C-3 fix, #1352 trusted manual Release qualification)
**Installed Runtime source:** `37a7823d89973dd0f6656ed276a7a290eb033f98` from official [Release Run 42451604271](https://github.com/physicslu/plasma/actions/runs/42451604271).

## Physical receipts: two independent one-shot jobs

| Scope | Blue Pill CDC v0.2 Bundle B | Blue Pill CDC v0.1 Bundle A |
| --- | --- | --- |
| Path 2 GitHub Run | [42463696052](https://github.com/physicslu/plasma/actions/runs/42463696052) | [42464939052](https://github.com/physicslu/plasma/actions/runs/42464939052) |
| Action | One `flash` (B already Active) | One `run`: canonical Bundle B1/B2/B3 `activate` then one `flash_cycle` |
| Firmware bytes | 62,800 | 18,768 |
| Firmware SHA256 | `e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c` | `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d` |
| Verified full Readback SHA256 | Equal to firmware SHA256 | Equal to firmware SHA256 |
| Canonical Bundle SHA256 | `387b9c8c08822a6d4edb8ac7904a71a6e3143b1714453a35778c372a7517764c` | `71e9a044c7f45d0f6e608c2727961f6ada220b483225bd20b928bf06f289946a` |
| Runtime Job ID | `job-20261108-083729-d1497377` | `job-20261108-085535-99bd8fe2` |
| B3 Transaction | N/A (B already Active) | `1c10269fe19947ff965ec064216d5608` |
| Actual Job terminal state | `success` | `success` |
| Job submit count | 1 | 1 |
| SAFE_OFF | `true` | `true` |
| Automatic retry | `DISABLED` | `DISABLED` |

After these transactions, **Bundle A is the selected Active Set**. There was no deliberate FPGA reload or Runtime update during the A/B Flash jobs.

## Prior runtime/worker/hardware identity evidence

- [Runtime install Path 2 Run 42462555488](https://github.com/physicslu/plasma/actions/runs/42462555488), single Coordinator tx `99e05cd0dde44a3fa90d7c6e5029aa73`, PASS.
- [Postinstall Site 2 read-only preflight Run 42462847345](https://github.com/physicslu/plasma/actions/runs/42462847345), Gateway/Site Idle, FPGA Image/Boot/Engine selection PASS.
- [Running C-3 Worker identity Run 42463456939](https://github.com/physicslu/plasma/actions/runs/42463456939), Worker PID `925`, installed SHA256 `703d5756a9a0aa71a31cee26ee76a316f9dd70c59d97b0f8706bd0f7bfc75530`, service process started after file replacement, Runtime Git SHA PASS.
- The first attempted A submission [Run 42464842143](https://github.com/physicslu/plasma/actions/runs/42464842143) was rejected by **GitHub metadata parser** (`WORK_ORDER_MONITOR_SUMMARY_DENIED`), before executor/any B3 or Job POST. Corrected A [Run 42464939052](https://github.com/physicslu/plasma/actions/runs/42464939052) is the **only** A physical transaction in this new-path validation.

**Scope discipline:** GitHub Dispatcher wrapper's generic `physical_hil=NOT_VERIFIED` field only means the wrapper does not grade a device result; the captured `PLASMA_PROGRAM` Runtime terminal Job receipt is the evidence for this exact Site/IC/firmware. Neither A nor B proves eight-Site concurrency, physical C-2 Package Provider, ST-LINK/PC, hardware fault injection, cancellation or sealed recovery.

## S2/S3 convergence consequence

Use one canonical programming CLI: `scripts/plasma_program.py` with its existing Runtime/Bootstrap/Root/C-3 protections. The superseded `scripts/plasma_site2_single_flash_path2.py` independently submits and polls REST Flash, hard-pins one firmware and is not referenced by the current product/Runner. Retiring it removes a second hardware-write entrypoint and leaves the authoritative Coordinator, SiteManager execution lease, per-Site C-3 Session/lock and native FPGA Owner fences **untouched**.

**No new physical Job is implied or authorized by this evidence document.**
