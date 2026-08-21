# Plasma Mock Runtime Operator Guide

Status: operator-facing software guide for Mock Runtime v1.1. SWPC deployment and capacity measurements require explicit deployment approval before execution.

This guide defines what an operator sees, how to configure Mock Runtime, how to interpret Production Batch states, and how to perform the 4 MiB x 60 Site SWPC acceptance after approval.

Canonical architecture/specification: `docs/architecture/mock-runtime-v1.1.md`.

## 1. What Mock Runtime is for

Use Mock Runtime to exercise Plasma software behavior without a physical PPU/IC path:

- Facility / PPU / Site selection;
- Erase / Program / Verify / Read workflows;
- multi-PPU Batch execution;
- repeated rounds;
- Site retries;
- FAULTED-Site threshold/circuit breaker;
- deterministic injected operation failures;
- cancellation;
- Programming Asset sharing;
- Batch/Site/operation/attempt statistics.

Do not use Mock results to claim Z2, FPGA, socket, electrical, or real-IC validation.

## 2. Engineering -> Mock Settings

The Mock settings page is server-owned. The page reads the currently applied configuration from the REST Gateway and submits explicit updates back to the Gateway.

Operator controls:

- Mock enabled/disabled state.
- Default image size.
- Seed mode.
- Fixed seed when fixed mode is selected.
- Erase error rate / base time / throughput / jitter.
- Program error rate / base time / throughput / jitter.
- Verify error rate / base time / throughput / jitter.
- Read error rate / base time / throughput / jitter.

### Error rate

The UI uses percent with 0.1% resolution.

Examples:

```text
0.0%  -> 0 per mille
0.1%  -> 1 per mille
5.0%  -> 50 per mille
100%  -> 1000 per mille
```

This is an injected software failure probability per operation attempt.

### Image size

Allowed range:

```text
64 KiB .. 4096 KiB
step = 64 KiB
```

The current product default is 256 KiB.

### Seed mode

`Auto`:

- the server resolves a new 63-bit execution seed when an execution snapshot is frozen;
- the resolved Batch seed is shown through Batch provenance;
- changing settings later does not change a running Batch.

`Fixed`:

- use when reproducing a specific deterministic run;
- the same full execution identity produces the same pseudo-random timing/failure stream;
- changing Facility, PPU, Site, round, operation, attempt, Batch ID, or profile revision intentionally changes the derived per-attempt stream.

### Applied Configuration

Treat the **Applied Configuration** card as the source of truth, not unsaved form inputs.

Record at least:

- profile revision;
- seed mode;
- fixed seed when applicable;
- default image size;
- E/P/V/R error/timing values.

## 3. Production Batch policy controls

Production Batch exposes three execution policy controls.

### Repeat Count

`repeat_count` is the number of complete selected-operation rounds required per Site.

Example:

```text
Selected operations: Erase + Program + Verify
Repeat Count: 3

SITE-01:
  Round 1: E -> P -> V
  Round 2: E -> P -> V
  Round 3: E -> P -> V
```

Sites progress independently. There is no global round barrier.

### Site Retry Limit

`site_retry_limit` is the number of retries after the first attempt.

```text
Retry Limit 0 -> maximum 1 attempt
Retry Limit 1 -> maximum 2 attempts
Retry Limit 2 -> maximum 3 attempts
```

A successful retry keeps the Site in the Batch and the attempt/retry statistics preserve the earlier failed attempts.

If the logical operation still fails after the allowed attempts, that Site becomes `FAULTED`.

### Failed Site Stop Threshold

`failed_site_stop_threshold` is an optional Batch circuit breaker.

Example:

```text
Threshold = 3

FAULTED count 1 -> Batch continues
FAULTED count 2 -> Batch continues
FAULTED count 3 -> Batch controlled stop
                  Batch -> ERROR
```

The comparison is `faulted_site_count >= threshold`.

The threshold cannot exceed the number of selected Sites.

## 4. Site state definitions

These definitions are canonical. UI wording, logs, reports, User Manual, training material, and localized documentation must preserve the same meaning.

| State | Operator meaning | What to do |
|---|---|---|
| `READY` | Site is selected but has not started. | No action unless it remains READY unexpectedly after Batch start. |
| `RUNNING` | Site is executing an operation/round. | Observe operation, progress, round, and attempts. |
| `SUCCESS` / `PASS` | All required work for this Site completed successfully. | Normal pass result. |
| `FAULTED` | A real operation result failed/timeout and all configured retries were exhausted. | Treat as DUT/Site process failure. Inspect operation, round, failure source, socket/contact/target assumptions when using real hardware later. |
| `ERROR` | Plasma infrastructure/control path failed, so a trustworthy DUT pass/fail result is unavailable. | Investigate PPU/Gateway/Server/interface/runtime/network/software path. Do not classify the IC as failed from this state alone. |
| `STOPPED` | Batch policy prevented this unfinished Site from continuing after a Batch-wide stop condition. | Inspect the Batch error/stop reason and the Site that triggered it. STOPPED alone is not a DUT failure. |
| `CANCELLED` | Operator Batch/PPU cancellation stopped the Site before completion. | Normal operator-controlled termination; rerun if required. |

