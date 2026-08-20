# Device Support and Validation Architecture

Status: proposed contract for implementation

## 1. Purpose

Plasma needs a device catalog that answers two different questions without confusing them:

1. Can an IC identifier be associated with a versioned programming backend/profile?
2. Has a specific IC, package, PPU, Site interface, Socket, and software combination actually been tested?

An OpenOCD target file or CMSIS Device Family Pack entry is evidence for a catalog candidate. It is not evidence of successful programming, PPU compatibility, Socket compatibility, pilot production, or volume production.

## 2. Scope and non-goals

This contract covers:

- manufacturer, family, device identifier, ordering pattern, and exact orderable part number records;
- programming-backend/profile candidate mappings and their provenance, beginning with OpenOCD;
- Plasma engineering validation using a limited number of physical samples;
- customer-reported pilot and production use;
- PPU, Site electrical interface, Socket, package, and software-version identity;
- customer-facing support labels and evidence boundaries.

This contract does not claim that Plasma can perform volume-production qualification. Plasma can verify engineering samples. Pilot and production results belong to the customer or factory that operated the recorded programming configuration.

## 3. Terminology

| Term | Meaning |
|---|---|
| Device identifier | A CMSIS/DFP or vendor identifier that may represent a family, device, or orderable part. |
| Ordering pattern | A wildcard or pattern covering multiple orderable parts. It is not an exact part number. |
| Part number | An exact orderable manufacturer part number when the source proves that granularity. |
| Programming backend | The implementation used to program a device, such as OpenOCD, a vendor CLI, or a future Plasma-native/FPGA backend. |
| Programming profile | A versioned backend-specific target, transport, operation-capability, and algorithm/settings definition. |
| Device variant | A device record at the most authoritative available orderable-part and package granularity. |
| PPU | One physical Plasma Programming Unit. |
| Site | One independently controlled Programming Site within a PPU. |
| Socket | The mechanical/electrical fixture attached to a Site. It is not the Site identity. |
| Programming configuration | The immutable compatibility combination of device, package, interface, PPU model revision, Socket model revision, and programming profile. It may be unverified. |
| Configuration fingerprint | A deterministic digest of the material fields in a programming configuration. |
| Engineering validation | Limited-sample testing performed by Plasma. |
| Pilot report | Small-batch use reported by a customer or factory. |
| Production report | Volume-production use reported by a customer or factory. It is not a Plasma certification. |

## 4. Separate status dimensions

Support must not be represented by one linear status. Catalog resolution, backend mapping, physical validation, field use, evidence origin/review, lifecycle, and limitations are independent dimensions.

### 4.1 Catalog resolution

| Machine value | Meaning |
|---|---|
| `source_only` | A source record exists but its identity granularity is not normalized. |
| `normalized` | Manufacturer, family, identifier, and identifier kind meet deterministic catalog rules. |
| `conflicted` | Authoritative sources disagree or normalization is ambiguous. |
| `excluded` | The record is intentionally unavailable to the selectable catalog. |

### 4.2 Programming-backend mapping

A device may have zero or many programming profiles. Each relationship has an independent resolution state:

```text
no_mapping | mapping_candidate | mapped | rejected
```

Each relationship records:

```text
backend_type
backend_version range
profile identifier and version
transport and interface
declared operation capabilities
mapping rule/version and provenance
resolution state and confidence
```

OpenOCD is the first backend, not the domain model. Future values may include `vendor_cli`, `plasma_native`, or `fpga_accelerated` without changing device or evidence semantics.

Imported OpenOCD/DFP/ESP-IDF device records start at `source_only`; deterministic identity rules may promote them to `normalized`. A backend relationship starts at `mapping_candidate` and may become `mapped` or `rejected`. Imports must never create physical-validation evidence.

### 4.3 Validation and field-use levels

Engineering validation:

| Machine value | Evidence owner | Meaning |
|---|---|---|
| `not_verified` | None | No physical validation exists for this exact configuration. |
| `engineering_verified` | Plasma | Limited physical samples passed the declared engineering test plan. |

Field-use evidence:

