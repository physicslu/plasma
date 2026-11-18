# PLASMA Catalog Database v1 + Data-only Publication Contract

- **Status:** Gate 1 design contract approved by owner (2026-11-18); Gate 2 is the single PR merge approval. This document is an architectural contract, **not** an implemented or deployed database.
- **Scope:** Canonical Exact ICPN Catalog, IC Selector, evidence, geometry, Provider Qualification and Controller-local overlays. This is a Catalog data-plane change, **not** a change to PPU programming execution, Bundle v3 or FPGA.
- **Normative dependencies:** [ADR-0002](../adr/0002-openocd-software-qualified-catalog-visibility.md), [IC Selector](ic-selector.md), [Unified Bundle-driven Programming](unified-bundle-driven-programming-decision-2026-11-04.md), [OPF Operations](opf-programming-operations-v1.md).
- **Separation requirement:** A Catalog row, an L2 claim, a Job Picker selection and a permitted programming Job are **four different decisions**. None implies the next.

## 1. Architecture boundaries

```text
Manufacturer Research / DFP / Documentary Import / Controller-local editor
                          |
            [Catalog staging + per-record validation]
                          |
             [Immutable published Catalog Revision]
                          |
           Manager CatalogRepository (SQLite v1)
                 |                    |
          IC Selector / Detail    Programming Qualification projection
          (L1/L2/L3)             (evidence + provider/release/profile lock)
                 |                    |
                 +------ Controller / Manager UI -------+
                             selected Bundle v3
                                   |
                       PPU Runtime / Provider / Site
                  (independent installed-asset and safety checks)
```

1. **Manager/Controller owns the Catalog database.** PPU Gateway, Site Worker, FPGA and programming provider must not use an online Catalog query to decide whether an already admitted Job can proceed. Catalog network/database downtime must not invalidate a previously accepted, self-contained and authorized Bundle; PPU still enforces its own immutable asset, Provider, route, lock, voltage, operation and SAFE_OFF gates.
2. **IC Selector remains a shared read-only capability, not an Engineering/Production Mode.** Preserve the existing Manager `GET /api/devices/search` and same-origin `GET /api/manager/devices/search` semantics, stable ranking/pagination and `503 DEVICE_SELECTOR_UNAVAILABLE` when no valid Catalog is available. Research L0 never leaks to customer Selector; customer Selector shows L1–L3; standard Job Picker shows L2/L3. Neither endpoint grants execution rights.
3. **Existing Bundle v3 / OPF execution contract stays canonical.** Controller selects a Provider and Programming Profile and resolves a versioned Bundle; PPU accepts explicit package bytes and its own admission policy. No new PPU Catalog DB, fixed exact-ICPN allowlist, ST-specific public API or live SQL dependency.
4. **Catalog contents do not ship inside product software builds.** An IC identity/qualification update is a data publication, not a Python wheel, FPGA bitstream, PPU image, release bundle or deployment.

## 2. Persistence and logical schema

**Initial storage:** one SQLite database under Manager-owned persistent data root, with foreign keys, transactional revisions, WAL and a tested backup/restore mechanism. SQLite is a deployment decision, **not** the domain model or public API. A future central PostgreSQL Catalog can publish verified revisions to each Controller's SQLite replica without changing Selector or PPU contracts.

Separate logical entities (physical tables may be adjusted after benchmark, but constraints below are binding):

