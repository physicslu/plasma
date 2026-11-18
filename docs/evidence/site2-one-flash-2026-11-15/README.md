# Site2 one-shot Flash — 2026-11-15

**PASS: exactly one real Site2 E/P/V Flash, full 62,800-byte readback and native SAFE_OFF.**

Executed source `5eca066907d449520dec13c649378726513e48b2` on Path 3,
Runner `SWPC-plasma-codex`, [run 43712609056](https://github.com/physicslu/plasma/actions/runs/43712609056),
job `development-codex` / **132807307691**. Owner Work Order canonical SHA256
`3103a5e1c0505e1d85640a015917ad50c0227cbc7736f5c5babb0957b15728b5` verified against the dispatcher event.

| Observation | Result |
| --- | --- |
| Manager Start | `63cb924e60d0c5be5480656ab1a4ad91` |
| Manager Batch | `72582e64dbe6006b9d212b2880428176` — COMPLETED / PASS |
| Manager Run | `8c878a02c799110453e5b541a2b39715` — PASS |
| Physical Job | `job-20261115-121827-5b1f77b2` — success, Site2 only |
| Image and full readback SHA256 | `e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c` |
| Bytes written / read back / verified | 62800 / 62800 / 62800 |
| Attempts / Jobs / Batch POST attempts | 1 / 1 / 1; retry_limit=0, repeat=1; no resend |
| Native SAFE_OFF / admission revoked | true / true; OpenOCD exit 0, `SAFE_OFF_MODE_OFF_VERIFIED` |
| Final state | Site2 idle, queue 0, PPU active Jobs 0, no owner, no seal/admission record |
| Resource reuse | true; no activation or FPGA load |

The unchanged `one_attempt` function was called **once**, through a private audited
wrapper. Existing focused host tests: **23 passed**. The smoke CLI was never invoked.
The request ledger records four distinct control-plane POSTs: preview plan,
VOID, Start allocation and **one** Batch execution POST. Preview Start
`6607ab73b1ea98acf34f1b91c62973f5` was voided with `NOT_ACCEPTED` before execution.
The one execution response was observed and its receipt validated; no unknown outcome occurred.

## Prior-run reconciliation and current admission

Used the existing sudo-to-owner UID1000 route, without sudoers edits. The current
Manager state directory contained no programming journals before this submission.
The archived directory `local-control-station.archive.20261115T110922Z.pid3970823`
contains 45 Runs, 62 Starts, 14 legacy Batches and 15 v2 Batches. Latest Run and
v2 Batch updates were respectively 03:07:22.429773 and 03:07:22.601941 UTC;
no unresolved Run/Batch outcome or later transaction was found. Owner-readable
Manager service journal records the 11:09:22 and 11:49:27 UTC starts, followed by
read-only status relays. Combined with retained run 43711477559's zero-attempt
record, run 43711950640's no-POST report, unchanged latest Site2 Job
`job-20261115-030715-47406b07`, and no intervening native Site2 receipt, these
reconcile the two prior continuations as no programming submission. No old
transaction was resent or changed. Archived journal digests are retained privately.

Current Z2 is paired/device-authenticated, controller Gen2 NORMAL. Enrollment
EXPIRED was observed; no re-enrollment occurred. Root held image and current boot
`4cefdc0c-f586-4d19-b126-1d8e1108c8f1` match; FPGA Manager is operating.
Protected Root admission verified image/manifest/Golden and existing development
AXI-isolation exception (`UNPROVEN_ACCEPTED_FOR_SOURCE_BOUND_DEVELOPMENT`).
Before Flash, locked read-only Site2 MMIO showed ID `0x50002`, MODE=0,
CONTROL=0, STATUS=0, FIFO levels=0, with **zero MMIO writes**. No external
OpenOCD process, Site2 seal or admission record was present.

Fixture power/wiring use the owner's existing explicit development attestation
in [Issue #981 comment 6881455945](https://github.com/physicslu/plasma/issues/981#issuecomment-6881455945),
which accepts the ready Site1/Site2 fixtures and revokes redundant analog
qualification/reconfirmation. This task's owner correction establishes physically
separate targets. Analog voltage remains **NOT_MEASURED**, external electrical
SAFE_OFF **NOT_VERIFIED**; native SAFE_OFF proves protocol/owner mode-off.
No contrary electrical symptom was observed. No additional confirmation was needed.

## CDC and disposition

SWD `site_id=2` selected the physical target independently of USB naming.
Post-write sysfs enumeration found USB serials `8D8C067A5749` and `4997124A3133`
(VID:PID `cafe:4001`), both retaining the descriptor `PLASMA Blue Pill CDC v0.1`.
These descriptors do not prove running firmware identity or physical Site association.
No CDC port was opened, and no reset/resume/power cycle was added. Current Site2
firmware ID **NOT_VERIFIED**, heartbeat **NOT_RUN**. This optional observation
does not change physical Flash/readback PASS.

No Site1 operation, deployment, service restart, FPGA install/load, activation,
permit bypass, recovery or merge occurred. PR #1436 remains Draft. No remaining
blocker to the requested one-Flash acceptance; this is not production qualification
or power-control verification. Gate 2 remains ungranted.

Nonsecret machine-readable evidence: [result.json](result.json). Complete private
SWPC responses, request ledger and native receipts remain under the run-specific
engineering evidence directory. Source report changes are left uncommitted for
the existing trusted post-Codex publisher, which verifies the pinned PR HEAD.
