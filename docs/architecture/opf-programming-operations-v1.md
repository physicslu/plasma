# OPF Programming Operations v1 — one Job, an ordered `operations` list

Status: implemented Host-only (Gate 1, 2026-11-11). **No hardware qualification yet**: every
statement below about Z2 / Site 2 is a contract, not evidence. See "Qualification" at the end.

## Model

| Job kind (`operation`) | Selector on the wire | What runs | Receipt |
| --- | --- | --- | --- |
| `programming` | `operations: [...]` (never an `operation`) | the ordered list, in ONE Job | per-step evidence |
| `read` | `operation: "read"` + `address` / `length` | one independent read | bytes + SHA256 + binary |
| `flash_cycle` | `operation: "flash_cycle"` | legacy complete cycle | unchanged |

* The basic operations are `erase`, `program`, `verify`. The order is always
  **erase → program → verify**; only the listed ones run.
* Every legal selection is the **same** Job kind: one Job ID, one PPU execution lease, one C-3
  Site session, one OpenOCD run, one Job Binding and one final receipt. `erase + program +
  verify` is `operations: ["erase","program","verify"]`; it is **not** mapped to `flash_cycle`
  and has no special branch.
* A single `erase` / `program` / `verify` is never a Job of its own (the PPU and the Manager
  refuse `operation: "erase"` etc.); send `operations: ["erase"]`.
* `flash_cycle` is a **legacy contract**. Its code path, wire format, Job Binding identity and
  committed Route (`z2-site2-stm32f103c8t6`, Resource Set unchanged) are untouched and stay
  available until the new model has passed Host-only and Site 2 HIL acceptance.
* `read` is not part of a list and not part of a Batch.

### Legal lists

`[erase]`, `[program]`, `[verify]`, `[erase, program]`, `[program, verify]`,
`[erase, program, verify]`.

Refused everywhere (UI, Manager plan `422 operations_invalid`, Job Binding, PPU, Worker):

* `[erase, verify]` — Verify compares the IC with the Programming Image; an IC that was only
  erased can never equal it, and a successful erase must not be reported as an Image verify.
  Erase alone already proves the erased range blank.
* an empty list, a repeated or mis-ordered entry, `read` / `flash_cycle` inside a list.

### Step semantics (C-3 OpenOCD reference Provider)

Common preamble and ending are the ones qualified for `flash_cycle`
(`reset halt` → `poll off` → `flash probe 0` … `reset run` → `shutdown`).

| Step | Action | Never does |
| --- | --- | --- |
| `erase` | `flash erase_address` over the Image's erase window (Image size rounded up to erase units); erase-only: the explicit Job range, then a full readback that must be all `0xFF` | program |
| `program` | `flash write_image` of the bound Image at the Job address, without the `erase` keyword | erase (programming a non-erased NOR cell fails in OpenOCD and is a FAIL) |
| `verify` | `dump_image` of the Image range, byte compare with the bound Image | erase, write |
| `read` (own Job) | `dump_image` of the bound range | erase, write |

## Identity

* A Route Profile declares the **basic** operations it supports (`erase`, `program`, `verify`,
  `read`, legacy `flash_cycle`); it never declares `programming`. Every operation of a Job must
  be declared by one Route (Manager) and by the Active Profile descriptor (PPU).
* The Manager picks the Route whose Profile declares every operation of the Job. The committed
  `z2-site2-stm32f103c8t6-operations` Route declares `erase, program, verify, read`; the legacy
  Route keeps declaring only `flash_cycle`. They are different Resource Sets: switching between
  them is a normal B1/B2/B3 activation (`fpga_load=false`) with an Image.
* Job Binding (`plasma.opf.job-image-binding.v1`): a `programming` Binding has
  `operation: "programming"` plus `operations: [...]`; the list is part of the Binding SHA256.
  A `flash_cycle` / `read` Binding has no `operations` field (legacy identity is byte-identical).
* Range: a list with `program` or `verify` requires the Image Asset and acts on exactly its
  range; an erase-only list and `read` take an explicit range and no Image. Erase ranges are
  whole erase units; every range must lie inside the Profile Flash bank. There is no MMIO or
  unbounded read.

## Layers

1. **Manager plan** (`POST …/programming/plans`): exactly one of `operations` or `operation`
   (`read`, `flash_cycle`). Unchanged: Registry, pairing, Recovery, Resource Reuse / B1–B3,
   plan TTL, one plan → one run, OUTCOME_UNKNOWN latch, `auto_retry = DISABLED`.
2. **PPU Gateway** `/api/jobs`: `operations` (+ `job_binding`) → `Operation.PROGRAMMING`.
3. **SiteManager**: re-derives the Resource Set, re-validates the list and verifies the exact
   Binding under the Job lease; `max_retries` must be 0.
4. **Execution router / OpenOCD interface**: `programming` and `read` run only under an
   admitted Binding; a separate erase / program / verify Job is `OPERATION_UNSUPPORTED`.
5. **OPF reference executor**: Active Set, Profile descriptor (every operation declared),
   engine and FPGA identity as for `flash_cycle`; the ordered list is pinned in the Provider
   route of the C-3 session.
6. **C-3 Site Worker** (`plasma.ppu.site-worker.v3`, additive): operation `programming` with
   the route's `operations`; `bind_image` when the list programs or verifies, `bind_range` for
   erase-only and `read`. One operation guard, one Site lock, SAFE_OFF, FPGA identity checks.
7. **ABI-v5 adapter**: one admitted OpenOCD session; evidence per step from what actually ran.

## Receipts and failure classes

* PPU Job result: `details.programming = {result, operations, steps: {erase, program, verify},
  safe_off, job_binding_sha256, …}`; `details.read = {read_address, read_length, bytes_read,
  sha256, safe_off, …}` and the bytes as the Job output file.
* Manager receipt `plasma.manager.programming-receipt.v3`: `operations`,
  `observed_operations`, `expected_steps` / `observed_steps`, `range`, `read_output`. PASS needs
  SAFE_OFF, the echoed Binding (including the list), one attempt, exactly the planned list
  (nothing skipped, nothing added) and matching evidence for every step.
* A PASS whose erase / program evidence is not the bound range seals the Site
  (`OUTCOME_UNKNOWN`). An unproven verify-only or read result is a safe failure (no write
  happened). A failing OpenOCD step with verified SAFE_OFF is a definite FAIL.
* Read Memory: the Manager fetches the Job output file through the PPU Gateway, checks length
  and SHA256 against the PPU evidence, retains it next to the run journal and serves it at
  `GET …/programming/runs/<run_id>/output` (re-hashed before every download). The Console
  downloads through the same-origin BFF only and re-hashes the bytes against the receipt.

## Qualification

Host-only tests use a fake root admission and a Flash simulator in place of OpenOCD. They prove
the contract, the argv and the evidence logic. They do **not** prove that the OpenOCD command
sequences above work on a real STM32F103 through `plasma_swd`. Until Site 2 HIL passes:

* `programming` (every list) and `read`: **NOT hardware qualified**;
* `flash_cycle`: existing qualification unchanged.

Nothing here is deployed by merging. The operations Route is used only after its Resources are
activated on a PPU by an explicit programming run.
