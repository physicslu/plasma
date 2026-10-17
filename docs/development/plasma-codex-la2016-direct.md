# PLASMA Issue #981 — LA2016 Codex Direct Execution A/B (Gate 1 only)

**Status: direct path merged in PR #1006; later one-shot HIL failed, Gate 1 diagnosis remediation pending.** Owner has explicitly approved **Gate 1 development and offline tests** only. Gate 2 is required for merge; a **separate one-shot explicit owner approval** is required before ever creating the hardware-triggering Issue comment.

## Hypothesis and controlled comparison

The archival real 2026-10-16 `KINGST PWM1 → same LA2016 CH0` loopback was functional PASS using the pinned sigrok AppImage and host Codex. On 2026-10-17 the reviewed Python JSON Supervisor pathway was NO_GO, followed by a read-only diagnosis showing `pinned_appimage=PASS`, `usb_metadata_dac_owner=PASS`, `runner_codex_cli=PASS`, `bwrap_usb_isolation=PASS`, `codex_readonly_request=AGENT_REQUEST_SCHEMA`. This establishes a failure in JSON request validation, **not** a Codex CLI failure or a physical test result.

This A/B experiment **does not remove the old implementation**. It adds a parallel direct path using the **same** dedicated SWPC `plasma-codex` worker, pinned AppImage SHA `b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475`, same loopback wiring, same PWM profiles, same sampling resolution, but **no intermediate JSON request/action dispatch**.

| Dimension | Existing indirect path | Proposed direct path |
| --- | --- | --- |
| Github | Exact owner Issue #981 command, hosted authorizer | Separate exact owner command, hosted authorizer |
| Linux worker | Dedicated `SWPC-plasma-codex` | Same worker |
| Codex | Return fixed JSON action request | Executes sigrok commands itself in its own tool calls |
| Hardware CLI | Reviewed Python Supervisor constructs settings | Codex dynamically discovers and runs pinned sigrok-cli |
| Device isolation | bwrap hides ALL USB nodes from model | bwrap exposes ONLY one dynamically resolved LA2016 USB character node |
| File access | Read-only workspace | Read-only host with dedicated isolated temp and writable evidence folder |
| OFF | Parent shutdown + detached deadline watchdog | **Minimal independent OFF deadline guard** + final host OFF attempt |
| Acceptance | Supervisor captures/measures and reports | Agent records four original .sr; **separate deterministic post-test verifier** checks period, duty, OFF-low and SHA256 |

**This isolates one hypothesis**, but a positive direct-mode result would not prove that the Python Supervisor was the only problem. It demonstrates that the same worker can run a real Codex-controlled LA2016 capture without the JSON mediator.

## Implementation

- `scripts/plasma-codex-la2016-direct.py`: one run entry, exact owner event matcher, SHA-pinned AppImage, USB sysfs identity and passive `fuser` check, rootless bubblewrap LA-only mount namespace, actual Codex CLI, minimal timed OFF guard and final OFF attempt, post-test waveform verification, sanitized report.
- `.github/workflows/plasma-codex-la2016-direct.yml`: GitHub-hosted authorization and fully offline PR CI; **no self-hosted job is enabled for PR or push**. The dedicated SWPC Runner is reached only on exact owner-created Issue comment on merged, pinned `main`.
- `scripts/tests/test-plasma-codex-la2016-direct.py`: offline negative authorization tests, exact archived waveform replay, wrong-duty rejects, malformed archive rejects, OFF command structure, namespace construction, no unverified worker.
- No deletion or modification of old `scripts/plasma-codex-la2016.py`, original workflow, Z2 or programming runtime.

After Gate 2 merge, a separately owner-authorized **single physical** Issue #981 trigger would be:

```text
/plasma-codex la2016-direct 981
```

Do not post this command without a fresh explicit owner approval for **one bounded real LA2016 PWM test**.

## Outer security boundary vs Codex shell privileges

Codex is purposely a **direct actuator**, not merely an intent generator. Codex's inner sandbox must permit native USB ioctls; the command selects `--sandbox danger-full-access` **inside** an already established rootless `bubblewrap` mount namespace. The wrapper uses host read-only mount, mounts fresh `/dev`, bind-exposes only the single validated LA2016 USB device, masks private Z2 SSH/credential directories, and only makes the private evidence folder, temporary directory and Codex's own auth directory writable. No root/privileged Linux group is added; no host-level `sudo`, Docker, USB Hub power, Z2 login, FPGA Manager or DUT controls are invoked by the host wrapper.