| Machine value | Evidence owner | Meaning |
|---|---|---|
| `none` | None | No customer/factory field-use report exists. |
| `pilot_reported` | Customer or factory | Small-batch result was reported for the exact configuration. |
| `production_reported` | Customer or factory | Production use was reported for the exact configuration. This is not a Plasma guarantee. |

The product must not use `production_verified` unless a separate certification program, acceptance criteria, audit process, and legal responsibility are approved in the future.

`not_verified`/`engineering_verified` is the engineering-validation dimension. `pilot_reported`/`production_reported` is a separate field-use dimension and must not overwrite engineering evidence.

### 4.4 Evidence origin and review

Evidence origin and evidence review are separate fields.

| Evidence origin | Meaning |
|---|---|
| `plasma_test_runner` | A Plasma real-target engineering runner generated the evidence. |
| `ppu_telemetry` | Immutable PPU batch/job records generated the evidence. |
| `customer_manual` | A customer manually supplied the result. |
| `partner_import` | An approved partner supplied a structured result. |

| Review state | Meaning |
|---|---|
| `unreviewed` | No structural or human review is complete. |
| `system_validated` | Schema, hashes, identity, quantities, and required evidence passed deterministic checks. |
| `human_reviewed` | An authorized reviewer examined the evidence and recorded the review. |
| `disputed` | A conflict or correction prevents normal use of the evidence. |

Review state confirms evidence integrity or review history; it does not change customer evidence into Plasma engineering evidence.

### 4.5 Lifecycle and limitations

Lifecycle is independent:

```text
active | deprecated | blocked
```

Lifecycle is scoped to the entity that owns it. Blocking one PPU/Site/Socket instance does not block its model; blocking one programming profile does not block other backends. Every non-active lifecycle value records reason, authority, and effective timestamp.

Restrictions such as unsupported Read, protection limitations, speed ceilings, or voltage constraints belong in structured `limitations`; they must not be hidden inside one status string.

## 5. Configuration identity and fingerprints

Every physical result must bind to at least:

```text
device record / exact part number when known
package
programming interface
target voltage and relevant electrical limits
programming backend/profile and versions
PPU model and hardware revision
Site interface revision or capability profile
Socket model/adapter revision
Plasma software version
algorithm/settings revision
```

The `configuration_fingerprint` covers reusable compatibility fields: device variant, package, programming backend/profile, interface, voltage/settings, PPU model/revision, Site interface profile/revision, Socket model/revision, and algorithm/settings revision.

An `execution_fingerprint` additionally covers the actual PPU instance, Site, Socket instance, source Programming Asset identity/SHA when relevant, Normalized Image SHA for Program/Verify, PPU software/runtime build, calibration record, and runtime configuration used for one test or batch. Asset SHA and Normalized Image SHA are distinct identities and must not be collapsed merely because `image + binary` currently normalizes one-to-one.

Changing a material compatibility field creates a different programming configuration. A result for an LQFP Socket must not automatically validate a BGA Socket. Instance health and calibration cannot be inferred from model-level engineering validation.

## 6. Model-level compatibility and instance-level health

Design compatibility and operational health must use separate identities.

```text
PpuModel / hardware revision
└── PpuInstance / equipment_serial_number
    └── SiteInstance / one-based site_id

SocketModel / design revision
└── SocketInstance / equipment_serial_number or managed asset ID
```

`PpuModel` and `SocketModel` describe reusable design compatibility. `PpuInstance`, `SiteInstance`, and `SocketInstance` describe the equipment that executed a test or production job.

Identity namespaces are intentionally separate:

```text
equipment_serial_number   identifies a physical PPU or Socket asset
unit_identifier            identifies one physical IC occurrence in a Batch
serial_number Asset        programming data provisioned to the target product/device
```

A manufacturing unit identifier may equal a provisioned Serial Number in a specific workflow, but Plasma must model that as an explicit binding, not assume the namespaces are identical.

Engineering validation may establish compatibility for a model/revision combination. Operational readiness additionally requires current instance evidence, including calibration/self-test state, enabled Site capability, Socket installation, accumulated cycles, maintenance status, and known faults.

A fault on one PPU, Site, or Socket instance must not mark the entire model unsupported. Conversely, model-level validation must not claim that every physical instance is currently healthy.