| Logical entity | Core identity | Data and invariant |
|---|---|---|
| `catalog_devices` | `(manufacturer_id, exact_icpn)` UNIQUE | Canonical exact commercial identity, base part, package, grade, normalized fields. Never derive commercial identity from family prefix alone. |
| `evidence_sources` | `source_id + revision` | Authority, document number/revision/URL, acquisition date, per-fact references; raw PDF bytes/hash may honestly be `NOT_ATTESTED`. |
| `evidence_facts` | `fact_id` | Field, value, exact/base/family applicability, source reference, validation status; contradictory sources must fail closed. |
| `memory_geometries` | `geometry_id + revision` | Base/size/start/end/bank/page/erase/write units and applicability; independently versioned and arithmetically validated. |
| `provider_releases` | `provider_id + release_identity` | Version/commit, Driver/Target/algorithm source, operation capabilities; no unverified installed Runtime claim. |
| `programming_profiles` | `profile_id + revision` | Typed configuration and constrained parameters, Provider reference; profile configuration requires schema validation, not a special per-change approval gate. |
| `provider_qualifications` | Exact ICPN + immutable Provider/Profile/Evidence revision | `UNKNOWN/CANDIDATE/BLOCKED/SUPPORTED/UNSUPPORTED`, operation scopes, reason codes, source lineage. Only validated `SUPPORTED` supports L2. |
| `physical_qualifications` | Exact ICPN + configuration/evidence revision | Existing L3 direct-HIL/family-ready authority. Must not be overwritten or downgraded by new L2 rows. |
| `catalog_revisions` | Monotonic revision ID + SHA-256 digest | Immutable published snapshot, source revision parent, schema version, validator version, actor, timestamp, publication outcome. |
| `controller_overlays` | Controller/tenant namespace + Exact ICPN + revision | User-defined/overridden entries and Profiles. Isolated from Open4th canonical authority and other Controllers. |
| `catalog_audit_events` | Event ID | Append-only actor/action/predecessor/result/error/revision audit trail; never silently rewrite published records. |

- Explicit foreign keys and UNIQUE constraints are required for identity, source/geometry/provider references and revision ownership. Stable surrogate IDs are internal; public identity remains `(manufacturer, exact_icpn)`.
- Vendor-specific raw evidence may be retained as JSON for provenance but **cannot create vendor-specific Product tables or endpoints** to bypass canonical admission.
- Geometry/Profile/Qualification changes are **append-only versioned facts** at publication level. No in-place mutation of a published revision; rollback changes the active revision pointer in a new audited transaction, retaining all historical snapshots.
- A resolved Job/Bundle must capture `catalog_revision_id`, `qualification_revision_id`, `profile_revision_id` and Provider/Bundle digests at selection time for audit. Existing Job/Bundle wire contracts are unchanged by Gate 1; any future new receipt fields need independent schema/compatibility review.

## 3. Source authority, levels and customer-owned entries

- Preserve ADR-0002 exactly: L0 = manufacturer Exact ICPN identity; L1 = source-backed programming route; L2 = L1 plus exact-ICPN `SUPPORTED` on a **pinned** Provider; L3 = prior valid physical configuration/family-ready qualification. A Level is the **highest** attained maturity, while an L3 device still satisfies L2-or-higher capability.
- Existing ST baseline is **77 highest-level L3**, which **must remain L3**. When the separate F103 Low-density 12-record qualification is admitted, expected outcome is **12 highest-level L2 + 77 highest-level L3 = 89 L2+**, not 89 L2 and zero L3.
- Official/standard Catalog `SUPPORTED` is derived only from validated documentary Provider evidence for the exact part. Raw manufacturer PDF byte custody is not a universal L2 precondition, but neither a fake digest nor undocumented applicability is allowed.
- Controller-local entries may create Exact ICPN aliases or a customer standard part and select custom Profiles **within that Controller only**. They must be clearly labelled local/unverified relative to official authority; cannot mutate global Catalog, impersonate an Open4th official L2, change another tenant's records or implicitly grant runtime permission.
- A customer-selected Custom Profile/Bundle path may be admitted under the Controller's explicit Engineering/Production policy **separately from the standard official L2/L3 Job Picker**. The underlying PPU operation, safety validation and Provider checks remain identical. No special Engineering-only programming engine.

## 4. Data-only publication: atomic admission pipeline

```text
import / edit / download
  -> staging revision (not public)
  -> schema + source/reference + exact-ICPN uniqueness validation
  -> geometry arithmetic + Provider version and operation applicability
  -> qualification/L0–L3 projection + negative safety invariants
  -> canonical deterministic snapshot hash
  -> BEGIN IMMEDIATE / transactionally seal revision + switch active pointer
  -> COMMIT -> invalidate Manager search cache by revision
  -> audit / observe / optional signed replication to other Controllers
```

**Publication invariants (fail closed):**

