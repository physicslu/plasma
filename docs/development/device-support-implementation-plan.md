# Device Support Catalog and Validation Implementation Plan

Status: planned work following the device-support validation contract

## 1. Goal

Build a maintainable Plasma device catalog and validation system without overstating OpenOCD, PPU, Socket, engineering, pilot, or production evidence.

The first implementation must preserve standalone PPU operation. It must not make Plasma Manager mandatory, change the canonical Plasma Protocol v3.3 / `PLASMA33` or Web REST v3 contracts without a separately approved architecture change, claim real-target validation from Mock tests, or add FastAPI/WebSocket without a separately approved architecture change.

## 2. Target architecture

Keep four layers independent:

```text
Device Catalog
    -> Programming Backend/Profile Support
        -> Model-level Compatibility and Engineering Evidence
            -> Instance-level Batch/Job Operational Evidence
```

OpenOCD is the first `ProgrammingBackend`, not a hard-coded domain boundary. A device may have multiple versioned `ProgrammingProfile` relationships, allowing future vendor CLI, Plasma-native, or FPGA-accelerated implementations.

Reusable design identity and physical asset identity remain separate:

```text
PpuModel -> PpuInstance -> SiteInstance
SocketModel -> SocketInstance
```

Model/revision records carry reusable compatibility. Instance records carry serial identity, calibration/self-test, Socket cycles, maintenance, faults, installation, and operational evidence.

## 3. Delivery sequence

### Phase 0 — Contract and source audit

- [x] Define support dimensions and validation responsibility.
- [x] Define `engineering_verified`, `pilot_reported`, and `production_reported` boundaries.
- [x] Bind physical evidence to a complete device/PPU/Socket/software configuration.
- [ ] Audit the generated OpenOCD/CMSIS/ESP-IDF catalog for licensing and redistribution.
- [ ] Quantify exact part numbers, CMSIS device names, ordering patterns, family aliases, duplicates, and unmapped identifiers separately.
- [ ] Reproduce the 5,760-record selectable research snapshot and record snapshot date, source versions, generator/importer version, mapping-rule version, source/license manifest references, and content hash before treating any count as a catalog baseline. Preserve the 24 STM32N6 and 12 TLE987x source identifiers as unmapped research records until a usable Flash bank/driver exists.
- [ ] Implement deterministic identifier classification and target-mapping rules with confidence, rule version, provenance, and an exception queue.
- [ ] Generate a machine-readable license/source manifest and quarantine sources outside an approved allowlist.
- [ ] Default customer production details to private; require explicit consent for publication or aggregation.

Exit criteria: catalog provenance and identifier kinds are understood; unresolved product/privacy decisions are recorded.

The MCU-first sequencing for the 344 target CFG files not yet expanded is defined in [OpenOCD Part-Number Expansion Plan](openocd-part-number-expansion-plan.md).

### Phase 1 — Versioned catalog artifact

Planned files:

```text
data/device-catalog/catalog.schema.json
data/device-catalog/openocd-parts.csv
data/device-catalog/openocd-parts.json
data/device-catalog/README.md
software/python/tools/import_device_catalog.py
software/python/tests/test_device_catalog_import.py
```

Tasks:

- [ ] Define a versioned JSON Schema for catalog records and provenance.
- [ ] Normalize manufacturer names without losing the original source value.
- [ ] Preserve original manufacturer family, optional manufacturer subfamily, and simplified Plasma series independently in every selectable catalog record.
- [ ] Represent `family_alias`, `cmsis_device_name`, `ordering_pattern`, and `exact_part_number` explicitly.
- [ ] Assign imported records `source_only`, backend relationships `mapping_candidate`, and configurations `not_verified` only.
- [ ] Preserve unmapped research records separately from selectable records.
- [ ] Make imports idempotent and produce added/changed/conflict/unmapped statistics.
- [ ] Emit `auto_accepted`, `needs_review`, or `rejected` for every inferred mapping; do not require bulk manual review.
- [ ] Parse OpenOCD Tcl include/driver/architecture/transport/ID constraints and compare them with authoritative vendor metadata.
- [ ] Add vendor mapping-rule fixtures so a rule change exposes all affected records before publication.
- [ ] Ensure refresh cannot delete or rewrite validation/report records.
- [ ] Add schema, duplicate, required-field, target-path, and deterministic-output tests.

