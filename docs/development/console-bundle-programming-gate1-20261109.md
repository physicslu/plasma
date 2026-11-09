# Console-driven Bundle Programming — Gate 1 (2026-11-09)

**Status:** Owner-approved Gate 1. P0 audit, P1 minimal implementation and P2
Host-only acceptance are in a Draft PR. **Not merged, not deployed. No real
B2/B3/Job/Flash.** Host-only PASS is **not** physical E2E evidence.

**Base:** `main` `5f97cad0b5cd2b3d6286331ed8c14b7a3f33223e`.
**Normative inputs:**
- [Unified Bundle-driven Programming Decision](../architecture/unified-bundle-driven-programming-decision-2026-11-04.md)
- [Canonical Bundle Packages](../architecture/ppu-canonical-bundle-packages.md)
- [Bundle v3 B3 Path 2](../deployment/ppu-bundle-v3-b3-path2.md)
- [Owner Operation Authorization](../deployment/ppu-owner-operation-authorization.md)
- [`plasma_program` CLI](../deployment/plasma-program-cli.md)

## Product requirement

A Console user selects IC, firmware file, PPU and Site, then presses **Start**.
Console/Manager then perform route resolution, Bundle v3 construction, Bundle
deployment/activation (only when needed), one `flash_cycle` Job, and result
verification. The user never hand-builds a Bundle and never needs an
engineering CLI.

## P0 — Gap audit (read-only)

### Inventory at the base commit

| Area | Existing implementation | Usable as-is? |
| --- | --- | --- |
| Console B1/B2/B3 | `ppu-runtime-deployment.tsx` → BFF → Manager `ManagerBootstrapCoordinator` (upload chunks, `bundle.admit`, B3 `mode`/`fpga_load`, owner authorization) | Yes. The user must still supply a ready-made Bundle file. |
| Bundle builders | `scripts/bluepill_bundle_v3_firmware_build.py` pins two fixture firmware digests. `scripts/opf_platform_bundle_v3_build.py` builds a profile-only Bundle from a source directory. | No. Neither accepts arbitrary user firmware, and neither ships with the Manager runtime. |
| Bundle verifier | `scripts/ppu_unified_deployment.verify_host_only_bundle` | Host/PPU side only. The PPU re-verifies at B2/B3. |
| Active Set | Bootstrap `GET /v1/assets` (`plasma.ppu.active-assets.v1`) | The Manager client had no read method for it. |
| `flash_cycle` | Gateway `POST /api/jobs` with `asset_set_sha256`, `asset_package_id` and `bundle_asset_sha256`; result read via `/api/status?job=` | The Manager allowlist already permits `POST /api/jobs`, but the Console UI has no `flash_cycle` path. Its Job UI covers only erase/program/verify/read with uploaded bytes. |
| End-to-end orchestration | `scripts/plasma_program.py` (CLI only): direct Bootstrap + Gateway, no Manager | Not usable from the Console. |
| Programming data | Provider and Profile JSON hard-coded inside the fixture builder | No data source a product could reuse. |

### Gaps: user selection → Bundle v3

1. **No Programming Route data.** Nothing maps IC + PPU platform + Site to
   Provider options, capabilities and flash profile, except constants inside a
   fixture script.
2. **No product Bundle writer.** No single canonical writer exists that is
   importable by the Manager runtime.
3. **No server-side composition.** Nothing chains route → Bundle → Active Set
   comparison → B1/B2/B3 → one `flash_cycle` → receipt behind the Manager.
4. **No Active Set read through the Manager.**
5. **No Console UI.** Nothing offers IC, firmware, PPU and Site selection with
   explicit confirmation, progress and receipt.
6. **IC picker hides L1 ICs.** The picker only requests Catalog Levels L2/L3,
   which conflicts with "Catalog Level is not an execution gate".

### Reuse versus new code

