# Plasma Operator Acceptance Test Matrix

This document defines the operator-driven acceptance contract for Plasma.

The purpose is not to replace unit, source, browser, or Mock CD tests. The purpose is to make operator behavior a first-class QA input and to maintain traceability from a real operator workflow to automated regression coverage, deployment acceptance, and hardware acceptance.

## 1. First principles

Plasma acceptance is layered:

```text
Source / unit tests
  -> Browser E2E with mocked API responses
  -> Mock CD software stack
  -> Mock CD Browser Runtime Acceptance
  -> SWPC deployment acceptance
  -> Human operator acceptance
  -> Z2 / FPGA / electrical / real-IC acceptance
```

A PASS at one layer does not imply PASS at the next layer.

The Operator Acceptance Test (OAT) matrix therefore records both automated evidence and the remaining human/hardware evidence.

## 2. Scenario ID convention

- `OAT-CONN-*` — connection/session/reconnect behavior.
- `OAT-TGT-*` — Facility / PPU / Site target selection.
- `OAT-JOB-*` — Erase / Program / Verify / Read execution semantics.
- `OAT-BATCH-*` — multi-Site batch behavior and cancellation.
- `OAT-FW-*` — firmware fingerprint, cache, upload, and PPU firmware ownership.
- `OAT-LOG-*` — operator observability and downloadable logs.
- `OAT-DATA-*` — Read/download/data-integrity checks.
- `OAT-HW-*` — Z2 / PL / physical interface / real IC acceptance.

Scenario IDs are stable contracts. Tests may move between files, but the scenario ID and acceptance meaning should not be silently repurposed.

## 3. Coverage level notation

| Mark | Meaning |
|---|---|
| `AUTO-MOCK` | Playwright/browser regression with API responses mocked where appropriate. |
| `AUTO-STACK` | Real browser -> real REST Gateway -> real Plasma Server / Engineering Provider -> MockInterface. No API fulfillment by Playwright. |
| `AUTO-PY` | Python/provider/server regression. |
| `SWPC` | Must be verified after deployment on SWPC. |
| `HUMAN` | Requires intentional operator interaction / visual judgment. |
| `HW` | Requires Z2, FPGA/electrical path, socket, or real IC. |

## 4. Engineering Programming operator matrix