Exit criteria: a reproducible, reviewed artifact can be imported twice with no unintended changes.

### Phase 2 — Domain model and persistence decision

Candidate files, subject to repository inspection at implementation time:

```text
software/python/plasma_core/device_support.py
software/python/tests/test_device_support_model.py
docs/architecture/device-support-storage.md
```

Tasks:

- [ ] Define independent catalog resolution, backend mapping, engineering level, field-use level, evidence origin, review state, lifecycle, and limitation fields.
- [ ] Define `ProgrammingBackend` and versioned `ProgrammingProfile` without OpenOCD-specific core fields.
- [ ] Define immutable `ProgrammingConfiguration`, `configuration_fingerprint`, `execution_fingerprint`, and material-revision rules.
- [ ] Separate `PpuModel`, `PpuInstance`, `SiteInstance`, `SocketModel`, and `SocketInstance`.
- [ ] Define `PASS`, `FAIL`, `NOT_TESTED`, `UNSUPPORTED`, and `SKIPPED` per-operation results.
- [ ] Define stable failure categories for device, power, PPU, Site, Socket, backend, timeout, protection, cancellation, and unknown failures.
- [ ] Define Batch, UnitRun, Job/attempt, quantity, retry, cancellation, and yield consistency rules.
- [ ] Implement the initial ownership baseline: versioned read-only catalog on each PPU, PPU-local evidence, signed export/import, and optional Manager aggregation.
- [ ] Define migration, backup, export, and rollback behavior.
- [ ] Define material configuration fingerprints and deterministic revision-compatibility rules.
- [ ] Add authorization-neutral domain invariants before adding HTTP handlers.

Exit criteria: the model rejects invalid state transitions and ambiguous configuration evidence independently of the Web layer.

### Phase 3 — Engineering validation workflow

Tasks:

- [ ] Define an engineering test-plan template with device-specific supported operations.
- [ ] Build a PPU/Site loopback and calibration self-test contract for voltage, current limit, pin drive/readback, protection, timing, and interface capability.
- [ ] Generate a Socket programming-pin manifest from versioned schematic/netlist data and compare it with authoritative device pins.
- [ ] Define a Socket continuity/short-test fixture and a machine-readable Socket profile/revision identity.
- [ ] Record sample identity/count, package, PPU model/instance, Site instance, Socket model/instance, voltage, interface, speed, software versions, and programming backend/profile.
- [ ] Record PPU calibration/self-test and Socket cycle/maintenance state with the execution evidence.
- [ ] Build a real-target runner that captures Erase, Blank Check, Program, Verify, Read, Reset/Run, boundary patterns, power cycles, retry, timing, and limitations as applicable.
- [ ] Store actual sample/cycle counts and derive named engineering levels from versioned test-plan profiles rather than manual status selection.
- [ ] Store logs/artifact references and operator/timestamp audit fields.
- [ ] Produce a content-addressed evidence manifest and compute status only when required artifacts are complete.
- [ ] Prevent Mock/CI results from creating physical validation records.
- [ ] Derive backend connection, per-operation results, and `engineering_verified` only from complete real-target evidence.
- [ ] Define invalidation/supersession behavior after material hardware, software, or profile changes.

Exit criteria: a limited-sample real-target test can produce an auditable engineering record without implying production qualification.

### Phase 4 — Read-only query API and Engineering UI

Tasks:

- [ ] Extend the existing Plasma Web REST Gateway; do not assume FastAPI or WebSocket.
- [ ] Specify REST contracts before implementation.
- [ ] Provide live, case-insensitive identifier-first search with pagination; rank exact matches before prefix matches and other partial matches.
- [ ] Expose manufacturer, original family, optional subfamily, and Plasma series as result context and optional filters; never require them before a part-number search.
- [ ] Provide device details, candidate programming profiles, compatible programming configurations, limitations, and evidence summaries.
- [ ] Expose model-level compatibility separately from current PPU/Site/Socket instance health.
- [ ] Add Engineering-mode actions for authorized validation records.
- [ ] Keep the normal customer-facing status to a small derived set.
- [ ] Show why a status applies, including package, PPU, Socket, versions, sample count, date, and evidence owner.
- [ ] Add unit/source, rendered HTML, browser E2E, and deterministic visual regression coverage as applicable.