- **Reused unchanged:**
  - `ManagerBootstrapCoordinator`: B1 upload, B2/B3 and owner authorization issuance;
  - `PPUOperationGate`: platform-launch versus managed-write serialization;
  - `_bootstrap_mutation_allowed`: idle, recovery and trusted observation;
  - the PPU Gateway `/api/jobs` and `/api/status` contract;
  - PPU-side verification, leases, SAFE_OFF and SEALED;
  - the BFF maintenance-capability boundary.
- **Deduplicated:** a single canonical writer `plasma_opf.bundle_v3`. The fixture
  builder now delegates to it and still reproduces Bundle A
  `71e9a044…` byte-for-byte.
- **Not added:**
  - no second Bundle Builder;
  - no Deployment Coordinator (the PPU Bootstrap coordinator stays the only
    install/activation authority);
  - no Execution Router (the PPU Runtime stays the only Job router).

### Data and authorization boundary

| Concern | Browser | Console BFF | Manager | PPU |
| --- | --- | --- | --- | --- |
| Firmware bytes | Reads the file. Sends base64 once, to plan. | Size-limited relay (2 MiB) | Builds the Bundle in memory; never journaled | Receives the Bundle at B1 only |
| Bundle bytes and digest | Displays the digest only | — | Builds and holds the plan (30 min TTL) | Verifies at B2 and B3 |
| Owner authorization | Never | Never | Issues `bundle.admit` and `bundle.activate` from the paired credential | Verifies |
| Permission | Explicit confirmation checkbox | Maintenance capability cookie required for POST | Commissioned lifecycle, paired device, idle and no-recovery gate | Lease, Site ownership, ABI and target |
| Hardware operation | Never | Never | Never directly; one Job request | Executes, SAFE_OFF, SEAL |

## P1 — Minimal implementation

- **`data/opf/programming-routes/*.json`** (`plasma.opf.programming-route.v1`):
  - one committed first-party route, `z2-site2-stm32f103c8t6`;
  - its bytes are the same as the Bundle A/B Provider and Profile Packages;
  - routes are Bundle *inputs*, not a PPU execution gate or ICPN registry.
- **`software/python/plasma_opf/bundle_v3.py`**:
  - route validation;
  - deterministic canonical ZIP (STORED, 1980 timestamp, sorted, mode 0644);
  - Provider → Profile → Firmware Bundle;
  - user firmware identities derived from the firmware SHA256;
  - limits enforced: size, flash size, filename.
- **`software/python/plasma_manager/programming.py`** (`BundleProgrammingWorkflow`):
  - `plan`:
    - requires commissioned lifecycle and a paired device with Runtime active;
    - resolves exactly one route, so 0 or more than 1 match fails;
    - builds the Bundle and reads the Active Set;
    - returns the digest and whether activation is required.
  - `start`:
    - requires `confirm: "PROGRAM"`;
    - one plan can start at most one run;
    - only one active run per PPU;
    - refused while an unacknowledged OUTCOME_UNKNOWN exists for that PPU.
  - Execution sequence:
    1. preflight: Site idle;
    2. only if the Active Set differs: B1, B2, B3 `activate` with `fpga_load=false`;
    3. Active Set must now equal the Bundle;
    4. Site target must come from the Active Set;
    5. exactly one `flash_cycle` submission;
    6. observe the Job;
    7. verify `safe_off`, job/result state, image identity, `attempts==1`,
       `flash_cycle=PASS`, readback SHA256 and verified bytes.
  - Failure classes:
    - B1 or B2 errors are a definitive FAIL; nothing was activated.
    - Any uncertainty after B3 or Job submission is `OUTCOME_UNKNOWN`. It is
      never retried and latches the PPU until an explicit `acknowledge`.
    - A Manager restart during a run becomes `OUTCOME_UNKNOWN`
      (`MANAGER_RESTARTED_DURING_RUN`), because the journal is durable beside
      the registry.
  - SEALED is never cleared; FPGA is never loaded.
- **Manager routes** (under the existing Bootstrap prefix):
  - `GET  /api/registry/{alias}/bootstrap/programming/routes`
  - `POST /api/registry/{alias}/bootstrap/programming/plans`
  - `POST /api/registry/{alias}/bootstrap/programming/runs` (gated by `_bootstrap_mutation_allowed`)
  - `GET  /api/registry/{alias}/bootstrap/programming/runs/{run_id}`
  - `POST /api/registry/{alias}/bootstrap/programming/runs/{run_id}/acknowledge`
