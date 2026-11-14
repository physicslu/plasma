# Issue #1424 — Site-independent Programming Profile and PPU-owned Site discovery

Status: Gate 1 implementation / Host-only verification in progress. Do not claim real Site 1, concurrent Site, electrical Power Control, or DUT HIL PASS from this document. Owner Gate 2 is required to merge PR #1425.

## First principle and change

The IC/ICPN identifies a device and its qualified programming algorithm; a **Site is a physical PPU endpoint**. Their identities are distinct. Site topology, interface binding, enablement, readiness and physical capability belong to the PPU. A Programming Profile declares IC, operations, driver ABI, transport/geometry requirements, **not an integer whitelist of Site IDs**. Console selects the Site from the PPU's current Fleet observation. Admission recomputes the selected IC/operation Profile and checks current PPU Site state. An issued Job still binds exact PPU, Site, ICPN, Profile, Resource Set, Image and range.

The PPU's `site_count` and maximum 8-Site ceiling do **not** prove which PL Sites are physically instantiated/qualified. The active Worker/ABI must prove real Site support before programming. Disabled/busy/faulted Sites stay unavailable for execution without forcing an unrelated ICPN/Profile restriction.

## File-level inventory: REMOVE / REPLACE / RETAIN

| Classification | Layer / files | Outcome and reason |
| --- | --- | --- |
| REPLACE | `software/python/plasma_opf/bundle_v3.py` `ProgrammingRoute.sites`, `parse_route`, `resolve_routes` | Match ICPN + supported operations only; remove static `sites[]` from Profile capability |
| REPLACE | `software/python/plasma_opf/bundle_v3.py` Resource Set, `job_image_binding` | Resource Set v2 excludes `constraints.sites`; each binding keeps positive integer `site_id` and PPU confirms actual Site validity |
| REPLACE | `data/opf/programming-routes/*.json` | Existing IC/operation Profiles no longer declare physical Site whitelists; no per-Site clones |
| REPLACE | `software/python/plasma_manager/programming.py` | `resolve_routes` independent of Site; `_readiness` no longer rejects a different job ICPN based on a persistent Site target |
| REPLACE | `scripts/ppu_provider_contract.py` | Provider descriptor no longer declares `sites[]`; selection still requires independent trusted hardware-observed `sites`, ABI, FPGA identity |
| REPLACE | `scripts/opf_platform_bundle_v3_build.py`, `scripts/plasma_program.py`, `scripts/ppu_opf_reference_openocd.py`, `scripts/plasma_site2_active_readonly_path2.py` | Align Provider Capability v2; stop using descriptor Site allowlist; keep actual hardware/site guard |
| REPLACE | `software/python/plasma_server/site_manager.py`, `software/python/plasma_server/server.py` | Reject non-Mock Job lacking explicit target; derive Site status target only from active Job; keep per-Job Resource and Binding validation |
| REPLACE | `software/python/plasma_web/site_configuration.py`, `software/python/plasma_web/gateway_phase2.py` | Writable Site Desired = `enabled/interface` only; deterministic revision and reconciliation exclude persistent ICPN; legacy Site target retired on a Site Desired write |
| REPLACE | `software/web/app/programming/managed-programming.ts`, `software/web/app/engineering/managed-programming-workspace.tsx`, `software/web/app/engineering/bundle-programming.tsx`, `software/web/app/engineering/bundle-programming-api.ts` | Derive selectable Site IDs from observed PPU topology/status and match IC Profile operations separately; no `route.sites` |
| REPLACE | `software/web/app/engineering/ppu-registry-api.ts`, `software/web/app/engineering/ppu-site-desired-configuration-core.tsx` | Remove editable Site Desired ICPN; IC is a programming Job input |
| RETAIN / LEGACY | `software/python/plasma_core/config.py` `SiteConfig.target` | Kept parseable for existing PPU YAML and Mock simulation fixtures, but not a real-hardware Job default; not an allowlist |
| RETAIN | `software/python/plasma_server/mock_resources.py` | Mock simulates one shared target/geometry as test-only PPU Active Set; its Profile no longer restricts Sites |
| RETAIN | `scripts/ppu_site_worker.py`, `scripts/ppu_asset_execution.py`, `software/python/plasma_interfaces/*`, FPGA/AXI/ABI verification | Physical Worker sessions and loaded FPGA capabilities bind actual one-based Site, with lease ownership and ABI checks |
| RETAIN | `software/python/plasma_server/site_manager.py` `_admit_job_binding`, `software/python/plasma_manager/programming.py` `_submit_once` | Exact Job PPU + Site + ICPN + Profile + Asset + range, immutable receipt, no blind OUTCOME_UNKNOWN resubmission |
| RETAIN | `software/python/plasma_core/config.py` `enabled/interface` | Administrative/maintenance Site configuration separate from one-time Job selection; currently requires controlled Runtime Activation rather than hot reload |
| RETAIN | `data/device-catalog/**` and Research ICPN applicability | Upstream informational Catalog/qualification, NOT a PPU Runtime execution allowlist after OPF S5 |
| RETAIN | `docs/evidence/**` | Historic evidence immutable; never rewrite old Site2 HIL snapshots to imply Site1 PASS |
| REPLACE | `software/python/tests/**`, `software/web/tests/**`, `software/web/e2e/**`, current architecture / operator docs | Update source-backed assertions and add Site1/Site2 positive, wrong Site binding negative, stale schema negative, disabled/faulted incompatible Site negative cases |