Exit criteria: users can distinguish a catalog candidate from an exact matching engineering-validated configuration.

### Phase 5 — Customer pilot and production reporting

This phase requires authentication and organization/facility authorization. Manual quantity entry is not the primary workflow.

Tasks:

- [ ] Add authenticated customer/factory reporting permissions.
- [ ] Restrict reports to authorized organizations and facilities.
- [ ] Implement Batch -> UnitRun -> Job/attempt aggregation using batch-local unit identity when no barcode/serial is available.
- [ ] Aggregate presented, attempted, first-pass, retry-success, final-failure, and aborted quantities automatically from immutable PPU telemetry.
- [ ] Preserve Socket-contact retry cause without counting a retry as a new physical unit.
- [ ] Exclude cancellation before target operation from programming failure; record cancellation after start as `aborted`.
- [ ] Display the yield denominator and treatment of aborted/not-attempted units explicitly.
- [ ] Generate an attestation-ready production-report draft when a customer closes a batch.
- [ ] Capture batch/lot, period, failure categories, reporter, and attachments.
- [ ] Separate evidence origin (`plasma_test_runner`, `ppu_telemetry`, `customer_manual`, `partner_import`) from review state (`unreviewed`, `system_validated`, `human_reviewed`, `disputed`).
- [ ] Prevent customers from creating Plasma engineering evidence.
- [ ] Define correction/supersession instead of silently editing historical reports.
- [ ] Keep report details private by default and require explicit customer consent for publication or aggregation.
- [ ] Add privacy-aware summaries and customer-visible disclaimers.

Exit criteria: production use is truthfully displayed as customer/factory-reported evidence for one exact configuration.

### Phase 6 — Operations and lifecycle

- [ ] Define scheduled OpenOCD/CMSIS/vendor-source refresh with automatic acceptance rules and an exception-only review queue.
- [ ] Detect target-config removal, rename, or incompatible OpenOCD changes.
- [ ] Add catalog version, provenance, import report, and rollback tooling.
- [ ] Preserve the catalog snapshot, backend/profile versions, and configuration/execution fingerprints referenced by historical evidence.
- [ ] Diff license/source manifests and quarantine new or changed redistribution terms.
- [ ] Add deprecation/blocking workflow and customer-visible limitations.
- [ ] Compare material configuration fingerprints and automatically create revalidation work only for affected configurations.
- [ ] Add export/backup for validation and customer-report records.
- [ ] Define operational metrics without exposing private customer data.

Exit criteria: catalog refresh and product updates cannot silently overstate or destroy support evidence.

## 4. Minimum data contracts

### Catalog record

```text
manufacturer
manufacturer_family
manufacturer_subfamily (nullable when unavailable)
plasma_series
identifier
identifier_kind
package (nullable until authoritative)
catalog_resolution
source_type
source_url
source_version
mapping_rule
imported_at
```

### Programming backend/profile relationship

```text
device_variant_id
backend_type
backend_version_range
profile_id/version
transport/interface
declared_operation_capabilities
mapping_state
automation_decision/confidence
mapping_rule/version
source_references
```

### Programming configuration

```text
device_variant_id
package_variant_id
programming_interface
target_voltage/settings
programming_backend/profile/version
ppu_model/revision
site_interface_profile/revision
socket_model/revision
algorithm/settings_revision
configuration_fingerprint
```

### Engineering validation

```text
programming_configuration_id
execution_fingerprint
ppu_instance_id/site_id
socket_instance_id
sample_count
operation_results
cycle_count
timing/results
limitations
failure_categories
operator
performed_at
artifact_references
```

### Batch and unit execution

```text
batch_id/facility/customer
programming_configuration_id
catalog_snapshot/profile/software versions
unit_run_id, unit_identifier, and optional customer barcode/manufacturing serial
job/attempt identifiers
operation results/failure categories
presented/attempted/first_pass/retry_success/final_failure/aborted counts
ppu_instance/site/socket_instance
started_at/closed_at
```

### Customer use report

