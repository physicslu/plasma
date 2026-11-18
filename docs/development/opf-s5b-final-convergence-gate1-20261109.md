# OPF S5-B — Final architecture convergence (Gate 1)

**Baseline:** `main@963042f4060dad97c767b3d79d182b7862d82458` (PR-C2 #1362 merged; S5-A #1363 merged).
**Scope:** delete the PPU Gateway compatibility Device Selector after consumer migration; reconfirm OPF/PPU/Manager invariants. Host-only; **HIL: NOT_RUN**.
**Reference:** [S0–S5 roadmap](../architecture/plasma-core-convergence-and-deletion-first-roadmap.md), [S5-A record](opf-s5a-source-convergence-gate1-20261108.md).

## P0 — Consumer audit of PPU `GET /api/devices/search`

| Consumer | State at baseline | Disposition |
| --- | --- | --- |
| Console `searchDevices` (`software/web/app/device-catalog-api.ts`) | `DEVICE_SELECTOR_PATH = /api/manager/devices/search` (PR-C2) | Manager; no change |
| Console BFF (`software/web/app/api/manager/manager-bff.ts`) | relays to **Manager** `/api/devices/search` | Manager; no change |
| Manager managed-PPU relay allow-list | Selector removed (PR-C2) | no change |
| PPU programming ingresses (`plasmactl-*-managed-ingress`) | `/api/devices/search` excluded (PR-C2) | comment updated |
| Render (`scripts/render-start.sh`, public smoke) | probes the **Manager** port / `/api/manager/devices/search` | no change |
| Packaged PPU (`ppu.pyz`) | Selector module excluded (`CATALOG_ONLY_MODULES`) ⇒ 503 | route deleted ⇒ 404 |
| Host tests (21 Catalog projection tests) | spun up `PlasmaWebHandler` only to query the Selector | retargeted to the real `PlasmaManagerHandler` |

No production or operator consumer of the PPU route remained.

## Deleted / retained

**Deleted (production):**

- `plasma_web/gateway.py`: `LEGACY_DEVICE_SELECTOR_MODULE`, `DeviceSelectorUnavailable`, `_legacy_device_selector`, `PlasmaWebHandler._is_device_search_path` / `_device_selector_unavailable` / `_device_search`, the `do_GET` branch, `warm_legacy_device_selector` and its call in `serve`, and the now-unused `import importlib`.
- `plasma_web/secure_gateway.py`: the `CATALOG_READ` authorization rule for `/api/devices/search`. The path now falls through to `_deny_unclassified_api_route` (fail-closed `AUTHORIZATION_DENIED`).

**No files deleted.** **Retained, with reasons:**

- `plasma_web/legacy_device_selector.py`: the Manager's only Selector projection (`search_response`, `warm`). It ships in `manager.pyz` and stays excluded from `ppu.pyz`. Renaming it is cosmetic and out of scope.
- `Permission.CATALOG_READ`: still guards `/api/engineering/targets`.
- `CATALOG_ONLY_MODULES` in `scripts/ppu-runtime.py`: still the packaging exclusion list.
- Every safety owner: Bundle v3, Active Set, Site Lease, Resource Lock, FPGA Ownership, SAFE_OFF, SEALED, Recovery, Outcome Unknown no-resend. None is touched.

Not restored: Catalog Runtime dependency, CompilerRegistry, OpenOCD Plan Compiler/Executor.

## Execution route / import graph

```text
Before (963042f40)                         After (S5-B)
Console ─BFF─> Manager /api/devices/search  Console ─BFF─> Manager /api/devices/search
PPU Gateway /api/devices/search             PPU Gateway: no route (404); Secure: deny
  └─ importlib(legacy_device_selector)?     gateway.py: no importlib, no Selector symbol
     absent ⇒ 503                           Gateway startup: no Selector warm-up probe
PPU Job: Gateway → SiteManager →            PPU Job: unchanged single SiteExecutionRouter
  SiteExecutionRouter {mock, C-3, C-2}        {mock_workflow, openocd C-3, opf_package C-2}
```

The `-I` import probe of every Gateway/Runtime entrypoint, with all `CATALOG_ONLY_MODULES` blocked, now records **zero** Catalog or Selector import attempts. Before this change, startup ran an optional Selector import attempt.

## Quantification

| Metric | Before | After | Δ |
| --- | ---: | ---: | ---: |
| Production Python LOC (`software/python`, excluding tests) | 33,935 | 33,862 | **−73** (+3/−76) |
| `plasma_web/gateway.py` | 897 | 827 | −70 |
| `plasma_web/secure_gateway.py` | 604 | 601 | −3 |
| `ppu.pyz` bytes | 1,054,507 | 1,053,800 | −707 |
| PPU runtime directory bytes | 1,069,469 | 1,068,762 | −707 |
| `ppu.pyz` Python modules / LOC | 112 / 28,535 | 112 / 28,462 | 0 / −73 |
| Runtime dependencies (`pyproject`) | PyYAML | PyYAML | 0 |
| Selector / Catalog modules in `ppu.pyz` | 0 | 0 | 0 |

## Acceptance (Host-only)

- Positive: Manager Selector contract (21 retargeted files, `test_manager_device_selector.py`, managed relay), Bundle v3 Mock flash with the Selector absent, and a packaged `ppu.pyz` Server + Gateway passing Health and loopback.
- Negative: the PPU path returns 404 with no `results` (Selector importable or not); Secure Gateway denies the path with no rule; Catalog faults stay confined to the Manager Selector (503, never an empty result).
- Mutation controls: restoring the base `gateway.py` fails 8 tests; restoring the base `secure_gateway.py` fails 2; a fake-empty 200 route fails 7; disabling the Manager route fails 206.
- Packaging: a non-editable install runs `test_ppu_runtime.py`, `test_ppu_gateway_catalog_free.py` and `test_ppu_armv7_runtime_acceptance.py`; `ppu-runtime.py build` + `validate` pass.
- The PR body records the exact-HEAD GitHub CI results. This document does not presume them.

**CI debt (not addressed, not presumed PASS):** Web validation subtest `not ok 143 — B3 Console control sends the exact admitted Bundle and explicit fpga_load choice through the BFF` fails on `main@963042f40` (run 42498562755) and `main@3d102beae`. That B3 contract is untouched here.

## Not done / remaining

- S2 C-2 / non-OpenOCD physical Provider qualification, S4 portable OPF macOS/ST-LINK, and full 8-Site HIL: **NOT_QUALIFIED / NOT_RUN**.
- No merge, deploy, restart, or SWPC/PPU/Z2/FPGA/DUT operation. This PR adds no physical Flash evidence.