| ID | Operator scenario | Required pass criteria | Current automation evidence | SWPC / human gate |
|---|---|---|---|---|
| `OAT-CONN-001` | Fresh Connect | New Engineering session is created; Provider catalog becomes available; Facility/PPU/Site topology is rendered. | `AUTO-MOCK`, `AUTO-STACK` | Confirm public Gateway and UI are reachable after deployment. |
| `OAT-CONN-002` | Temporary Provider outage on the same Gateway -> reconnect | UI reports unavailable; reconnect creates a new session; catalog and target polling recover without losing the durable target selection. | `AUTO-MOCK`, `AUTO-STACK` | Disconnect/reconnect once on deployed UI and verify recovery. |
| `OAT-CONN-003` | Original Gateway -> unreachable Gateway -> original Gateway | Browser reports the transport failure; returning to the original Gateway restores session/catalog polling and preserves the previously valid Facility/PPU/Site selection. | `AUTO-MOCK` using an actual aborted browser request | Reproduce once with a deliberately unreachable endpoint during Engineering acceptance. |
| `OAT-TGT-001` | Select a non-default Facility/PPU | Selected `(facility_id, ppu_id)` is used for STATUS and Job routes; Site count matches selected PPU. | `AUTO-MOCK`, `AUTO-STACK` | Select at least one non-default PPU on SWPC. |
| `OAT-TGT-002` | Reconnect while original PPU still exists | Same Facility/PPU is restored after reconnect. | `AUTO-MOCK` | Verify once after deployment. |
| `OAT-TGT-003` | Reconnect when original PPU no longer exists | Selection falls back to canonical Default target: first Facility / first PPU. | `AUTO-MOCK` | Manual failure-injection only when catalog manipulation is available. |
| `OAT-TGT-004` | Keep arbitrary Site subset, e.g. SITE 1 / 5 / 6 | Polling must not change the operator selection. | `AUTO-MOCK` | Verify with a non-contiguous subset on SWPC. |
| `OAT-TGT-005` | Reconnect with an explicit Site subset selected | Same PPU and same valid Site subset are restored for both same-Gateway reconnect and bad-Gateway -> original-Gateway recovery. | `AUTO-MOCK`; real-stack cache test also requires Site subset preservation. | Verify once after deployment. |
| `OAT-TGT-006` | Explicitly unselect every Site | `0 / N` is a valid user state; repeated status polling must not turn it back into all selected. | `AUTO-MOCK` | Leave UI idle for several polling cycles and confirm `0 / N`. |
| `OAT-TGT-007` | Reconnect while Site selection is explicitly empty | Explicit `0 / N` remains `0 / N`; empty does not mean uninitialized. | `AUTO-MOCK` | Verify once after deployment. |
| `OAT-JOB-001` | Independent Erase | Only selected Site receives Erase; Erase does not imply Program. | `AUTO-MOCK`, `AUTO-STACK` | Verify individual Site action. |
| `OAT-JOB-002` | Independent Program | Program means write-only; selected Site receives Program only. | `AUTO-MOCK`, `AUTO-STACK` | Verify individual Site action. |
| `OAT-JOB-003` | Independent Verify | Verify is an explicit independent operation. | `AUTO-MOCK`, `AUTO-STACK` | Verify individual Site action. |
| `OAT-JOB-004` | Independent Read | Read is independent and exposes downloadable output when successful. | `AUTO-STACK` | Verify browser download. |
| `OAT-JOB-005` | E -> P -> V -> R lifecycle | Operations selected for one Site execute sequentially in requested lifecycle order. | `AUTO-STACK` | Verify status/progress/log sequence. |
| `OAT-BATCH-001` | All-Site multi-Site batch | Selected Sites execute concurrently; no Site waits for another Site to finish before entering the same operation phase. | `AUTO-STACK` plus request-routing tests | Verify with 4+ Sites. |
| `OAT-BATCH-002` | Arbitrary non-contiguous Site membership | Dispatch set equals `selected Sites x selected operations`; unselected Sites receive no jobs. | `AUTO-STACK` | Verify one arbitrary subset. |
| `OAT-BATCH-003` | Batch Cancel | All participating Sites stop; no later operation may dispatch after the batch cancel barrier; aggregate result is `CANCELLED`. | Browser regression / BatchLifecycle coverage | Verify during a long-enough Mock Program/Erase. |
| `OAT-BATCH-004` | Independent Site Cancel inside batch | Cancelled Site stops while unaffected Sites continue; aggregate result is `PARTIAL` with correct success/cancelled sets. | Browser regression | Reproduce once with at least 3 Sites. |
| `OAT-BATCH-005` | Mixed terminal results | Aggregate log distinguishes `COMPLETE`, `PARTIAL`, `CANCELLED`, and `FAILED`; it must not label a partial result as complete. | Browser regression | Inspect Job Log after cancellation/failure tests. |
| `OAT-FW-001` | First Program/Verify using a firmware image | Browser sends SHA-256 fingerprint check; cache miss is reported; binary firmware is uploaded once per PPU/session. | `AUTO-MOCK`, `AUTO-STACK`, `AUTO-PY` | Confirm log shows CHECK -> MISS -> UPLOAD START -> UPLOAD COMPLETE. |
| `OAT-FW-002` | Concurrent selected Sites use same firmware | One binary upload is shared; Site jobs carry session/SHA references rather than duplicate Base64 firmware. | `AUTO-MOCK`, `AUTO-STACK`, `AUTO-PY` | Inspect Job Log / browser Network once if needed. |
| `OAT-FW-003` | Repeat same firmware in same session/PPU | Fingerprint check occurs; cache hit is reported; no additional binary upload occurs. | `AUTO-MOCK`, `AUTO-STACK`, `AUTO-PY` | Confirm `CACHE HIT · reference only · no binary upload`. |
| `OAT-FW-004` | Change firmware contents | Different SHA-256 produces cache miss and replacement upload. | `AUTO-MOCK`, `AUTO-PY` | Optional manual check with a second BIN. |
| `OAT-FW-005` | Reconnect then use same firmware | New session clears previous firmware cache; first Program/Verify after reconnect must upload binary again. | `AUTO-MOCK`, `AUTO-STACK`, `AUTO-PY` | Confirm reconnect log and new upload. |
| `OAT-FW-006` | Same PPU, same active firmware across Sites/sessions | Same SHA may run concurrently on multiple Sites. | `AUTO-PY` | Future multi-browser SWPC acceptance when needed. |
| `OAT-FW-007` | Same PPU, different active firmware while jobs are running | Server rejects conflicting firmware with recoverable busy semantics until active lease is released. | `AUTO-PY` | Future multi-browser SWPC acceptance when needed. |
| `OAT-FW-008` | Size-aware Mock timing | Mock duration scales with firmware size; Program of the operator test image must be long enough to exercise cancellation. | `AUTO-PY`; runtime acceptance indirectly exercises it | Human timing is diagnostic only; do not treat Mock timing as hardware performance. |
| `OAT-LOG-001` | Job Log ordering | Newest event is at the top. | `AUTO-MOCK` | Visual confirmation. |
| `OAT-LOG-002` | Firmware transfer observability | Log distinguishes fingerprint-only check, hit/miss, binary upload start/complete, and new session/cache clear. Network request count remains source of truth. | `AUTO-MOCK`, `AUTO-STACK` | Compare Log with browser Network only when diagnosing. |
| `OAT-LOG-003` | Batch result observability | Final aggregate lists success/cancelled/failed Sites explicitly. | Browser regression | Inspect operator log after batch tests. |
| `OAT-LOG-004` | Download `.log` | Browser exposes visible `Download .log`; exported file uses same newest-first order as UI. | `AUTO-MOCK` using real Playwright download event and file-content comparison | Download once on SWPC for release acceptance. |
| `OAT-DATA-001` | Program -> Verify -> Read deterministic bytes | Read result length and bytes match programmed deterministic input for tested range. | `AUTO-STACK` | Repeat on SWPC Mock before real hardware validation. |
| `OAT-DATA-002` | Read file naming/download | Successful Read provides the expected output filename and download action. | `AUTO-STACK` | Browser download must succeed. |