The most important distinction:

```text
FAULTED
= Plasma executed the operation and obtained a trustworthy failure after retry policy.

ERROR
= Plasma itself could not reliably determine whether the DUT should pass or fail.
```

Do not merge these two states in reporting.

## 5. Job FAILED vs Site FAULTED

`FAILED` is a Job/operation-level terminal result.

`FAULTED` is the Site-level isolation state used by server-side Batch Runtime after the selected operation is terminal failed/timeout and retry policy is exhausted.

Example:

```text
Program attempt 1 -> FAILED
Program attempt 2 -> FAILED
Program attempt 3 -> FAILED
Retry Limit = 2

Logical Program operation -> failed after retries
Site -> FAULTED
```

This Site does not enter later rounds.

## 6. Batch state definitions

| Batch state | Meaning |
|---|---|
| `QUEUED` | Batch exists but has not started execution. |
| `RUNNING` | Batch is actively executing. |
| `STOPPING` | Controlled cancellation/stop is being applied. |
| `SUCCESS` | Every participating Site completed successfully. |
| `PARTIAL` | Mixed non-infrastructure terminal results exist and no Batch error circuit breaker was triggered. Example: one PPU cancelled while another succeeds. |
| `ERROR` | Infrastructure failure, runtime exception, or FAULTED-Site threshold stopped the Batch. |
| `CANCELLED` | Operator cancelled the Batch, or all participating Sites ended cancelled. |

Completed Job results are never rewritten merely to make the Batch summary look uniform.

## 7. Cancellation timing

Cancellation is not retrospective.

If a Job reaches terminal SUCCESS before the cancel request is accepted, it remains SUCCESS.

If the cancel request reaches an active Job first, the affected Site can become CANCELLED.

Therefore do not diagnose a cancellation issue from button-click timing alone. Inspect the final Job/Site timestamps and state.

PPU Cancel affects only the selected PPU inside the server Batch. Other PPUs continue independently.

## 8. FAULTED, ERROR, STOPPED, CANCELLED examples

### FAULTED

```text
Program fails
Retry 1 fails
Retry 2 fails
-> Site FAULTED
```

### ERROR

```text
Program running
Gateway/PPU/interface infrastructure failure
No trustworthy DUT result
-> Site ERROR
-> Batch ERROR
```

### STOPPED

```text
Threshold = 3
Third Site becomes FAULTED
-> Batch STOPPING
-> unfinished non-faulted Sites STOPPED
-> Batch ERROR
```

### CANCELLED

```text
Operator clicks Cancel PPU while Job is active
-> affected PPU Sites CANCELLED
-> unrelated PPU continues
-> Batch may become PARTIAL
```

## 9. Yield and infrastructure quality

Do not mix product/DUT yield with infrastructure errors.

Basic programmed yield:

```text
Yield = SUCCESS / (SUCCESS + FAULTED)
```

Example:

```text
SUCCESS  970
FAULTED   25
ERROR      5

Yield = 970 / 995 = 97.49%
```

The 5 ERROR Sites must be reported separately as infrastructure/system quality.

A production dashboard should therefore preserve at least two views:

1. DUT/process yield: SUCCESS vs FAULTED.
2. System execution quality: ERROR / STOPPED / CANCELLED and their causes.

## 10. Operation and attempt statistics

Do not confuse logical executions with attempts.

For one Program operation:

```text
attempt 1 -> fail
attempt 2 -> fail
attempt 3 -> success
```

Statistics should show:

```text
logical executions = 1
attempts = 3
retries = 2
failed attempts = 2
successful executions = 1
```

This distinction is required for realistic process analysis.

## 11. Recommended deterministic operator profile

For functional acceptance where injected failures are not the subject under test:

```text
Seed mode: fixed
Fixed seed: 424242
Error rate: 0.0% for E/P/V/R
Jitter: 0 ms for E/P/V/R
```

Choose timing long enough for any intended cancellation test. Do not set timing near zero when validating Cancel behavior because the Job may truthfully finish before cancellation is accepted.

For failure/retry testing, deliberately set the target operation error rate and seed required by the scenario. Record the applied revision and seed with the evidence.

## 12. SWPC 4 MiB x 60 Site acceptance gate