This gives OS-level **filesystem/device** isolation, but is not complete security against all network paths. The Codex process still needs network egress for the model API; the current proposal uses a reviewed fixed prompt banning Z2 and other hosts, masks private credentials, and does not claim an enforced per-destination network firewall. In addition, the `plasma-codex-io` host group can access more physical devices *outside* the sandbox; the launcher must always run inside the device-limited namespace. Therefore this proposal must pass the actual **LA-only namespace preflight on the same Runner** before any PWM actuation; a hosted CI construction test alone cannot prove Linux mount/kernel compatibility or external electrical isolation.

No runtime workflow is executed until the separate hardware test authorization. Do not confuse a successful hosted CI with a real device grant validation.

## Independent OFF and evidentiary integrity

- Before running Codex, the parent must verify the current USB connection is unique, AppImage SHA matches, USB node accessible/not busy, and bwrap child can see exactly one LA USB node but no `/dev/mem` or `/dev/ttyUSB*`.
- The parent arms an independent detached 135-second OFF timer (removes GitHub tracking tag); if Codex dies or stalls before a host-confirmed shutdown receipt, it attempts `PWM1:enabled=off`.
- The parent permits no more than 118 seconds of Codex runtime. It attempts a second bounded OFF in its `finally` path whether the model succeeded, failed, timed out, or failed evidence validation.
- The timer or `finally` cannot guarantee actual physical OFF after host crash, USB disconnect, kernel hang, malformed device state or power loss. Prior to real usage, an independent operator must verify wiring and an emergency instrument OFF method. No hardware-power toggle is granted.
- Codex uses explicit PWM ON and OFF commands; four independent original captures: `1000hz-on.sr`, `1000hz-off.sr`, `2000hz-on.sr`, `2000hz-off.sr`. All non-digital model logs and last messages stay **private** on SWPC and are **not uploaded** to GitHub Actions.
- The trusted post-test verifier uses only bounded sigrok archives: CH0 metadata, 1 MHz sampling, 16-bit words, ≥20 complete cycles, expected periods and highs within ±1 sample, 20,000 or more OFF samples **all LOW**, distinct file sizes and SHA256 checks. The reported PASS requires both cases plus the host OFF command; the parent computes hashes on exact original .sr archives.
- Return NO_GO on missing, malformed, busy, ambiguous or mismatched evidence. No synthetic or archived replay is accepted in an actual Runner job. PR CI safely runs the identical verifier against **existing** archived captures as test fixtures, never reuses them as new device acceptance.

**Comparison boundary:** The earlier diagnostic's `SIGROK_FIRMWARE_PATH=NOT_CONFIGURED_INFORMATIONAL` did not imply failing firmware. An AppImage's presence/digest is not proof the live sigrok CLI can open the device. The direct physical acceptance is exactly what will test that.

## Gate structure

1. **Gate 1 (approved):** introduce the new parallel workflow/script/host-only regression tests and this documentation; submit PR; finish all hosted offline CI. No SWPC execution.
2. **Gate 2 (not yet authorized):** owner reviews exact PR HEAD, latest main, mergeability, complete CI; merge only after explicit approval.
3. **Hardware acceptance (not yet authorized):** separate explicit one-shot owner approval, then one exact Issue command on merged main. Do not retry on failure without fresh approval.
4. Only if real direct A/B acceptance passes: consider a **separate** PR retiring JSON Supervisor; never silently delete the old route.

## Open design/qualification limitations

- Outer `bubblewrap` LA-only USB bind mounting on this specific SWPC kernel is unqualified until the one-shot real Runner job. The existing read-only probe verified an **all-USB-hidden** namespace, which is not the same case.
- Native sigrok/AppImage extraction needs a writable temporary directory, provided by isolated `/tmp`. The firmware lookup environment may require additional local qualification; no firmware is installed or uploaded by this proposal.
- Runtime USB permission alone is insufficient if a different process holds the device. Race conditions beyond an advisory `fuser`+file lock require physical acceptance.
- Codex may still fail or refuse shell work, or produce invalid files. Those are honest NO_GO, not evidence that the old Supervisor is needed.

## 2026-10-17 one-shot real Direct result and Gate 1 diagnostics remediation