```text
programming_configuration_id
batch_id
organization/facility
batch/lot and period
presented/attempted quantities
first_pass/retry_success/final_failure/aborted quantities
failure_categories
reporter and reported_at
evidence_origin
review_state
artifact_references
```

## 5. Required invariants and tests

- [ ] No import path can create a physical-validation status.
- [ ] No overall status is accepted directly from an untrusted UI client.
- [ ] Every engineering/pilot/production record references one immutable configuration.
- [ ] OpenOCD-specific fields do not leak into backend-neutral device or evidence contracts.
- [ ] Package, PPU model revision, Socket model revision, and relevant software/profile versions participate in the configuration fingerprint.
- [ ] PPU instance, one-based Site identity, Socket instance, calibration, and runtime versions participate in the execution fingerprint.
- [ ] Programming Asset source identity and Normalized Image execution identity remain distinct in evidence/fingerprint contracts.
- [ ] `equipment_serial_number`, Batch `unit_identifier`, and the `serial_number` Programming Asset remain separate namespaces unless an explicit workflow binding links them.
- [ ] Model-level compatibility never implies current instance health.
- [ ] One failing instance never blocks an entire model without a separate model-level finding.
- [ ] A result for one Socket/package cannot automatically validate another.
- [ ] Customer roles cannot create `engineering_verified` records.
- [ ] Evidence review does not change customer evidence into Plasma evidence.
- [ ] A `ppu_telemetry` report is reproducible from immutable PPU job records and still requires customer/factory attestation before customer-reported publication.
- [ ] `NOT_TESTED`, `UNSUPPORTED`, and `SKIPPED` never become `PASS`; required operations come from a versioned test-plan profile.
- [ ] Batch totals satisfy `attempted = first_pass + retry_success + final_failure + aborted` at close.
- [ ] Batch-close UnitRun dispositions are mutually exclusive, `presented >= attempted`, and intermediate failed/aborted attempts remain in Job telemetry.
- [ ] Multiple retry Jobs under one UnitRun never increase the physical-unit count.
- [ ] Cancellation and Socket-contact retry rules are deterministic and covered by tests.
- [ ] Mock, CI, SSR, and E2E results are never represented as real-target evidence.
- [ ] Catalog refresh preserves historical validations and reports.
- [ ] Quantity fields are non-negative and internally consistent.
- [ ] Superseded records remain auditable.
- [ ] UI labels are derived from matching records and expose limitations.
- [ ] Uncertain imports enter an exception queue; they never become selectable through confidence alone.

## 6. Pull request plan

Use focused PRs rather than one large implementation:

1. Catalog schema, cleaned seed artifact, import report, and importer tests.
2. Backend-neutral domain model, model/instance identities, fingerprints, invariants, persistence architecture, and unit tests.
3. Engineering validation, operation/failure taxonomy, PPU/Socket self-test records, and real-target test-plan contract.
4. Read-only REST queries, model-versus-instance health, and Engineering-mode UI.
5. Batch/UnitRun/Job aggregation, authentication/privacy, and customer pilot/production reporting.
6. Catalog refresh, deprecation, backup, export, and lifecycle automation.

Each PR must state what was tested and what was not. Software tests must not be reported as PPU, Socket, OpenOCD, Z2, real-IC, pilot, or production validation.

## 7. Definition of done for the complete feature

- Device identifiers and exact part numbers are visibly distinct.
- Programming-backend mappings retain authoritative provenance and mapping rationale; OpenOCD is replaceable/extendable.
- Engineering evidence is bound to exact hardware/software configurations.
- Model-level compatibility and instance-level operational health are visibly separate.
- Socket instances have cycle, maintenance, installation, and fault identity.
- Operation results and failure categories are stable and queryable.
- Batch yield is reproducible from UnitRun and Job attempts without counting retries as new units.
- Customer pilot/production use remains customer/factory-reported.
- Standalone PPU operation remains available without Plasma Manager.
- Catalog refresh is reproducible and cannot overwrite evidence.
- API and UI permissions enforce evidence ownership.
- Tests cover state derivation, authorization boundaries, revision matching, import idempotency, and historical preservation.
- Documentation and UI do not claim validation beyond observed evidence.