Do not execute this section until explicit deployment/restart approval has been given.

Purpose:

- validate the 3 Facility / 12 PPU / 60 Site topology on SWPC;
- validate one shared 4 MiB Programming Asset under concurrent server-side Batch execution;
- measure actual RSS and high-water RSS;
- detect accidental `60 x 4 MiB` persistent image/Flash duplication;
- verify no OOM, crash, deadlock, or incorrect data result.

### 12.1 Preconditions

Record:

```text
Git commit:
SWPC date/time:
Python version:
Node version:
plasma-server PID:
plasma-web PID:
plasma-vite PID:
MemTotal:
MemAvailable before test:
```

Required software gates before deployment:

```text
Canonical terminology contract PASS
Python / PL source tests PASS
Web tests PASS
Mock CD PASS
Mock CD Browser Runtime Acceptance PASS
```

Then, only after deployment approval:

```bash
git status
git log -1 --oneline
./scripts/plasmactl test
./scripts/plasmactl ports
./scripts/plasmactl restart
./scripts/plasmactl status
```

Use the repository's actual `plasmactl` path/entry point if it differs in the deployed checkout.

Do not stage or modify unrelated user experiment files during this acceptance.

### 12.2 Baseline memory evidence

Get the Gateway MainPID from the user service:

```bash
WEB_PID="$(systemctl --user show -p MainPID --value plasma-web)"
echo "plasma-web PID=$WEB_PID"
grep -E '^(VmRSS|VmHWM|VmSize):' "/proc/$WEB_PID/status"
grep -E '^(Rss|Pss|Shared_Clean|Shared_Dirty|Private_Clean|Private_Dirty):' "/proc/$WEB_PID/smaps_rollup"
grep -E '^(MemTotal|MemAvailable):' /proc/meminfo
```

Record the values before starting the 60-Site Batch.

`VmRSS` is current resident memory. `VmHWM` is the process resident high-water mark since process start. Because `VmHWM` does not reset without process restart, the cleanest release measurement is after the approved service restart and before unrelated heavy workloads.

### 12.3 Configure deterministic 4 MiB profile

In Engineering -> Mock:

```text
Enabled: true
Default Image Size: 4096 KiB
Seed Mode: fixed
Fixed Seed: 424242
E/P/V/R Error Rate: 0.0%
E/P/V/R Jitter: 0 ms
```

For capacity measurement, use moderate deterministic throughput/timing so the Batch remains observable long enough to sample memory. Timing is not the performance result.

Suggested acceptance-only values:

```text
Erase:   base 100 ms, throughput 16 MiB/s
Program: base 100 ms, throughput 16 MiB/s
Verify:  base 100 ms, throughput 16 MiB/s
Read:    base 100 ms, throughput 16 MiB/s
```

Record the applied Profile revision.

### 12.4 Prepare one 4 MiB Programming Asset

Create one deterministic 4 MiB BIN if a suitable acceptance image is not already available:

```bash
python - <<'PY'
from pathlib import Path
import hashlib

path = Path('/tmp/plasma-4mib-acceptance.bin')
data = bytes(range(256)) * (4 * 1024 * 1024 // 256)
path.write_bytes(data)
print(path)
print('bytes =', len(data))
print('sha256 =', hashlib.sha256(data).hexdigest())
PY
```

The same file must be used for the entire Batch.

### 12.5 Start memory sampling

In a separate SWPC shell:

```bash
WEB_PID="$(systemctl --user show -p MainPID --value plasma-web)"
OUT="/tmp/plasma-web-memory-$(date +%Y%m%d-%H%M%S).csv"
echo 'timestamp_ms,vmrss_kib,vmhwm_kib,memavailable_kib' > "$OUT"
while kill -0 "$WEB_PID" 2>/dev/null; do
  TS="$(date +%s%3N)"
  RSS="$(awk '/^VmRSS:/{print $2}' /proc/$WEB_PID/status)"
  HWM="$(awk '/^VmHWM:/{print $2}' /proc/$WEB_PID/status)"
  AVAIL="$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)"
  echo "$TS,$RSS,$HWM,$AVAIL" >> "$OUT"
  sleep 0.2
done
```

Stop the sampler with `Ctrl-C` after the Batch and post-Batch idle measurement are complete.

### 12.6 Execute the 60-Site Batch

In Production:

1. Select all 3 Facilities.
2. Select all 12 PPUs.
3. Confirm total selected Sites = 60.
4. Select the same 4 MiB BIN.
5. Select `Erase + Program + Verify`.
6. Set `Repeat Count = 3`.
7. Set `Site Retry Limit = 0`.
8. Set `Failed Site Stop Threshold = off`.
9. Execute one server-side Batch.
10. Do not start a second independent Batch concurrently.