## 7. Engineering validation owned by Plasma

Plasma engineering validation may include:

- visual confirmation of device marking, package, and fixture identity;
- power-off continuity/pin-map inspection where applicable;
- voltage and current-limit setup;
- programming-backend connection and device-ID check;
- erase and blank check when supported;
- program;
- verify or checksum comparison;
- read when supported and permitted;
- reset/run behavior when included in the profile;
- repeated cycles on a declared number of samples;
- duration, programming speed, failure, retry, and operator notes;
- retained logs and test artifacts.

The record must state the sample count and operations actually executed. Missing or unsupported operations must remain explicit. Mock, CI, and software-only tests cannot create an engineering validation record.

### 7.1 Per-operation result

Every declared operation records one of:

```text
PASS | FAIL | NOT_TESTED | UNSUPPORTED | SKIPPED
```

`UNSUPPORTED` may be acceptable when the programming profile and UI disclose the limitation. `NOT_TESTED` can never be interpreted as `PASS`. A versioned test-plan profile defines which operations are required for a named engineering level.

### 7.2 Failure taxonomy

Failures must use stable categories before free-form detail:

```text
DEVICE_NOT_DETECTED
DEVICE_ID_MISMATCH
POWER_FAULT
OVERCURRENT
SOCKET_CONTACT
ERASE_FAILED
BLANK_CHECK_FAILED
PROGRAM_FAILED
VERIFY_FAILED
READ_FAILED
PROTECTION_ENABLED
RESET_RUN_FAILED
TIMEOUT
BACKEND_ERROR
OPERATOR_ABORT
UNKNOWN
```

This separation permits Plasma to distinguish device-algorithm problems from PPU, Site, Socket, power, operator, and backend failures.

## 8. Customer pilot and production reports

Only the customer or factory operating the process can report pilot or production use. A report should capture:

- programming-configuration and execution fingerprints;
- reporting organization and facility identity with access control;
- lot or batch reference;
- report period;
- presented quantity;
- attempted quantity;
- first-pass success quantity;
- retry-success quantity;
- final-failure quantity;
- aborted quantity;
- failure categories;
- relevant logs or report attachment references;
- reporter identity and timestamp;
- evidence origin and review state.

Production quantities are observations for one configuration and environment. They do not guarantee equal results for other packages, PPU revisions, Socket revisions, lots, factories, voltages, speeds, or software versions.

### 8.1 Batch, unit, and job aggregation

Production evidence is derived through this hierarchy:

```text
Batch
└── UnitRun (one physical IC occurrence in the batch)
    └── Job / operation attempts
```

A Job is not a produced unit. Retries create additional Jobs/attempts under the same `UnitRun`. An external `unit_identifier` such as a barcode or manufacturing serial may identify a unit; when unavailable, Plasma assigns a batch-local immutable unit identifier. This identifier is not automatically the same thing as the `serial_number` Programming Asset that may be provisioned to the target.

At batch close, the system records:

```text
presented_count
attempted_count
first_pass_success_count
retry_success_count
final_failure_count
aborted_count
```

For a closed batch:

```text
attempted_count
  = first_pass_success_count
  + retry_success_count
  + final_failure_count
  + aborted_count
```

`presented_count` counts units introduced to the process. `attempted_count` begins when a target operation actually starts. Cancellation before target operation is not a programming failure; cancellation after start is `aborted` and remains visible. Socket-contact retries remain retries with `SOCKET_CONTACT` cause rather than new units. Yield definitions and denominator must be displayed explicitly instead of silently treating aborted or never-attempted units as failures.

The batch-close categories are mutually exclusive final `UnitRun` dispositions. For example, a UnitRun with an aborted attempt followed by successful retry is `retry_success`, not also `aborted`. Operation-attempt telemetry retains the intermediate abort. `presented_count >= attempted_count` must always hold.

## 9. Customer-facing presentation

The normal device selector should keep status simple:

| UI label | Derived meaning |
|---|---|
| Not verified | Source-only, mapping-candidate, or mapped profile; no matching physical validation. |
| Plasma engineering verified | A matching immutable configuration has Plasma engineering evidence. |
| Customer pilot reported | A matching configuration has a customer/factory pilot report. |
| Customer production reported | A matching configuration has a customer/factory production report. |
| Limited | A usable record has declared restrictions. |
| Blocked / unsupported | A known problem prevents supported use. |

The details view must expose the PPU, Socket, package, interface, relevant versions, sample/quantity count, last validation/report date, limitations, and evidence owner. Search results must not reduce a device-level candidate and a configuration-level validation into one ambiguous badge.

## 10. Required domain records

The implementation should separate these records:

1. `Manufacturer`
2. `DeviceFamily`
3. `DeviceRecord`
4. `DeviceVariant`
5. `PackageVariant`
6. `ProgrammingBackend`
7. `ProgrammingProfile`
8. `PpuModel`
9. `PpuInstance`
10. `SiteInstance`
11. `SocketModel`
12. `SocketInstance`
13. `ProgrammingConfiguration`
14. `EngineeringValidation`
15. `Batch`
16. `UnitRun`
17. `ProgrammingJob`
18. `CustomerUseReport`

`DeviceRecord.identifier_kind` must distinguish at least:

```text
family_alias
cmsis_device_name
ordering_pattern
exact_part_number
```

The current OpenOCD-derived catalog must not label every identifier as an exact orderable part number.

## 11. Provenance and audit requirements

Catalog and evidence data must retain:

- source type and canonical source URL;
- source vendor/package/repository version;
- import timestamp and importer version;
- mapping rule or authorized exception decision;
- creator/reporter/reviewer identity;
- creation and review timestamps;
- immutable evidence or artifact references;
- superseded/deprecated relationship rather than destructive replacement.

Catalog refresh must not overwrite engineering validations or customer reports. A source update may supersede a candidate mapping, but historical test records must continue to reference the exact configuration that was tested.

## 12. Authorization boundaries

- Catalog import may create or update catalog candidates and provenance.
- Plasma engineering roles may create engineering validations after physical testing.
- Customers may submit reports only for organizations/facilities they are authorized to represent.
- Customers cannot mark a configuration as Plasma engineering verified.
- Reviewing evidence cannot rewrite the original reporter or quantities.
- Status derivation must be deterministic from authorized records; UI clients cannot submit an arbitrary overall support badge.

## 13. Initial catalog baseline

A pre-import research snapshot counted 5,760 selectable OpenOCD candidate records across ten vendor groups and also contained broader authoritative identifiers that remain unmapped. The selectable count excludes 24 STM32N6 and 12 TLE987x identifiers because their current target CFG files do not configure an OpenOCD Flash bank/driver. This number is research evidence only, not a canonical product count or support guarantee. It must not be promoted to a shipped catalog baseline until the snapshot is reproducible and carries snapshot date, source versions, generator/importer version, mapping-rule version, source/license manifest references, and a content hash.

Before import into Plasma:

- deduplicate identifiers using vendor-aware normalization;
- retain original spelling and provenance;
- separate exact part numbers from CMSIS names and ordering patterns;
- keep unmapped records available for research but hidden from the normal supported-device selector;
- assign imported records `source_only`, relationships `mapping_candidate`, and configurations `not_verified`;
- validate licensing and redistribution requirements for generated catalog data.

## 14. Automation-first uncertainty resolution

Uncertainty should be converted into machine-checkable evidence and an exception queue. Humans should not review thousands of records one by one.

### 14.1 Resolution states

Every inferred catalog field or mapping should include:

```text
automation_decision: auto_accepted | needs_review | rejected
confidence: 0.0 .. 1.0
rule_id and rule_version
source references
conflict reasons
```

`confidence` is diagnostic; deterministic acceptance criteria decide `automation_decision`. A high score alone must not create catalog normalization, a mapped backend relationship, or physical-validation status.

### 14.2 Automation-first resolution matrix