### Permanent reconnect coverage rule

`OAT-CONN-002` and `OAT-CONN-003` are complementary permanent regressions. They must both remain in the suite.

```text
same-URL reconnect
  -> exercises Provider/session recovery while transport identity is unchanged

bad-Gateway -> original-Gateway round trip
  -> exercises transport-endpoint changes without losing durable target identity
```

A PASS in one scenario must never be used as justification to remove, weaken, or replace the other scenario. The same rule applies to the explicit-zero Site-selection reconnect case and the missing-PPU -> Default fallback case because each exercises a distinct state transition.

## 5. Canonical operator-driven smoke sequence

This sequence is the preferred human acceptance flow because one continuous session exercises state transitions that isolated happy-path tests can miss.

```text
1. Fresh Connect.
2. Select a non-default 6-Site PPU.
3. Select all Sites and run E -> P -> V with deterministic firmware.
4. Confirm first firmware use is CACHE MISS + one binary upload.
5. Run same batch again and confirm CACHE HIT + no binary upload.
6. Select a subset and perform Batch Cancel.
7. Select another non-contiguous subset; independently cancel one or more Sites.
8. Confirm unaffected Sites continue and final aggregate is PARTIAL.
9. Select a non-contiguous Site subset and leave the page through multiple status polls.
10. Perform a same-Gateway Provider outage/reconnect and confirm the same PPU and Site subset return.
11. Change the Gateway URL to a deliberately unreachable endpoint; confirm the UI reports the transport failure.
12. Restore the original Gateway URL; confirm the same PPU and same Site subset return.
13. Confirm first firmware use after reconnect is CACHE MISS + binary upload again.
14. Explicitly unselect every Site; wait through several polls; confirm 0 / N remains.
15. Reconnect again; confirm explicit 0 / N remains.
16. Download the newest-first `.log` and retain it as acceptance evidence.
```

For an implementation that includes Read/data integrity, extend the same session with:

```text
17. Program deterministic bytes.
18. Verify.
19. Read the same range.
20. Compare byte length and content/hash.
```

## 6. Automation mapping

Current primary test owners:

| Coverage | Primary file / workflow |
|---|---|
| Engineering target selection, E/P/V/R routing, browser behavior | `software/web/e2e/tests/engineering-programming.spec.ts` |
| Operator Site selection / same-Gateway reconnect / bad-Gateway round trip / explicit zero selection | `software/web/e2e/tests/engineering-site-selection-reconnect.spec.ts` |
| Firmware cache behavior through real browser + real Gateway/Provider/Server | `software/web/e2e/tests/engineering-firmware-cache-runtime.spec.ts` |
| Baseline real-stack PPU operator and batch acceptance | `software/web/e2e/tests/mock-cd-runtime.spec.ts` |
| Browser regression CI | `.github/workflows/web-tests.yml` |
| Full software-stack acceptance | `.github/workflows/mock-cd.yml` |
| Real browser + persistent Mock CD stack | `.github/workflows/mock-cd-browser.yml` |
| Provider/server firmware cache and PPU lease | `software/python/tests/test_engineering_targets.py` and Gateway tests |

