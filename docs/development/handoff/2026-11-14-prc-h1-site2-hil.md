# PR-C H1 — Site 2 HIL acceptance (real Z2, real Blue Pill)

2026-11-14. Owner-authorised: deploy PR-C to the SWPC Control Station, one E+P+V flash on
Site 2, and the Resource Set activation it requires. Two cycles were run; both **PASS**.

Raw evidence (not in the repository): `/storage/projects/plasma-evidence/prc-h1-site2-20261114/`
— `SUMMARY.md` plus the request, admission, poll, receipt, reconciliation and snapshot JSON of
every step.

## What was under test

| | |
| --- | --- |
| Control Station | `3d6f3c6b2ff4` (#1409) → **`60ed373561c3`** (this PR; unmerged at run time) |
| Z2 Runtime | `6323ad90ae34` — **unchanged**. No FPGA load, no Z2 restart, no Runtime deploy. |
| PPU / device | `z2-hil` / `ppu-device-7ed4b30913a9bf6101da5a7a`, paired, commissioned |
| Site | 2 (openocd, `plasma_swd:5`, STM32F103C8T6 Blue Pill) |

Deploying this PR to the Control Station also carried the eight PRs merged to `main` since
#1409 — among them PR-B (#1416, the Batch engine), PR-B1 (#1412) and C-3's derived SAFE_OFF
receipt (#1414). A failure here would not have been PR-C's alone.

## Both Resource paths were exercised

| Cycle | Image | Resource path | Active Set |
| --- | --- | --- | --- |
| H1 | `plasma-blue-pill-cdc.bin`, 18768 B, `8d3ffb02…d841d` | `activation_required true`, `reuse false` → B1/B2/B3 | gen 19 `stm32f103c8t6-site2` `["flash_cycle"]` `39e4bf85…` → **gen 20 `stm32f103c8t6-site2-operations`** `f844b260…` |
| H1-R | `plasma-blue-pill-cdc-v0.2.bin`, 62800 B, `e691ab23…682c` | `activation_required false`, **`reuse true`** | gen 20 **unchanged** — the reuse path really skipped activation |

The DUT held `e691ab23…` before H1, so H1's readback of `8d3ffb02…` proves a real write rather
than an unchanged part; H1-R restored `e691ab23…`, again proven by readback.

## Results

| Check | H1 | H1-R |
| --- | --- | --- |
| canonical start issue, `ppu_alias: null` | `8240061ad024…` | `ecff6e3e3636…` |
| Batch admission (202), `targets [{z2,[2]}]` | `66ba472f0294…` | `f04cdcb5e778…` |
| Job | `job-20261114-083113-d778d34b` | `job-20261114-083507-2c474551` |
| one submission, no retry | `job_submission_count 1`, `auto_retry DISABLED`, 1 attempt | same |
| job binding expected == observed | `94b4af14…755c` | `def21066…4d7a` |
| resource set expected == observed | `f844b260…e5a50` | `f844b260…e5a50` |
| readback == expected image | `8d3ffb02…d841d` | `e691ab23…682c` |
| `safe_off` | true | true |
| `observed_operations` | `["erase","program","verify"]` | same |
| per-Site unit | PASS, `job_key {batch, z2, 2, 1}`, `counts {pass 1, sites 1}` | same |
| reconciliation by `start_id` | `TERMINAL_CONFIRMED` / PASS, two reads byte-identical | `TERMINAL_CONFIRMED` / PASS |
| replay of a consumed start | 409 `programming_start_not_startable` | same |
| void of an admitted start | 409 `programming_start_not_voidable` | same |

**Retired routes.** All six alias-scoped Batch and start routes answered **410
`programming_route_retired`** on the Manager, and **404 (not allowlisted)** through the Console
BFF, so the browser cannot reach them at all. The PPU-scoped `programming/routes` still answers
200 — PR-C does not touch what a PPU owns.

**Journals.** The live journal was schema v1 with 14 Batches. After the upgrade it stayed
**byte-identical**, and the v2 sibling was created holding only the two H1 Batches — no legacy
Batch was copied forward. The canonical start record on disk reads `start_scope: "manager"`,
`ppu_alias: ""`, `targets: [{"ppu_alias": "z2", "site_ids": [2]}]`: the empty alias is the
rollback placeholder and `start_scope` is what identifies the start, exactly as §5.8 states.

## NOT proven here

* **Multi-Site is NOT_RUN.** This PPU has one real Site: Site 1 is `interface: mock` and
  disabled, and `counts.sites` was 1 in both cycles. Per-Site admission isolation (the Platform /
  Target gate split), failure-domain isolation, the stop policy across Sites and PPU latching
  therefore have **no hardware evidence**. H1 does not stand in for H2.
* **The BFF per-Target capability check did not execute.** This Control Station runs
  `PLASMA_MANAGER_REGISTRY_POLICY=mutable`, under which that gate is a no-op. Its evidence stays
  host-only and contract-level.
* **The reset sequence is not in the receipt.** `observed_steps` records erase, program and
  verify. That the Site adapter brackets them with `reset halt … reset run` is read from the
  deployed Runtime's `scripts/ppu_site_adapter_abi5.py`, not observed in this run's evidence.
  Confirming it would need the Z2's OpenOCD log.

## Deployment state after the run

The Control Station runs `60ed373561c3`; the previous release `3d6f3c6b2ff4` is kept, and
rollback is re-running `plasmactl-local-control-station deploy` from it. Site 2's Active Resource
Set stays on the operations profile (gen 20); running the legacy `flash_cycle` path again would
require re-activating that Bundle, which is its own device write.