| Uncertain area | Default automated solution | Human exception only |
|---|---|---|
| Identifier kind | Use structured DFP/PDSC hierarchy, vendor order-code fields, and vendor-specific tested patterns to classify family aliases, CMSIS device names, ordering patterns, and exact parts. Conflicting or incomplete records stay non-selectable. | Review new vendor formats or conflicts that no deterministic rule resolves. |
| OpenOCD mapping | Parse the Tcl include graph, target/flash driver, architecture, transport, expected ID registers, and family constraints; require a compatible intersection with authoritative vendor metadata. Run regression fixtures for every mapping rule. | Review ambiguous many-to-many matches or add a new mapping rule. |
| Package and pinout | Import only structured vendor package/pin data with provenance. Generate a pin-map manifest and compare required programming/power/reset pins. Unknown package or pin data remains `unknown`; Plasma must not guess from a PDF filename. | Confirm a new Socket design or resolve contradictory vendor sources. |
| License/redistribution | Generate a source manifest containing license URL/text hash, file provenance, extraction method, and redistribution class. Accept only an approved allowlist; quarantine unknown or changed terms automatically. | Legal/product approval for a new or changed license. |
| PPU electrical capability | Establish the model/revision capability with an automated loopback/calibration fixture, then run instance/Site self-test for voltage, current limit, pin drive/readback, timing, protection, and interface checks. Store calibrated results against the actual instance. | Initial fixture safety approval and investigation of failures. |
| Socket correctness and health | Generate the Socket-model pin map from the versioned schematic/netlist, compare it with the device programming-pin manifest, and run continuity/short testing. Track each Socket instance's installation, accumulated cycles, maintenance, contact-test result, and faults. | First physical seating/contact inspection and failures that require mechanical judgment. |
| Device algorithm | Use a real-target validation runner to execute the declared operation matrix, multiple data patterns, boundary sizes, repeated cycles, reset/power-cycle checks, and evidence capture. | Insert/replace physical samples and diagnose failures; the pass/fail calculation is automatic. |
| Sample count | Do not invent an absolute production claim. Record the actual sample and cycle counts. The UI displays them, while a versioned test-plan profile defines the minimum for a named engineering level. | Approve a new test-plan profile, not each result. |
| Revision compatibility | Compute configuration fingerprints from material fields. Identical fingerprints inherit query compatibility automatically. A changed material fingerprint creates a new configuration and requires revalidation unless a documented compatibility rule proves equivalence. | Approve a new compatibility rule or waiver with rationale. |
| Customer production result | Build a report draft automatically from immutable PPU batch/job telemetry, including attempted, first-pass, retry, failure, versions, PPU, Site, and Socket. The customer closes/attests the batch instead of typing totals. | Customer confirmation, correction reason, and consent for visibility. |
| Evidence integrity | Store a content-addressed manifest with hashes for logs, configuration, software versions, test plan, results, and attachments. Derive status only from complete manifests. | Review tampering, missing evidence, or exceptional retention requests. |

### 14.3 Default deployment and privacy choices

The lowest-risk initial implementation is:

- ship a versioned read-only catalog snapshot with each standalone PPU;
- store engineering evidence on the PPU that performed the test and support signed export/import;
- keep Plasma Manager optional and use it only for aggregation when enabled;
- keep organization, facility, batch, quantities, and attachments private by default;
- publish or aggregate customer production information only after explicit customer consent;
- retain evidence metadata and hashes across catalog upgrades even when large artifacts follow a configurable retention policy;
- use versioned forward migrations and rollback to an earlier catalog snapshot without deleting later evidence.

This baseline removes a database-ownership blocker without requiring distributed synchronization in the first release.

### 14.4 Human gates that remain necessary

Automation can reduce manual work to exceptions, but it cannot truthfully remove these gates:

1. Safety approval for a new electrical/Socket test fixture before it can drive a real IC.
2. Physical confirmation that the first sample and Socket orientation/contact are correct.
3. Handling and replacement of the limited physical engineering samples.
4. Customer/factory attestation that an automatically generated batch report represents their production use.
5. Consent before customer-identifying or quantity information is shared outside that customer.
6. Legal approval when source licensing is absent, changed, or outside the approved allowlist.
7. Engineering investigation of automated conflicts, electrical failures, or ambiguous sources.

These are narrow approval or exception tasks. Normal catalog refresh, mapping, self-test, algorithm execution, evidence capture, status derivation, and batch aggregation should be automated.