`docs/development/mock-cd.md` remains the authoritative document for Mock CD layer boundaries. `docs/development/engineering-firmware-observability-test-plan.md` remains the focused firmware/log observability specification. This OAT matrix is the cross-layer operator contract tying those tests together.

## 7. Release gate policy

For a normal software-only Engineering change:

```text
Required before merge:
- Source/unit tests PASS
- Web E2E PASS when Web behavior changes
- Mock CD PASS when runtime integration is affected
- Mock CD Browser Runtime Acceptance PASS when operator/runtime path is affected

Required before declaring SWPC acceptance:
- Explicit deployment approval
- SWPC update/restart succeeds
- Relevant OAT smoke subset is executed by operator

Required before declaring hardware acceptance:
- Z2/FPGA/physical interface/real-IC OAT rows pass
```

A GitHub CI PASS must never be reported as Z2 or real-IC validation.

## 8. Evidence to retain

For release-relevant human acceptance, retain enough evidence to reconstruct what happened:

- commit / release identifier;
- Facility / PPU identity;
- selected Site set;
- firmware filename, size, and SHA-256 prefix/full digest where appropriate;
- downloadable Engineering `.log`;
- relevant Read output/hash when data integrity is tested;
- PASS/FAIL for OAT scenario IDs executed;
- screenshot/video only when visual behavior is material.

Do not use screenshots as the sole evidence for network transfer, cache, or data integrity. For those cases, request counts, server/provider assertions, and byte/hash comparison are stronger evidence.

## 9. Hardware extension matrix

These rows are intentionally not satisfied by current Mock automation.

| ID | Future hardware scenario | Required pass criteria | Gate |
|---|---|---|---|
| `OAT-HW-001` | Z2 PS -> PL loopback | Deterministic payload crosses PS/PL path and returns byte-identical. Include 1 KiB-1, 1 KiB, 1 KiB+1 boundaries. | `HW` |
| `OAT-HW-002` | Large loopback / throughput | Exercise increasing sizes up to supported test maximum; record throughput and failures without changing correctness criteria. | `HW` |
| `OAT-HW-003` | Physical I2C/SPI/SWD target | E/P/V/R semantics map correctly to the selected physical interface/target. | `HW` |
| `OAT-HW-004` | Multi-Site electrical concurrency | Selected Sites run concurrently without cross-Site interference, power instability, or shared-bus corruption. | `HW` |
| `OAT-HW-005` | Real IC Program -> Verify -> Read | Read-back data/hash matches programmed image under the real programming algorithm. | `HW` |
| `OAT-HW-006` | Hardware cancel/recovery | Cancellation leaves the PPU/Site in a known recoverable state; subsequent job succeeds without power-cycle unless explicitly required by target algorithm. | `HW` |

## 10. Change-control rule

When an operator discovers a defect through a realistic workflow:

1. Reproduce and identify the violated OAT scenario or create a new stable Scenario ID.
2. Convert the operator workflow into the highest-value automated regression layer possible before or alongside the product fix.
3. When technically practical, run that regression against the known-bad pre-fix code and retain evidence that it fails for the intended reason (`RED`).
4. Fix the product behavior at the correct architectural boundary.
5. Run the same regression against the fixed code and require it to pass (`GREEN`).
6. Keep the regression focused on the observable contract, not incidental implementation details.
7. If automation or a pre-fix negative control cannot prove the behavior (for example electrical timing, destructive hardware state, unavailable historical environment, or real IC behavior), record why and retain it as an explicit `SWPC`, `HUMAN`, or `HW` release gate.

This is the core rule: **operator discoveries become institutional regression knowledge instead of one-time manual knowledge.**

## 11. Regression validity: Red-before-Green

For an operator-discovered software defect, a newly added regression is strongest when it demonstrates both sides of the behavioral boundary:

```text
known-bad product code + new regression
  -> FAIL for the expected observable defect (RED)

fixed product code + the same regression contract
  -> PASS (GREEN)
```

The negative control must isolate the product behavior as far as practical. Prefer a temporary branch/PR where the known-bad product commit is unchanged and only the new regression is added. Do not merge negative-control branches or intentionally failing PRs.

A useful negative-control result should show:

- the intended new regression fails;
- existing unrelated tests remain predominantly green;
- the failure message points to the violated OAT contract rather than a test harness/setup failure;
- the fixed branch passes the corresponding regression and normal CI gates.

Red-before-Green is the default validation method for reproducible software regressions, not an absolute requirement for every defect. Hardware-only, timing-sensitive, destructive, or historically unreproducible failures may require other evidence, but the exception must be explicit.