1. All changed records resolve valid identities, source/evidence lineage, geometry and Provider/Profile versions. An incomplete new ICPN remains L0/L1 as evidence permits; a `SUPPORTED` claim without exact applicability is rejected, not silently downgraded after publication.
2. Data-only update does not execute a programming command, install a Provider, mutate FPGA, change a security rule or alter PPU active assets. An unknown schema or new unsupported Provider operation is a **code/schema release**, not a data-only change.
3. Never infer L3 from L2. Existing L3/verified evidence must remain intact unless a separately authorized, evidence-backed revocation is issued; a new L2 row cannot downgrade the 77 baseline.
4. Publication is idempotent by revision/content digest. Concurrent writes serialize; readers see either the prior published snapshot or the complete new snapshot. Failed validation/commit leaves the prior revision fully usable.
5. Security: authorized publisher identity, tenant-scoped writes, audit and no untrusted SQL or dynamic evaluation. Snapshots intended for remote import require verified digest and source authority; add signing before supporting cross-organization trust.
6. Search/pagination results are internally consistent for one revision. Cache keys include the active Catalog revision. If a valid last-known-good snapshot exists, a transient upstream sync outage need not disable local search; local integrity corruption fails closed rather than serving partial data.
7. Backup/restore must use a consistent SQLite snapshot (not an unsafe raw copy with active WAL). Recovery validates version, foreign keys, integrity and digest before activating a revision.

**Success of data publication** means validated committed revision and unchanged running software. No GitHub PR or product CI is required for a **data-only** change after the publication engine and schema have been separately qualified.

## 5. CI/CD separation contract

| Change type | Admission/test boundary | Full product CI/CD? |
|---|---|---|
| Add Exact ICPN, documentary evidence or existing-schema Geometry | Transactional row/schema/source/geometry validation | **No** |
| Promote L1→L2 using an existing pinned Provider and supported Profile schema | Exact applicability, version lock, conflict and operation-scope check | **No** |
| Add local Controller ICPN/Profile | Local validation + scoped authorization + audit | **No** |
| Change DB schema, migration, Catalog service or API semantics | Migration forward/rollback, contracts, concurrency, read-path test | Targeted software CI **yes** |
| Change Provider implementation, driver, FPGA, PPU Runtime or unsafe operations | Relevant software/hardware/security integration gates | Product-specific CI **yes** |
| Publish new central revision to Controllers | Digest/authenticity/monotonicity + atomic replica install | Data release only; no PPU rebuild |

- Avoid `reviewed_exact_icpns == 78/90`, `L2 == 77/89` and other global **fixed-count** assertions as general test oracles. Replace with invariant/property tests, an independent recorded reference snapshot for legacy-protection, and explicit before/after data-delta assertions. Fixed numbers may remain in frozen historical fixtures, not in runtime-coupled regression tests.
- GitHub `paths`-filtered workflows can reduce *code PR* CI but cannot solve the architecture problem alone. Once DB data-only publication is implemented, **ordinary Catalog updates must bypass repository software release triggers entirely**.
- CI must still exercise corrupted data, duplicate ICPNs, inconsistent Geometry, mismatched Provider version, unsupported operations, L3 preservation, partial SQLite write/power-loss, rollback, concurrent readers, offline Controller, cross-tenant isolation and authority spoofing.

## 6. Implementation milestones (not approval gates)