- **Manager client:** `BootstrapHttpClient.assets` and
  `ManagerBootstrapCoordinator.assets`, a read-only, validated Active Set read.
- **Console BFF:** allowlists exactly the routes above. POSTs keep the existing
  maintenance capability requirement.
- **Console UI** (`engineering/bundle-programming.tsx`, on the PPU → Platform
  page for commissioned PPUs):
  - IC picker (L1–L3), firmware file, Site options taken from routes;
  - **Prepare Bundle**, which shows the plan;
  - confirmation checkbox, then **Start Programming** (single-shot);
  - live steps and Job progress;
  - receipt: readback SHA256, verified bytes, SAFE_OFF;
  - an OUTCOME_UNKNOWN banner with an explicit acknowledge.
- **Packaging:**
  - The Control Station runtime Manager zipapp now ships `plasma_opf` and the
    committed routes. Its packaging validator requires
    `plasma_manager/programming.py` and `plasma_opf/bundle_v3.py`.
  - The `local-control-station` release already exports `data/`.

## P2 — Host-only acceptance

| Layer | Evidence |
| --- | --- |
| Shared writer | Golden: route + v0.1 firmware → `71e9a044…` (historical Bundle A). The user Bundle passes `verify_host_only_bundle`. |
| Manager workflow (fake Bootstrap + fake Gateway/Provider) | `tests/test_bundle_programming_workflow.py`: success with activation; already active (no B1–B3); route not found; Site not declared; firmware too large; plan missing or consumed; duplicate plan; run already in progress; confirmation required; Job POST timeout → OUTCOME_UNKNOWN, latched, no retry, unlock only after acknowledge; B3 submission unknown; B3 status timeout; B3 failed; SAFE_OFF failure; readback mismatch; PPU rejects Job; busy Site blocks before any write; unpaired, not-commissioned and unknown-alias permission denials; Manager restart mid-run; route root missing |
| Manager HTTP | `tests/test_manager_bundle_programming_rest.py`: routing and status codes; run gated by the platform idle check; unlisted paths return 404 |
| Console BFF and source contract | `tests/bundle-programming-contract.test.mjs` |
| Real Console UI (Playwright, Manager mocked at the Browser boundary) | `e2e/tests/bundle-programming.spec.ts`: user flow IC → firmware → PPU/Site → Bundle → B1/B2/B3 → `flash_cycle` → receipt, with a double click still starting once; already active; incompatible; Bundle missing; permission denied; OUTCOME_UNKNOWN with no resubmit and explicit acknowledge; SAFE_OFF failure; Manager HTTP failure while polling |

## Known limits / follow-ups (not in this PR)

- **Only one first-party route.** Third-party or user-supplied route Packages, a
  signed route source, and multi-Site and FPGA-bearing routes are later work.
- **Manager-side compatibility is declaration-level only.** The Manager checks
  the route's declared Sites and size. The actual board, FPGA part, Driver ABI
  and target are verified by the PPU at B2/B3/Job, as the Decision §3 requires.
- **The plan cache is in memory.** A Manager restart drops prepared plans; the
  user prepares again. Runs are journaled.
- **macOS/Windows packaged runtimes** include the routes and writer through the
  zipapp trace. Live acceptance on those platforms is NOT_RUN.
- **No physical evidence.** A real SWPC deployment and a single Z2 Site 2
  attempt each need separate owner authorization.

## Gate 2 / next authorizations required

1. Review and merge this PR.
2. Deploy the SWPC `local-control-station` from the merged SHA.
3. One owner-approved Console run on Z2 Site 2. The expected Bundle digest is
   shown before Start. The flow is B1/B2/B3 only if the Active Set differs,
   then exactly one `flash_cycle`. On OUTCOME_UNKNOWN: no retry; reconcile.
