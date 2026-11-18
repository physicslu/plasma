# Manager definite-FAIL SAFE_OFF receipt — Z2 2-Site HIL recheck (2026-11-16)

**Verdict: PASS.** With #1457 deployed on the SWPC Control Station, a Site-local definite FAIL (`VERIFY_MISMATCH`) now has a Manager receipt with `safe_off: true`, read from the Site Worker result. The Batch treats it as a retry-eligible definite FAIL and retried it once (`retry_limit: 1`). The healthy Site in the same Batch passed. Scope: one PPU (`z2-hil`), Sites 1 and 2, STM32F103C8T6 Blue Pills. No PPU, FPGA or Runtime change, and no fault injection.

## Gap being closed

In WP-07 step 6b (batch `332df1a4…`, [evidence](../wp07-two-site-concurrent-hil-2026-11-15/README.md)), the Site Worker reported `safe_off: true` for Site 1's `VERIFY_MISMATCH`. The Manager receipt still read `safe_off: null` / `SAFE_OFF_NOT_VERIFIED`, so the FAIL was never retry-eligible.

Cause: the C-3 Site Worker reports a FAIL as a PPU Job `error` with empty `details`, and its SAFE_OFF observation sits in `error.context.site_worker_result`. The Manager read only `details`. #1457 reads the Worker result only for a single-attempt `failed`/`error` Job whose identities all match and whose outcome is not marked unknown. The new receipt field `safe_off_source` records where SAFE_OFF came from.

## Deployed identity

| Item | Value |
|---|---|
| SWPC Control Station | `ac1cac4a7e6a` (main `ac1cac4a7`, #1457); rollback `109a97602a0c` kept |
| Z2 Runtime / Active Asset Set | `0.2.1-f1994ba5ca19` / `957ac4e6…` gen 22, Resource reuse; unchanged |
| `max_concurrent_jobs` | 2 (unchanged) |

## Procedure

One Batch carries one firmware and one MCU. The two Sites therefore had to hold different contents before the Batch could give one Site a FAIL and the other a PASS.

| Step | Batch | What | Result |
|---|---|---|---|
| A | `6904e6e4…` | Site 2 alone, erase/program/verify v0.1 (`8d3ffb02…`) | PASS, `safe_off: true` (`job_details`) |
| B | `214e264c…` | Sites 1+2 verify-only v0.1, `retry_limit: 1`, one POST | Site 1 FAIL (2 attempts), Site 2 PASS → Batch FAIL |

Before step B, Site 1 held v0.2 and Site 2 held v0.1.

## Step B results

| Site | Attempt | PPU Job | Site Worker | Manager receipt | Retry decision |
|---|---|---|---|---|---|
| 1 | 1 | `job-20261116-045826-5810bd86` `error` | `VERIFY_MISMATCH`, readback `0ecc03b3…`, `safe_off: true` (admission revoked, marker present) | `safe_off: true`, source `site_worker_failure`, reason `JOB_NOT_SUCCESS` | eligible, `DEFINITE_FAIL_SAFE_OFF_VERIFIED`, **RETRY** |
| 1 | 2 | `job-20261116-045838-60fd4c51` `error` | same | same | eligible, **NO_RETRY** → unit `RETRY_LIMIT_EXHAUSTED` |
| 2 | 1 | `job-20261116-045827-e4873126` `success` | PASS, readback `8d3ffb02…`, 18,768 B | `safe_off: true`, source `job_details` | — |

LA2016 (20 MHz, 1.4 V, 1-ms windows):
- Site 1 SWCLK (CH3) is active at 13.468–13.989 s and again at 22.751–23.146 s: the first attempt and the retry.
- Site 2 SWCLK (CH0) is active at 14.646–15.079 s, a single attempt.

After the Batch: both Sites idle, PPU not busy, no lease held, no Site sealed. The DUTs now hold Site 1 v0.2 and Site 2 v0.1.

## Not covered

- The PPU, Site Worker and Root admission code were not changed or re-qualified here.
- A FAIL whose session close fails stays `OUTCOME_UNKNOWN` by design. This recheck did not exercise that case on hardware; it is covered by Host-only tests.
- This is not a 4/8-Site or production qualification.

## Files

- `result.json`: Batch, start, run and Job IDs, per-attempt receipt fields and retry decisions, the Site Worker failure fields, LA bursts, and the `.sr` SHA-256 values.
- `b-batch-final.json`: final Manager Batch for step B.
- `b-run-site1-attempt1.json`, `b-run-site1-attempt2.json`, `b-run-site2-attempt1.json`: Manager runs with full receipts for step B.
- `a-run-site2.json`: Manager run for step A.

Raw LA captures (`.sr`) and the 500 ms Z2 samples stay in the SWPC evidence store `wp07-two-site-hil-20261115/recheck-20261116-*`. Only their SHA-256 values are recorded here.