**Milestone A — Contract and dependency inventory (PR #1478).**
Freeze boundary and list current seams: `plasma_web/device_catalog.py` (manifest/CSV and process cache), `plasma_web/programming_qualification.py` (provider projections/cache), `catalog_promotion_framework.py`, Manager search and BFF, `data/device-catalog/**`, `data/ic-support/**`, `release/openocd-qualification/**`, `.github/workflows/ic-support-validation.yml`, `.github/workflows/openocd-software-qualification.yml`, Catalog Promotion and cross-repository exact-count tests. Document-only; no runtime behavior change.

**Milestone B — SQLite shadow importer + repository interface.**
Implement `CatalogRepository` abstraction; import current canonical Catalog/Qualification/evidence into a separately versioned SQLite database. Run both legacy and SQLite projections on the same frozen revision, comparing *full exact-ICPN sets, levels, sort/pagination, provider bindings, exclusions and source-lineage hashes*, not just totals. Store remains passive; no UI/Job behavior change.

**Milestone C — Manager read-path switch with rollback.**
Route current Selector API and Qualification projection to the SQLite repository behind a feature flag. Preserve L0 invisibility, L1 not selectable, L2/L3 standard picker, 503 semantics and PPU Catalog-free contract. Verify cold start, offline mode, cache invalidation, concurrency, rollback and equivalence before retiring CSV/JSON runtime readers.

**Milestone D — Data-only revision publisher and Controller overlay.**
Add staging/import, deterministic validators, local edit/create, atomic publish/rollback, audit and namespace isolation. Demonstrate revision publication **without GitHub PR, Python redeploy, PPU image rebuild, or Z2/DUT activity**. Backend code/schema upgrades still use normal targeted CI.

### Milestone D host publisher interface

The Manager-owned SQLite file is selected with `--db`. Initial migration imports the
verified manifest with `--with-qualification`. Subsequent JSON change sets contain
`[{"record": <DeviceCatalogRecord fields>, "qualification": <projection fields>}]`.
The publisher stages against the active digest, checks every exact identity and
source-backed route, then publishes the complete snapshot in one SQLite transaction.
The same database file must be writable only by the trusted Manager/Publisher OS
identity; `--actor` is an audit label, not an authentication secret. Evidence paths
for L2 must be locally available to that identity at both stage and publish time;
the recorded SHA-256 is checked against actual bytes. An L2 evidence file is a
reviewed JSON packet (`schema_version=catalog-l2-reviewed-evidence-v1`) containing
the exact ICPN, exact applicability, source authority/reference, pinned Provider
release/target/driver, Profile/geometry, operation scopes, an `ADMITTED` reviewer
decision, and per-fact document references for identity, route, geometry and
operations. These fields must match the staged row and qualification exactly.
The immutable published revision retains the reviewer and per-fact references
alongside the reviewed packet digest, while removing the host-local file path.
The packet hash attests the reviewed packet bytes, **not** the original PDF bytes;
unavailable original-document custody must not be represented as a PDF digest.
The trusted Publisher OS identity is the admission authority; the reviewer's
name in the packet is an audit claim, not authentication by itself. The Publisher uses only
Provider release/Profile locks already admitted in the active Catalog. A new
Provider implementation, Profile schema or release requires a code/schema change.

```bash
python3 -m plasma_web.catalog_sqlite_repository --db /manager-data/catalog.sqlite3 --stage-file changes.json --actor catalog-owner
python3 -m plasma_web.catalog_sqlite_repository --db /manager-data/catalog.sqlite3 --publish-stage STAGE_DIGEST --actor catalog-owner
python3 -m plasma_web.catalog_sqlite_repository --db /manager-data/catalog.sqlite3 --rollback PREVIOUS_REVISION --actor catalog-owner
```

Controller-local Profiles use `--local-file` with `namespace`, `manufacturer`,
`exact_icpn` and `profile`; they remain in `controller_overlays`, outside the
official Selector. Their payload must have `official=false`,
`execution_authorized=false` and cannot claim L2/L3. The Controller's own
authorization and Job policy remain separate. The publisher does not call PPU,
Provider, FPGA or Job execution code. No PR #1147 candidate is published by this
Milestone D implementation.

**Milestone E — Remove duplicated static coupling.**
After parity and rollback evidence, retire dynamic per-IC Python registration, global count assertions and Catalog data-triggered product pipelines. Temporary legacy/SQLite parallel reading must exist only in the shadow-comparison phase and be removed when the canonical read path switches, consistent with Replace-by-Default. Keep versioned manufacturer/Provider evidence available for audits and repeatable snapshots.

**Migration fixture:** use the existing **STM32F103 Low-density 12 exact ICPNs** from separate [PR #1147](https://github.com/physicslu/plasma/pull/1147) as a *replay fixture* (not a second authority or duplicate PR). Verify a 12-row delta, three excluded conflicted T4/T6 parts unchanged, legacy 77 L3 preserved and an 89-entry L2-or-higher projection **only when that source revision is actually admitted**. If #1147 is still Draft/unmerged, do not secretly publish its candidate records as official main.

## 7. Gate 2 readiness for this contract

Gate 2 review should verify: (a) agreement with ADR-0002/OPF/Bundle v3, (b) SQLite-first and PostgreSQL-ready interfaces without premature distributed infrastructure, (c) clear global vs Controller-local authority, (d) no runtime authorization from Catalog, (e) data-only non-code publication with transactional rollback, and (f) measurable Milestones B–E migration acceptance. Gate 2 is **only the owner-authorized merge of this documentation PR**, not an additional implementation gate. The owner approved proceeding to Gate 2 on 2026-11-18. Merging this contract does not itself install a DB, switch Manager reads, deploy to SWPC/Z2 or authorize production data migration. Those engineering milestones require implementation and actual acceptance under their approved scope, without inventing extra owner gates.