**Historical fact, not a successful Direct acceptance:** [run #39031253858](https://github.com/physicslu/plasma/actions/runs/39031253858) launched on trusted `main fb7e6b764611f5ea75f59c951b528c51ab0dc777`, passed GitHub authorization/worker-identity and entered the direct `codex exec` stage. The execution lasted ~118 seconds, matching the prior `subprocess.run(... timeout=118)`. Report and SHA256 checked: `result=NO_GO_OFF`, `agent_exec=NOT_RUN`, `cases=[]`, `independent_off_watchdog=ARMED`, `pwm_off_command=FAILED_OR_UNKNOWN`. No new .sr files were archived; physical OFF status was **NOT ATTESTED**. The old `NOT_RUN` sentinel was not proof the Codex subprocess had not started: it only changed after a successful return from `subprocess.run()`. A detached, unobserved watchdog attempt is likewise no proof of CH0 LOW.

The operator subsequently provided an independently run local Codex success on the **same LA2016**, ~185 seconds, with *fresh* 1kHz/50% and 2kHz/25% captured archives, verified OFF captures (each 22,496 LOW samples), and 25 evidence SHA256 PASS. It initially hit `LIBUSB_ERROR_ACCESS`; using an already-authorized `plasma-codex-io` group session via `sg plasma-codex-io` resolved it without changing host permissions. The observed success is user-supplied testimony; the local `.work/la2016-repeat/20261017T121229Z` data were **not independently fetched into this PR**. It is strong evidence that **an interactive Codex workflow can do the task**, but does not prove the separately isolated self-hosted Runner had the same supplementary groups or working libusb access.

### New Gate 1 remediation contract — no hardware work authorized

This PR modifies only the reviewed source and hosted/offline tests, **not** SWPC permissions, instruments or real hardware jobs.

- Codex direct physical test duration budget extends from 118 to 600 seconds (10 minutes). Non-actuating Codex preparation now uses 300, 600, 900, and 1200 seconds (initial attempt plus three timeout-only retries). The independent live-stage deadline attempts OFF at 635 seconds unless a successful parent OFF *command* was recorded. These are *software attempt deadlines*, **not PWM1 ON-time electrical interlocks**. A truly independent output-on watchdog would require instrument/host-independent current state sensing or a power gate, and is not claimed here.
- `invoke_codex` uses a new process session, with 0600 **SWPC-private raw stdout JSONL and stderr**. GitHub receives only enumerated stage/exit categories and elapsed duration; no raw private paths, commands, credentials or USB identities.
- Before host OFF, a hung process group gets SIGTERM, bounded reap, then SIGKILL + bounded reap. The reaper status is diagnostic only: a child that creates a new session or a kernel hang may escape. Any uncertain process ownership remains a **NO-GO**, not a verified recovery.
- Report independently retains `primary_failure` (`CODEX_TIMEOUT`, `CODEX_EXIT_NONZERO`, `FAIL_IN_EVIDENCE_VERIFICATION`, etc.), `failure_stage`, `agent_termination`, `codex_elapsed_seconds`, `pwm_off_command`, `watchdog_final_receipt` so that `NO_GO_OFF` cannot erase the earlier cause.
- The watchdog now writes a **private sanitized receipt** after either parent command confirmation or its own deadline OFF attempt. The parent waits for this outcome (including the full deadline when its own OFF fails), so a normal job uploads the receipt rather than losing it when Runner temporary storage is cleaned. The artifact can still report `PENDING_OR_UNOBSERVED` after an abnormal kill, timeout or missing receipt. Neither `COMMAND_OK` nor `DEADLINE_OFF_COMMAND_OK` proves physical CH0 LOW without a real capture.
- The outer Runner checks that `plasma-codex-io` is an **actually loaded supplementary group** (not just a name in `/etc/group`). Its bwrap preflight attempts a bounded open/close of the *single* exposed USB character node, without configuring the instrument or changing access control. This passive device-open test happens **only after a separate physical-test authorization**, not in Gate 1/PR CI. `LIBUSB_ERROR_ACCESS` may still arise from an actual libusb claim; it must remain diagnosable from the private logs.
- The independent host OFF attempt also logs stderr/stdout privately at mode 0600. Post-test waveform verifier still rejects stale archival replay and requires actual per-case OFF-low captures.

### Known risks before authorizing another physical run

The direct CLI still lives inside bwrap, whereas the local interactive test did not necessarily share that mount/user namespace; `sg` on the host is not proof the nested process can claim the USB interface. Even a successful `os.open()` does not prove a `libusb_claim_interface()` will succeed. It also remains possible that Codex may take **longer** than 600 seconds on an unusually complex diagnosis; such a result must still be reported as TIMEOUT, not retried automatically. The parent and deadline OFF attempts may both fail if USB is unavailable, busy or the host crashes. **If `NO_GO_OFF` is seen, obtain operator verification of PWM1 OFF or safe power removal before any retry.**

**Gate scope:** This PR is Gate 1 only (offline implementation and test); separate Gate 2 to merge, then separate explicit one-time hardware approval, and no automated replay.

## 2026-10-17: five-minute preparation starting budget and conditional adaptive retry (Gate 1)

The owner subsequently revised the preparation-phase initial Codex timeout to 5 minutes, followed by *three progressively longer retries on timeout*. This is implemented without extending the independent PWM watchdog across AI thinking/retry cycles:

| Stage | Attempt | Codex timeout | LA2016 USB visibility | PWM action | Auto retry on timeout |
| --- | --- | --- | --- | --- | --- |
| Inert preparation | 1 | 300 s (5 min) | No device node | **Impossible via direct USB** | If timeout and process group reaped |
| Inert preparation | 2 | 600 s (10 min) | No device node | **Impossible via direct USB** | If timeout and process group reaped |
| Inert preparation | 3 | 900 s (15 min) | No device node | **Impossible via direct USB** | If timeout and process group reaped |
| Inert preparation | 4 | 1200 s (20 min) | No device node | **Impossible via direct USB** | No further retries |
| Actual Codex Direct LA2016 | **1 only** | 600 s (10 min) | Exactly one validated LA2016 device | Actual PWM1/CH0 test | **Never** |

Each inert preparation attempt opens a separate isolated writable folder and retains **private** Codex JSONL/err. The outer bwrap sandbox masks ALL USB devices, including the LA, and read-only code and private credential boundaries are unchanged. A passive namespace check must prove USB is hidden before each retry. The purpose of preparation is to allow Codex to examine the working command contract, assess risks and plan execution without touching LA2016. This remains direct Codex work, not a JSON control protocol or an action forwarding Supervisor. This is not a claim of network isolation: the model API remains reachable and is constrained by instruction against unrelated network hosts.

If preparation returns `EXIT_NONZERO`, `SPAWN_OR_IO_ERROR`, or `TIMEOUT` without confirmed subprocess group reaping, **stop immediately**. Only a genuine `TIMEOUT` with a reaped process group may advance to the next budget. Each attempt's result is durably saved as an enumerated receipt, including all four when retries exhaust. No script automatically resubmits GitHub Issue comments or restarts a GitHub Actions run.

The **actual** Codex session sees the LA2016 USB node only **after** preparation succeeds and preflight validates device access. It runs once, for up to 600 s. A timeout or any uncertain physical PWM state is **NO-GO**, never an automated repeat. The live-stage best-effort OFF watchdog attempts shutdown after 635 s (not after the cumulative 50-minute preparation). The Actions self-hosted job retains a conservative 95-minute ceiling to accommodate worst-case 50-minute preparation + 10-minute real invocation + safety cleanup, and GitHub-hosted PR contract CI remains 8 minutes.

**Why this exception matters:** A hardware-enabled agent can activate PWM in any previous attempt. Merely receiving `TIMEOUT`, a successful sigrok `enabled=off` command, or a process termination receipt does not prove physical LOW. Automatic threefold re-execution of a potentially actuated instrument task would violate the project's single-run hardware-approval boundary and could retry with still-open USB handles. A separate explicit owner authorization is required for another physical run.

No real hardware was operated by this code change; only hosted/offline contract tests qualify these retry rules.

## 2026-10-17 — DNS recovery and private diagnostics (new Gate 1, offline only)

The approved run [Actions #39034925259](https://github.com/physicslu/plasma/actions/runs/39034925259)
failed at **CODEX_PREPARATION** with `EXIT_NONZERO` after 177.77 s — **not TIMEOUT**;
`live_attempts=0`, no new PWM, no `.sr` archives, watchdog not armed.
The GitHub Actions summary also failed independently because Python tried to
concatenate a list (`preparation_attempts`) with a string.

On SWPC the operator verified `/etc/resolv.conf` is a symlink to
`/run/systemd/resolve/stub-resolv.conf`. The real bwrap layout with
`--tmpfs /run` made `resolv.conf exists: False` and DNS `gaierror`.
A separate **non-actuating** bwrap probe that read-only binds just this stub
returned `resolv.conf: True`, `DNS: PASS`. This establishes a real sandbox
DNS defect, but **the previous 177.77-second Codex exit reason cannot be proved**
without the original private stderr, which Runner cleanup had already removed.

### Exact revised boundary

- Preserve `--ro-bind / /`, `--dev /dev`, `--proc /proc`, `--tmpfs /run`
  and `--tmpfs /tmp`. If `/etc/resolv.conf` resolves to an allowlisted
  `/run/systemd/resolve/{stub-resolv.conf,resolv.conf}`, create only
  `/run/systemd/resolve` and **read-only bind exactly the resolved file**.
  Other `/run` symlink targets fail closed; regular host resolv.conf is
  left read-only as inherited. No wholesale host /run exposure, no USB
  relaxation, no host DNS changes and no permission changes.
- Before **each inert preparation Codex invocation**, execute an independent
  Python DNS preflight **inside that exact bwrap namespace**, asserting
  resolv.conf is present and `socket.getaddrinfo('api.openai.com',443)`
  succeeds; suppress untrusted output. `CODEX_NETWORK_RESOLV_CONF_MISSING`
  and `CODEX_NETWORK_DNS_FAIL` are separately classified and **stop before
  Codex or USB operations**. Repeat the same DNS check before the
  once-only real Codex stage (after passive LA-only namespace probe, before
  the OFF watchdog and hardware execution).
- **DNS pass is not authentication or application-layer reachability proof.**
  It does not verify TLS/proxy, account login, an actual Codex model API call,
  or the model subscription. The stage returns the exact sanitized status
  `DNS_PASS_MODEL_API_UNVERIFIED`; Codex's own result and private
  stderr/JSONL must be consulted for genuine application failures. Never
  promote DNS PASS into a hardware acceptance verdict.
- Use a dedicated **non-root owner-only** durable directory, separate from
  `RUNNER_TEMP`:

  ```text
  ${WORKER_HOME}/.local/state/plasma/codex-runs/
    <GITHUB_RUN_ID>-attempt-<GITHUB_RUN_ATTEMPT>/
      preparation/attempt-1/codex-stdout-private.jsonl
      preparation/attempt-1/codex-stderr-private.log
      preparation/attempt-1/last-message-private.txt
      ...
      codex-stdout-private.jsonl
      codex-stderr-private.log
      parent-off-private.log
      watchdog-off-private.log
  ```

  The private `plasma` and `codex-runs` directories must be
  owner-controlled mode **0700**; raw logs are created exclusively mode
  **0600**. Existing symlinks, unexpected owners, and collisions fail
  closed. The runner does not change privileged host settings. All
  `GITHUB_RUN_ID` and run-attempt components are validated numeric.
  On each new authorized run, owner-only numeric run folders older than
  **14 days** are pruned; non-matching and symlink paths are not followed.
  Avoid manual upload of these private files to GitHub; they can contain
  prompts, file contents and credentials. Only sanitized `report.json`,
  `exit_code`, hashes and original waveforms belong in Artifacts.
- Summary printing now serializes lists/dicts with `json.dumps`, avoiding
  the secondary `TypeError`. Network status is a separate field. Existing
  5/10/15/20-minute retry sequence and **single 10-minute live stage**,
  fixed host OFF, and 635s best-effort guard remain unchanged.

### Operator-only read-only investigation

For a future authorized GitHub run ID, inspect on SWPC **without starting a
hardware job**:

```bash
RUN=<numeric-github-run-id>
WORKER_HOME=$(getent passwd plasma-codex | cut -d: -f6)
BASE=${WORKER_HOME}/.local/state/plasma/codex-runs
sudo find "$BASE" -maxdepth 1 -type d -name "$RUN-attempt-*" -print
sudo ls -l "$BASE/${RUN}-attempt-1/preparation/attempt-1/"
sudo tail -n 80 "$BASE/${RUN}-attempt-1/preparation/attempt-1/codex-stderr-private.log"
```

Do not paste raw stderr/JSONL into public issues; manually redact secrets,
private paths and tokens before sharing summaries. Never infer PWM1 electrical
OFF from a command exit code or a watchdog software receipt.

**Gate boundary:** all new tests in this change run offline on GitHub-hosted
CI; **no self-hosted runner**, issue comment dispatch, SWPC login, real
LA2016 operation, Z2, Hub or DUT access. Gate 2 merge and any further live
hardware authorization remain separate.