## Call graph — canonical route

```text
PPU FPGA/Runtime Site presence and state
   → PPU Gateway GET /api/status
   → Manager Registry/Fleet observation
   → Console Site selection (1..N observed Sites, real interface and readiness)
Operator picks exact ICPN + Image + operations + Site(s)
   → Manager canonical programming start / Batch
   → BundleProgrammingWorkflow.plan
      → bundle_v3.resolve_routes(icpn, operations) [NO static Site list]
      → Resource Set v2 from Provider Capability v2 + Flash Profile
      → PPU Gateway GET /api/status?site=N [actual Site]
      → Manager Job Image Binding SHA256 (ppu_id, site_id, icpn, resource, image, range)
   → existing Resource reuse / B1-B2-B3 only when necessary
   → PPU SiteManager._admit_job_binding
      → rederive Resource Set from verified PPU Active Bundle
      → verify Job Binding SHA256 and real Site lease/interface / target
   → C-3 Site Worker / PS OpenOCD / FPGA Site N
   → Job evidence and per-Site Receipt
```

## Compatibility / migration

- Provider Capability v1 and Resource Set v1 are **retired**: v2 is not wire-compatible with the old Profile bytes or hashes. This is deliberate Replace-by-Default; no silent migration, loose fallback or synthetic reuse of an old Resource Set.
- Bundle container stays canonical v3; the inner Provider/Profile descriptor and computed Resource Set change. A first Job after upgrading code may require a controlled B1/B2/B3 Resource activation, preserving PPU identity and existing Rollback/Recovery guards.
- The existing `site2` words in historical route filenames and Profile package IDs are labels, **not a Site allowlist**; renaming them would further change package identity. They should be renamed in a separate versioned cleanup only with all consumers accounted for; they must not gate selecting Site 1.
- Site Desired API no longer edits target ICPN. A legacy YAML `target` field remains parseable to avoid breaking an existing PPU startup; saving the affected Site Desired removes it. Do not silently rewrite unrelated Sites on upgrade.

## Acceptance evidence needed before Gate 2

- Python/TypeScript build, focused and regression tests, GitHub-hosted CI, positive Site1/Site2 and negative cases, current PR HEAD verified.
- PPU Status for each actually enabled Site; dynamic programming readiness; no newly invented Site or interface capabilities.
- Actual Site1 hardware HIL and Site2 regression remain separate field evidence: mark NOT_RUN when not performed; no claim that Host-only CI = DUT PASS.
- The validated OpenOCD Flash Profile now exposes `site_interface=openocd` in the Route summary. Manager checks that requirement before Resource activation and before Job submission; Console applies the same per-Profile interface compatibility to PPU-observed Sites. An unqualified direct `fpga` interface remains blocked for this OpenOCD Profile, without hardcoding a physical Site number. Future Provider/Profile families require their own validated interface mapping.
- Host-only regressions exercise switching already-ready Site 1→2 with one Active Resource Set despite a stale legacy Site target; wrong execution interface is rejected before B1/B2/B3 and Job submission.
- EMode/PMode Playwright fixtures no longer invent a `sites[]` Profile whitelist. Mock Fleet can vary interfaces per Site; disabled/busy/incompatible (e.g. direct FPGA versus qualified OpenOCD) are distinct refusal reasons. Idle Site status has no persistent ICPN.
- Current OPF Gate 1, PPU Site Desired persistence and Resource/Job Binding architecture docs were synchronized: Provider Capability v2, no `sites[]` whitelist or `target` Desired field, and independent PPU Site admission. Historical evidence records are unchanged.
