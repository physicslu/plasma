# F1-B Path 3 — Codex as-run operation ledger (2026-10-20)

**Historical execution record, NOT an executable recipe or permission to repeat the load.**

Source: [Actions Run #39395142726](https://github.com/physicslu/plasma/actions/runs/39395142726), [Artifact #12251322848](https://github.com/physicslu/plasma/actions/runs/39395142726/artifacts/12251322848), authoritative engineering report in the nested artifact `.plasma-path3-evidence/engineering-report.md`; report SHA256 `85e8ab98283a935fe72aa125afb4c273c2bee198e2b2dc3347f310b19d335a9d`. Source PR #1074 pinned commit `38461a153afef7e09c360019acf8070eeb6dbe31`. The repaired target program was archived at `pl/hil/f1b_owner_once.py`, SHA256 `5c3d8b6e834ba33f429163bae8da265b030b8d57eed2fb2fea74186e822cc841`; this PR preserves the **exact** final file. The original unmodified wrapper in `reviewed-source.tar` was superseded after a pre-load Python import fix; do not execute the old version.

## Exact historical sequence and observed exits

| # | Codex performed | Observed result / disposition |
|---|---|---|
| 01 | Read candidate source and `git status -sb` without mutation | Exit 0; detached candidate HEAD; read existing `f1b`, `one_shot`, `development`, MMIO backend and recovery controls |
| 02 | Tried local `python`, then switched to `python3` | Initial command exit **127** because `python` missing; corrected without affecting FPGA |
| 03 | Used already-enrolled private pinned-host-key SSH and a password-fed sudo channel | SSH PASS; `sudo -S -p '' /usr/bin/id -u` exit **0**, uid 0; no credentials copied into logs |
| 04 | Read-only root inspection of firmware, FPGA manager and attached UIO | Manager `operating`; original `base.bin` present; no driver unbind/restart; exploratory optional `resource` lookup exited 1 because the file did not exist; final collector handles this |
| 05 | Checked exact BIT/HWH pinned hashes, recovered FPGA Manager raw BIN from the verified BIT payload using existing `staging.bit_payload` / 32-bit word swap and the observed Bootgen NOP | **4,045,568 bytes**, SHA256 `c351f668094a2b841426c64681d44c76cb8c14b61766d90a0e10adcf3a22a3c3`; no Vivado or Bootgen rebuild |
| 06 | Created protected reviewed-source archive and staged source/firmware under a root-only directory | `python3 .plasma-path3-evidence/execute_owner_once.py stage` exit **0**, remote stage exit **0**; manifest/archive hash verified before extraction; no FPGA write |
| 07 | Executed offline positive and negative admission tests | Exit **0**: exact UIO + explicit acknowledgment PASS; changed UIO/driver/mapping/runtime/IRQ/missing acknowledgment rejected; five active-device FD checks and stale mapping rejected |
| 08 | First execution attempt: `python3 .plasma-path3-evidence/execute_owner_once.py execute` | Exit **1**, `ModuleNotFoundError: No module named 'yaml'` through unrelated package imports. **Before one-shot claim, durable evidence directory or any FPGA write** |
| 09 | Repaired wrapper imports only; avoided unrelated `plasma_interfaces.__init__` / mock imports and used the unchanged reviewed `linux_mmio.py` through importlib | `python3 -m py_compile pl/hil/f1b_owner_once.py` exit **0**; `python3 .plasma-path3-evidence/execute_owner_once.py repair-import` exit **0**; asserted no earlier claim and re-pinned source SHA |
| 10 | Final one-shot live execution: `python3 .plasma-path3-evidence/execute_owner_once.py execute` | Host exit **0**, remote supervisor exit **0**; this was the only **candidate FPGA Manager write**, not a candidate load retry |
| 11 | Before write, verified firmware/base SHA, manager original `operating` + `base.bin` kernel trace, ARMv7 little-endian CPython 3.12.13, 100 MHz FCLK0, original services/owners, full root process visibility | 88 processes observed, no retained `/dev/mem`/UIO FD/VMA; bounded exception for exact bound passive `uio1` only, **AXI isolation UNPROVEN**. Persisted and fsynced original snapshot, `RESTORE_REQUIRED` intent and exclusive one-shot claim |
| 12 | Wrote exactly one F1-B candidate BIN via the existing Linux FPGA Manager writer; checked trace and `operating` | Candidate manager trace `[82936.566766]`, one candidate write. No unbind or service restart |
| 13 | Launched the existing reaped bounded MMIO child, read exactly three aligned native-u32 Identity registers, with empty write allowlist | `0x40000000 = 0x4D534C50`, `0x40000004 = 0x00010000`, `0x40004000 = 0x00000001`, all PASS; read32=3/write32=0; child exit 0 |
| 14 | Rechecked ownership (88 visible, exact same bound condition), original boot ID, manager and recovery hash; loaded original `base.bin` exactly once | Recovery manager trace `[82939.089659]`, then verified manager `operating`, same boot/driver bindings/five services |
| 15 | Collected readonly root evidence JSON and independently asserted write counters / identity / restored state | Host evidence collection exit **0**, final `PASS_DEVELOPMENT_IDENTITY_LOAD_RESTORE`; restored-image MMIO Identity NOT_RUN |

Actual privileged supervisor command (historical; not for replay):
```text
sudo -S -p '' env OWNER_DEV_RISK_ACK=F1B_ONE_SHOT_BOUND_PASSIVE_UIO PYTHONPATH=/root/plasma-f1b-owner-20261020-once:/root/plasma-f1b-owner-20261020-once/software/python /opt/plasma/python/3.12.13/bin/python3 -m pl.hil.f1b_owner_once
```
**Do not copy/paste or rerun**. Password input was provided privately over SSH stdin, not embedded in this command. The actual host helper and raw run artifacts are archived inside the linked Action artifact. The artifact's nested archive has target JSON and source but does **not** include every raw stream file referenced in the narrative; do not invent missing logs.

## Path 2 reuse contract: independent triggers, not a monolithic macro

Path 2 shall model **three separately triggerable stages**:
| Stage / explicit trigger | Precondition and output | Transition policy |
|---|---|---|
| `Build Code` | Version-pinned source, Vivado/build constraints, produced image/HWH, SHA256 + Build Evidence | On PASS **stop by default**. Download only on an explicitly selected per-run option |
| `Download FPGA` | Owner-authorized programmer+target, verified immutable image/recovery hash, lease, current safety state; log exact manager operation, receipt and firmware identity | Trigger independently against an approved existing Build artifact. On PASS **stop by default**. Testing only on an explicitly selected per-run option |
| `Testing` | Target/profile match, loaded-image provenance, separately selected testing callback and exact expected register allowlist; evidence of observed reads/writes | Trigger independently when eligible, without recompiling/re-downloading. Never synthesize PASS from a no-op callback |

Optional flags `auto_download_after_build_success` and `auto_test_after_download_success` default to **false**, remain **independent** and must be selected by the user/operator for that execution. A stage completion by itself does not trigger the next one. Restore for transient test images is **safety cleanup**, not an implicit transition into another stage. Path 2 is the orchestrator; the common Supervisor manages Load/Restore lifecycle; the Hardware Profile defines ABI; the Driver performs MMIO; Test Callback defines the test.

Do **not** propagate `OWNER_DEV_RISK_ACK`, the dated UIO exception, hardcoded paths, password-auth helper, root privileges or one-shot claim into generic Path 2 production behavior. This run establishes a single development observation, not AXI quiescence or product programming qualification. For Path 2, implement explicit approvals, provenance, current owner/AXI safety checks, idempotency/recovery policy, operator-selected transitions, and evidence gates.

**Historical irreversible/uncertain conditions:** missing root credentials, changed pinned files or UIO, retained MMIO mappings, failed candidate load, SIGBUS/AXI hang, unreaped child, unknown restore safety ⇒ stop/UNKNOWN; no blind retry or unsafe recovery reload. This one-shot has already executed and cannot be replayed as validation.