Required functional result for this zero-error profile:

```text
60 Sites SUCCESS
0 FAULTED
0 ERROR
0 STOPPED
0 CANCELLED
Batch SUCCESS
```

Expected logical operation counts:

```text
Erase   = 60 Sites x 3 rounds = 180
Program = 180
Verify  = 180
```

There should be one immutable Programming Asset snapshot for the Batch and one content-addressed image payload reused by the Mock execution path, not sixty persistent 4 MiB Job images.

### 12.7 Post-Batch evidence

Immediately after terminal SUCCESS:

```bash
WEB_PID="$(systemctl --user show -p MainPID --value plasma-web)"
grep -E '^(VmRSS|VmHWM|VmSize):' "/proc/$WEB_PID/status"
grep -E '^(Rss|Pss|Shared_Clean|Shared_Dirty|Private_Clean|Private_Dirty):' "/proc/$WEB_PID/smaps_rollup"
grep -E '^(MemTotal|MemAvailable):' /proc/meminfo
```

Retain:

- sampling CSV;
- pre/post `/proc` values;
- commit SHA;
- applied Mock Profile revision and seed;
- Programming Asset filename, size, and SHA-256;
- Batch ID;
- Batch statistics;
- final 60-Site state counts;
- any server/Gateway log anomaly.

### 12.8 Memory acceptance decision

This first SWPC v1.1 run establishes the empirical baseline. Do not invent a hard RSS threshold before measurement.

PASS requires all of the following:

- no process OOM or restart;
- no Gateway/Provider/Server crash;
- no deadlock or permanently RUNNING Site;
- all 60 Sites complete with the zero-error expected result;
- one 4 MiB Programming Asset is reused through the shared-image path;
- peak/current memory is measured and retained;
- post-Batch RSS returns toward a stable level rather than growing without bound across the three rounds;
- evidence does not indicate sixty independent persistent 4 MiB image/Flash copies.

FAIL or investigate if any of these occur:

- memory grows approximately as one full 4 MiB persistent buffer per Site;
- RSS continues monotonically increasing after rounds complete;
- the process is killed or restarted;
- JobRegistry retains full image bytes per Site;
- Verify materializes a full expected 4 MiB copy per concurrently executing Site;
- any Site result is inconsistent with the zero-error deterministic profile.

After the first empirical baseline is recorded, a numerical regression budget may be defined from measured data plus engineering margin. Do not choose that budget from theory alone.

## 13. Human acceptance after SWPC deployment

Recommended minimum operator sequence:

1. Open Engineering -> Mock and confirm server-applied revision.
2. Change Program error rate by 0.1% and Apply; confirm revision increments.
3. Restore deterministic zero-error profile.
4. Production: select multiple PPUs and a non-contiguous Site subset.
5. Run E/P/V with one Programming Asset.
6. Run Repeat Count > 1 and verify independent round progress.
7. Configure a reproducible failure/retry case and confirm attempts/retries.
8. Exhaust retries and confirm Site `FAULTED`, not `ERROR` or Disabled.
9. Configure a FAULTED-Site threshold and confirm Batch controlled stop with unfinished Sites `STOPPED`.
10. Run a deliberately long operation and Cancel one PPU while Sites are RUNNING; confirm that PPU cancels while another PPU continues.
11. Cancel an entire Batch and confirm no later operation dispatches after the cancel barrier.
12. Inspect Batch statistics and state labels.

Do not interpret a fast operation that already completed SUCCESS as a failed cancellation. Cancellation cannot rewrite a terminal Job.

## 14. Evidence and release language

Acceptable release statement after GitHub CI only:

```text
Mock Runtime v1.1 software validation passed.
```

Acceptable statement after approved SWPC test:

```text
Mock Runtime v1.1 SWPC deployment and 4 MiB x 60 Site capacity acceptance passed,
with recorded memory evidence.
```

Do not state any of the following without the corresponding hardware work:

```text
Z2 validated
FPGA validated
physical socket validated
real IC programming validated
hardware throughput validated
```

## 15. Future User Manual requirement

When a formal end-user manual is produced, this document's state definitions are normative input. At minimum the manual must include:

- Site state table;
- Batch state table;
- `FAULTED` vs `ERROR` distinction;
- `FAILED` Job vs `FAULTED` Site distinction;
- `STOPPED` vs `CANCELLED` distinction;
- retry semantics;
- FAULTED-Site threshold semantics;
- yield formula and the exclusion of infrastructure ERROR from DUT yield;
- cancellation timing/truthfulness rule;
- Mock timing non-hardware disclaimer.

Localization may translate explanations, but must not change these semantics.
