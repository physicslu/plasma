# PR #1428 — Site 1 / Site 2 real STM32F103 HIL evidence (2026-11-15)

**Verdict: PASS for two sequential, independent Site execution routes.** Captured by trusted Path 3 runner [Run #43621296849](https://github.com/physicslu/plasma/actions/runs/43621296849), job `132527432483`, from PR source `783102b9e5521bbced4be4fb1f3f494bdcab299c`. Original [GitHub Actions Artifact #14124701335](https://github.com/physicslu/plasma/actions/runs/43621296849/artifacts/14124701335). The original artifact is time-limited; this commit preserves the evidence-critical data in Git. PR merge is **not** authorized.

| Site | Manager Start ID | Batch ID | Job ID | Result |
|---|---|---|---|---|
| 1 | `ba2d324f69cfb1a882efccb4b350e4ea` | `cfc9b75fe88de4e01fda5026a7e268e9` | `job-20261114-173152-251ffbeb` | PASS |
| 2 | `8f45084936065f42abf29587a1e5e93e` | `5f841fe97e370d2a4f14f6c17b43c7d2` | `job-20261114-173233-2e834e16` | PASS |

Both jobs have ordered **Erase → Program → Verify**, `attempts=1`, `safe_off=true`, independent Job Binding, native `PS_OWNER_ATTACHED site 1/2`, SWD `DPIDR=0x1ba01477`, STM32 device ID `0x20036410`, OpenOCD exit 0, admission revoked and native `SAFE_OFF_MODE_OFF_VERIFIED`. Each erased 19,456 bytes and programmed/read back 18,768 bytes. Both readback SHA256 values equal the 18,768-byte image SHA256: `8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d`.

**Files:** `site1-receipt.json` / `site2-receipt.json` preserve the raw Manager receipt JSON content; `acceptance.json` records provenance, Manager Start/Batch/Job IDs, final-state observations and source artifact hashes. `native-openocd-excerpt.log` is a minimally normalized non-secret transcription of both raw OpenOCD stdout segments, NOT a byte-identical copy; its original source hash is in `acceptance.json`. This distinction is intentional so source hashes are not misrepresented.

**Scope:** Two independently executed Site routes, sequentially; not concurrent operation or an eight-Site throughput qualification. Native SAFE_OFF is SWD owner/protocol-state evidence, not external analog-power evidence. `voltage_source=NOT_MEASURED` was informational and did not prohibit approved DEVELOPMENT MODE HIL. External analog SAFE_OFF and 5 MHz SWD remain NOT_VERIFIED / NOT_RUN. No independent board serial IDs were observed.

The deployment from [Run #43619099724](https://github.com/physicslu/plasma/actions/runs/43619099724) was reused; Resource Set v2 Generation 22. No redeploy, no FPGA reload, no sudoers change, no DUT blind resend, no Golden Restore and no source-code edits in this evidence-only commit. All original non-secret raw files remain attributable to artifact #14124701335 by their separately recorded SHA256 values. GitHub-hosted checks and explicit Gate 2 approval remain outstanding.
