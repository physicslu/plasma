# PPU single deployment entry — Gate 1 Path 1 (Host-only integration baseline)

> **Status:** owner-approved 2026-10-29, including revised Gate 1 Path 1 for PS Runtime API/Coordinator correlation; Draft PR, **NOT deployed or merged**. No SWPC/Z2 operation or Linux permission change. Original baseline `main e338083564c30dc6bdc24009f7b62a3984fb7023` has been reconciled with merged #1208 at `main 1fb0c4b6c95e9da8f746fc3571a160b5a8bf6390`. The Host-only Master role contract is not a deployed Principal/Root authorization boundary.

## Latest owner decision — revised Gate 1, generic package + single Engine (2026-10-29)

**This section supersedes the earlier three-module-only design limits below.**
The PPU is a dedicated embedded IC programmer: it needs **one logical Deployment
Engine**, not a fleet-oriented Coordinator → Installer Adapter → privileged
daemon chain. Reuse the existing `DeploymentCoordinator` transaction process as
that Engine, its **one** `deployment.lock` and **one** `deployment.json`. The
existing PS Runtime installer verification functions remain internal helpers;
there is no new install service/adapter, separate lock or journal.

The new package envelope `plasma.ppu.package.v1` is independent of a static
module-name allowlist. A ZIP has one strict `manifest.json` and declared
`payload/` files, with exact byte count and SHA-256 for each file; the manifest
records `name`, `version`, immutable source commit, `kind`, and target
`platform`/`board`/`fpga_part`. Supported data types are `native-c`, `python`,
and `fpga-image`. An FPGA package additionally declares an Image + HWH pair.
Compatibility is compared with an independently supplied target profile. ZIP
symlinks, duplicate entries/JSON keys, traversal, undeclared files, digest
mismatch, nonregular entries and incompatible board identity are denied.
The v1 Host-only file-shape boundaries are independent of module names:
`native-c` accepts executable files only under `payload/bin/` and
nonexecutable `.so`/`.a` libraries or `.h`/`.hpp` headers under `payload/lib/`
and `payload/include/`; `python` accepts nonexecutable Python and reviewed
configuration/text extensions under `payload/python/`, `payload/scripts/`, or
`payload/software/python/`; `fpga-image` accepts only nonexecutable
`.bit`/`.bin`/`.hwh`/`.json` under `payload/fpga/`, still requiring the exact
declared Image/HWH pair. Cross-kind payload paths fail closed. This restricts
package *data shape*, never authorizes execution or production installation.
Module names identify a package; they do **not** grant Root, file write,
execution or authority. Authentic publisher approval, target Master and
protected Root Source Pin remain **unqualified for production**.

`DeploymentCoordinator.execute_package_host_only()` reuses the existing lock,
journal and recovery classification, validates a package, stages files only
inside a deliberately isolated Host-only simulation tree, atomically changes a
version receipt, verifies staged contents, and compensates/rolls back an
activation failure. Unverified restoration becomes `recovery_required`. It
never executes package C/Python, loads FPGA, changes `/opt/plasma` or activates
systemd. Both the Bootstrap network endpoint and SWPC HTTPS client continue to
reject Engineering/FPGA deployment requests. The existing SSH implementation
and local factory rescue remain unchanged until *separately authorized* live
parity, ownership and recovery evidence exists.
When reusing a previously staged release, the same Host-only Engine now
checks that its file set is exact and that no nested symlink or undeclared file
was inserted; any mismatch fails closed with a journaled transaction outcome.

**First Host-only acceptance batch**: `wordport`, `openocd-integration` and
`abtest`, using the merged #1207 package/source as the compatibility reference;
additional synthetic native-C and FPGA Image/HWH packages prove the generic
envelope is not a three-module special case. Positive stages and rollback
negative tests are *simulation evidence only*: no SWPC, Z2, FPGA or DUT was
accessed. Cross-host commit, actual protected Installer/Root authority, real
API Master authorization and deployment still require later qualification.

The paragraphs below record the **prior Gate 1 baseline/history**, including
the previously intentional exact-three allowlist, and must not be mistaken for
the revised generic Host-only architecture above.

## Owner architecture decision — unified multi-purpose Capability Package (2026-10-29)

**Status: architecture decision / proposed contract extension; NOT implemented or qualified.** This decision extends the generic single-Engine direction above; it does not replace the existing Bootstrap transaction, authorize device access, or change the current `plasma.ppu.package.v1` validator.

**One logical Package, one network upload/validation path, one Deployment Engine; separate execution lifecycles.** Production programming, engineering diagnostics, experimental testing, and PPU system/runtime updates all use the same PPU Package ingress and existing Bootstrap `POST /v1/deployments` transaction authority. Purpose-specific authorization and execution remain separate. Do not add a second deployment service, installer adapter, lock, journal, SSH writer, or privileged daemon. A common upload mechanism does **not** mean the currently PS-runtime-only API already admits all purposes.

### Package composition and dependency resolution

- SWPC resolves an **exact ICPN** and intended operation to required PS parsers/providers, programming profile/qualification references, programming asset/firmware, and any required PL image. A complete immutable Manifest describes all dependencies, including independently pinned PPU-resident components; only missing or changed content-addressed components need transfer after verified target inventory. Do not trust an unverified cache hit.
- The **Base FPGA** is preinstalled on the PPU and normally reused without transmission or reprogramming. A **specialized FPGA** is an optional component only when the selected operation needs additional PL capability. Reuse a compatible, already verified specialized image when present. No exact-ICPN-to-unique-bitstream assumption.
- A specialized FPGA is delivered with its required paired image/manifest and, where applicable, HWH metadata, verified against board/FPGA part, hardware ABI, current Root Guard and Golden/recovery policy. A valid digest or pairing is **not** publisher authentication. Never overwrite the protected Golden image as an ordinary package update.
- A single logical Bundle may contain multiple components (native C, Python, PL image, profiles and optional firmware). This requires a **versioned multi-component Bundle/Manifest contract** beyond the current single-`kind` Host-only `plasma.ppu.package.v1`; define compatibility and dependency rules without silently widening v1 admission.
- Shared FPGA fabric may serve multiple Sites. A whole-image replacement is a **PPU-wide hardware resource change** unless verified isolation/partial reconfiguration exists. Enforce active Site/job quiescence, exclusive owner/lease, safe electrical state and proven recovery before any PL change. Do not assume independent per-Site image swapping.
- A programming asset may be packaged for delivery but **programming a DUT is not a deployment transaction**. Installation/activation is journaled by the one Deployment Engine; Programming Jobs, diagnostics sessions and experiments retain their own operation IDs, permissions, outcomes and evidence. Do not claim IC Flash erase/program/OTP/security operations are generally reversible.
- A Bundle's declared `purpose` (e.g. `programming`, `diagnostics`, `experiment`, `system`) selects admission policy, **not privilege by itself**. A programming Bundle cannot self-assert ICPN L2/SUPPORTED status; the PPU checks independently trusted ProgrammingQualification, target compatibility and operation authorization. Experimental payloads must not auto-promote to production.
- Reuse the existing PS-local OpenOCD/WordPort and protected FPGA Root boundaries. SWPC distributes high-level packages and jobs, never live per-bit SWD execution.

### Unified logical flow

`SWPC exact ICPN / diagnostic / experiment / system intent`
→ `Capability Resolver + complete dependency Manifest`
→ `existing bounded PPU upload + integrity/provenance validation`
→ `existing Bootstrap Deployment API + single DeploymentCoordinator lock/journal`
→ `verified stage/install/activate of required PS/PL/data components`
→ `purpose-specific Programming Engine / diagnostic / experimental / runtime lifecycle`.

The **common ingress** is a logical reuse of existing capabilities, not a new server or separate privileged control plane. Avoid unnecessary transfer of Base FPGA or identical verified artifacts. Factory/Engineer recovery remains independent of ordinary network deployment.

### Gap audit — implementation versus target architecture (as of 2026-10-29)

| Priority | Capability / missing work | Verified baseline or gap | Required acceptance |
| --- | --- | --- | --- |
| P0 | Multi-purpose, multi-component Bundle contract | **MISSING**: current `plasma.ppu.package.v1` Host-only verifier is single-`kind` (`native-c`, `python`, `fpga-image`); no complete PS+PL+profile+firmware Bundle semantics | Versioned Manifest schema, exact file/dependency validation, incompatible/duplicate/missing-component negatives, v1 compatibility |
| P0 | Exact-ICPN Capability Resolver | **MISSING** as unified deployment selection: target IC, Provider, Parser, base/special PL ABI and firmware dependency resolution are not an end-to-end Bundle contract | Deterministic resolution and independently verified qualification/compatibility; no self-authorized SUPPORTED/L2 |
| P0 | Unified purpose-based authorization | **NOT QUALIFIED**: active Master generation/revocation, trusted publisher/source, TLS server and least-privilege installer not live-qualified | Fail-closed authorization for programming/diagnostics/experiment/system; reject escalation and untrusted source |
| P0 | SWPC API migration + real installation | **PARTIAL HOST-ONLY**: HTTPS client and shared Coordinator tests exist, but engineering/FPGA API admission rejects; engineering CLI still writes via SSH | One actual API/lock/journal and trusted PS install/activation; verified two-host receipts/compensation before SSH retirement |
| P0 | PPU-wide quiescence and FPGA safety | **NOT QUALIFIED** for unified Bundle activation; existing protected Root/owner/Golden rules must be preserved | Real owner/lease, Site/job exclusion, board/ABI/Image+Manifest pairing, failed-load/unknown-state recovery |
| P1 | Base/specialized FPGA inventory and reuse | **MISSING** as Bundle dependency/cache policy | Verified component identity/ABI, content-addressed cache hits, no unnecessary Base FPGA upload/reload, cache corruption negatives |
| P1 | Shared ingress for firmware/profile data | **MISSING** as unified Bundle delivery/activation contract; existing PS-runtime upload is not a general programming-asset service | Bound size, hashes, safe parsing, version pinning, data-vs-executable separation, no unintended install authority |
| P1 | Purpose-specific execution isolation | **MISSING** as an end-to-end package-to-job/session contract | Separate Programming Job / diagnostic / experiment IDs, lifecycle and evidence; deployment does not auto-execute |
| P1 | Cross-host consistency and recovery | **PARTIAL HOST-ONLY**; no proven atomic SWPC+PPU activation | Idempotent receipts, crash/reboot/timeout reconciliation, bounded compensation and `recovery_required` for ambiguity |
| P1 | Mixed-package and eight-Site acceptance | **NOT RUN** on physical target | Host-only negative matrix, then separately authorized PPU hardware acceptance, concurrent Site conflicts and recovery |
| P2 | Partial reconfiguration | **UNDECIDED / NOT A PREREQUISITE** | First prove whole-image switching safety; evaluate partial reconfiguration only if hardware/resource economics justify it |

**Delivery sequencing:** (1) freeze Bundle v2/purpose/dependency/ICPN contracts and Host-only tests; (2) qualify existing API/Engine trusted real installation and component inventory; (3) integrate programming/diagnostic/experiment activation with Root/Site exclusion; (4) run separately authorized end-to-end SWPC/PPU and hardware recovery acceptance; (5) retire legacy SSH only after proven parity. No merge, deployment, Root/FPGA load, SWPC/Z2/DUT operation or production qualification is implied by this documentation.

## Decision: one product-facing installation endpoint, one transaction

The **only target normal-install endpoint** is the existing Z2 PPU Bootstrap `POST /v1/deployments`; SWPC `ppu-deploy` and Console are *clients*, not independent Z2 installers. The authoritative transaction must be the existing `scripts/ppu-bootstrap-deployment.py`: `/var/lib/plasma-bootstrap/deployment.lock` plus `deployment.json`, verified release staging, activation and rollback. `ppu-z2-installer.py` and its Core remain **internal** verified PS installers, not separate product APIs. `ppu-bootstrap-installer.py` remains only **local factory/Engineer recovery**, outside normal network deployment. Protected FPGA Root `download|test|restore` remains hardware lifecycle and recovery, not an Image installation API.

| Entry or subsystem | Current factual behavior | Gate 1 contract / intended endpoint |
| --- | --- | --- |
| Console/Manager Bootstrap HTTP | One authenticated PS Runtime install API using the existing device-local Bootstrap Bearer token and bounded upload/transaction | **KEEP** `POST /v1/deployments` as the only product installation API. Existing token proves controlled commissioning authority, **not** registered Master generation, publisher authenticity or production-grade transport confidentiality. |
| `plasmactl z2-ps` | Root CLI; install/deploy already routes through Bootstrap deployment coordinator and its journal | **REUSE** existing Coordinator; eventually expose as client of same API for routine upgrades. Keep local factory/root recovery separate. |
| SWPC `scripts/ppu-deploy` | Independently SSH-executes bounded Z2-side Python installer; separate SWPC/Z2 state, version, compensation and rollback for `wordport`, `openocd-integration`, `abtest` | **MIGRATE** all three to the same Bootstrap API and same Coordinator lock/journal. Current SSH path remains untouched until end-to-end feature parity and physical authority are proven. Do **not** claim it is already migrated. |
| `ppu_deploy_target.py` | Current engineering installer with pinning, root check, allowed paths and owner scan | **RETIRE LATER**, after reviewed replacement has exact file allowlist, atomic verified transaction, active-device exclusion and rollback, never by deleting its functioning security checks first. |
| `ppu-z2-installer.py` and `ppu-bootstrap-deployment.py` | Canonical PS-only installer and durable transaction core | **KEEP AS COMPONENTS**, not separately exposed normal installation authorities. Engineering modules cannot be passed into this PS-only installer today. |
| FPGA Image + Manifest install | No current unified installed Image + Manifest staging capability; protected Root only loads/tests/restores already installed approved files | **UNQUALIFIED**, explicitly reject for now. Add future paired Image + Manifest atomic deployment only after hardware qualification; retain Root/Golden. |
| Factory/bootstrap installer | Installs independent Bootstrap control plane for a missing/broken product Runtime | **KEEP offline** under Engineer/local maintenance, not an alternative routine authenticated network installation API. |

## This PR's actual source changes

1. `scripts/ppu_unified_deployment.py` introduces a **non-executing** typed deployment plan: exact `ppu-runtime`, `engineering-module` (exact three modules), `fpga-image`; exact source commit and archive SHA-256; the **same** Bootstrap endpoint, canonical Coordinator lock and journal. Engineering and FPGA kinds report `blocked-not-qualified`.
2. `scripts/ppu_deploy.py` `plan` now includes `unified_deployment` evidence with proposed common API and a **blocked** status; `deploy/verify/rollback/status` are intentionally **unchanged** and still use legacy engineering SSH. No remote call is made by `plan`.
3. The **existing** `scripts/ppu-bootstrap-service.py` `_deployment_request()` accepts absent or explicit `kind=ppu-runtime` for compatibility, strictly denies `engineering-module`, `fpga-image`, unknown kinds and caller-chosen fields. There is **no new HTTP endpoint**, and no path by which the PS-only Installer accidentally receives executable engineering code.
4. `software/python/tests/test_ppu_single_deployment_entry_gate1.py` proves on Host only: all three module identities, SHA, a common endpoint and lock/journal reference, unchanged PS Runtime deployment request, fail-closed unsupported installers, invalid Root/script selectors, and preserved Root/owner/rollback/factory contracts.

## Gate 1 continuation: shared transaction core + verified Engineering ZIP

The existing **`scripts/ppu-bootstrap-deployment.py`** now has an internal **`execute_engineering(EngineeringDeploymentRequest)`** Host-only execution path. It uses the **same `_deployment_lock()`, `Journal`, recovery classification and transaction record** as PS Runtime. It does **not** add a privileged daemon, a new API, a second lock, or a second journal. Three exact module names are permitted; unknown, symlink, malformed-source and changed-hash requests are rejected. A verified Host test fake demonstrates `wordport`, `openocd-integration` and `abtest` receipt; lock conflict, interrupted/recovery transactions, rollback-done and rollback-uncertain are explicitly tested. A confirmed engineering transaction is marked `engineering_active`, separate from `runtime_active` for accurate audit.

The **existing `scripts/ppu-z2-installer-core.py`** now includes `verify_engineering_package()` as a **read-only ZIP verifier** for the actual `ppu-deploy` bundle format, including exact payload allowlist, module-specific SWPC manifest, archive digest, per-file digest, source-commit *format* and package size limits. It returns `install_qualified=False`: **a matching SHA/source string is NOT proof of approved Git publisher provenance, protected executable trust or a device-side Master authorization**. The installed PS-only Core exposes **no `install_engineering_package()`**. The Coordinator therefore rejects normal engineering installation with `ENGINEERING_INSTALL_NOT_QUALIFIED` before any journal update. The current Bootstrap HTTP `POST /v1/deployments` also continues to reject engineering packages. No production Root code execution, installer activation or SWPC/Z2 update was enabled.

**Remaining blocking work**: ship and independently trust an immutable *on-device* installer capable of installing only a qualified Engineering Package; enforce active Console Master generation, approved publisher identity and Source Pin; verify real lock/quiescence; integrate SWPC's API upload/operation polling and two-host compensation/recovery. Only after those pass may the old SSH writer and duplicate engineering state be retired. The current Host-only `EngineeringInstallRolledBack` classification is **only a trusted installer contract**, not evidence of actual rollback on Z2.

**No claims of completed convergence:** Product deployment still operates through Bootstrap; engineering deployment still has independent SSH and local state. There are currently **two actual transaction implementations**; one is being retired only after replacement is safe and available. Merely sharing an endpoint string or a plan is not yet shared transactional locking. The current main still does not implement a trusted Master ownership generation service or an authenticated non-Root WordPort privileged helper. Gate 1 Host-only must **never** authorize `sudo`, arbitrary Python/argv, source pin replacement or FPGA programming.

## Host-only SWPC API transport continuation

The new **`scripts/ppu_deploy_api.py` is only an HTTPS CLIENT**, not another installer, privileged helper, server, auth platform, or API endpoint. It implements the exact pre-existing Bootstrap `/v1/uploads` create/chunk/commit protocol, `POST /v1/deployments` and `GET /v1/deployment`/status with fixed sizes, strict receipt IDs, SHA-256, progress confirmation, fail-closed ambiguous outcomes and **no silent retry** of writes. It enforces certificate-validated HTTPS, forbids embedded URL credentials, redirects and environment proxy credential leakage. An injected transport is used solely to test against the actual Bootstrap upload validation functions with synthetic archives; it is **not executed against SWPC or Z2**.

The existing Bootstrap API **reads the Coordinator's private `deployment.json` before queueing** a PS Runtime deployment: only an absent first-install journal or a structurally valid terminal safe state is admitted. Active/unknown/recovery-required, malformed, oversized, symlinked or over-permissive journals stop the request **before** `deployment-api.json` is replaced. The byte limit is enforced on raw UTF-8 bytes. This is a read-only early guard; the Coordinator still owns its original `flock` and authoritative admission under that lock. Host-only positive/negative tests cover the guard; no installed service was changed.

**Revised Gate 1: actual PS Runtime API↔Coordinator correlation in source.** The Bootstrap service generates its own non-caller-selectable 32-hex API transaction ID and passes it through the already-existing `ppu-bootstrap-kit.py` → `plasmactl z2-ps` → `ppu-bootstrap-deployment.py` path. The Coordinator records that exact ID **inside its existing `deployment.json` under the existing `deployment.lock`** as an audit-only field, alongside its independently generated Coordinator transaction ID. The API Worker now calls `_reconcile_runtime_result()` before marking a transaction succeeded: it requires a PASS Kit result, matching Release ID, `ppu-runtime` kind, `runtime_active` state, the **same exact API ID** and a Coordinator transaction ID different from the pre-admission journal. Any missing, stale, mismatched or ambiguous runner/journal result is `recovery_required` with no success receipt or blind retry. No second Lock, Journal, privileged route, HTTP endpoint or new installer is created. Legacy local `plasmactl z2-ps` calls remain valid without an API ID.

This is **code-path and Host-only test evidence**, not proof the updated Bootstrap/Kit binaries are installed or have executed on Z2. The API correlation tag is **not** a Master generation, Root grant, package signature, publisher attestation or durable cross-host commit record. API status remains a projection of the authoritative Coordinator PS Runtime transaction, not a second authority; actual restart/recovery, production TLS and SWPC/Z2 Engineering cross-host rollback qualification remain separate.

Existing `scripts/ppu-deploy` gains a **read-only** `api-status --api-url https://... --token-file PATH` mode with a caller-owned, regular non-symlink mode-0600 token file. No token appears on CLI arguments, printed responses or network-failure messages. This does not alter the existing `deploy/verify/rollback/status` behavior (which continues to use the legacy engineering SSH route until independently qualified). **Current Bootstrap Service still offers commissioning-only HTTP, not qualified HTTPS**: the new HTTPS client cannot be used on that existing endpoint without approved TLS termination/service and independent Master/publisher authorization. Do not use a fake TLS connection or HTTP downgrade to claim migration.

`BootstrapAPIClient.submit(kind="engineering-module")` and `submit(kind="fpga-image")` explicitly reject **before any request**. The HTTP server also rejects these kinds. Host-only protocol readiness does not qualify a Root on-device Installer, nor atomic SWPC + Z2 rollout. A future approved runtime migration must enforce active Master ownership at dispatch, approved bundle issuer/source, immutable protected Root Source Pin and Site/recovery checks, and only then migrate live engineering deployment and remove SSH write code.

## Required next integration acceptance before removing legacy paths

- **One production authority:** authenticate a real active Master (and validate revocation/generation at dispatch), bind PPU identity, use transport that meets deployment security requirements. Bootstrap commissioning token alone cannot stand in for this.
- **One transaction and journal:** adapt immutable and allowlisted engineering packages to existing Bootstrap upload/Coordinator, not a new Lock/Journal. Enforce source integrity and *publisher authenticity* independently, path confinement, protected Root code boundary, Site/FPGA quiescence and negative recovery cases. The target helper must be installed/reviewed and cannot be a client-supplied `python -c` under Root.
- **Dual-host lifecycle:** retain SWPC bundle version matching, idempotent retry, atomic activation, verify and bounded compensation/rollback including Z2 failure, and fail-closed `recovery_required` if one side's state is unknown. A multi-host transaction is not automatically atomic because both hosts have local locks.
- **No breaking cut-over:** only after Host-only source/CI plus separately approved real Z2/SWPC acceptance demonstrate `wordport`, `openocd-integration`, and `abtest` deploy/verify/rollback, switch SWPC CLI to API and remove SSH writer and its duplicate journal/rollback. Retain existing physical Root Guard, owner lock, Image/Manifest/Golden and Engineer factory recovery throughout.
- **FPGA Image install:** stage verified paired BIN+Manifest through the same future transaction; keep protected `download/test/restore` for live lifecycle. Do not disguise `download` as `install`.

## Owner-approved downstream acceptance batch: #1207 engineering modules after #1209 convergence (2026-10-29)

> **Plan-only / NOT_RUN.** The owner approved adding the already-merged #1207 engineering modules as the **first downstream deployment acceptance batch after** the #1209 unified entry is fully qualified. This does **not** expand the existing #1209 Host-only Gate 1, authorize live deployment or hardware operations, or make the engineering write API available. No generic C, arbitrary Python or FPGA Image installation is included.

### Dependency and release boundaries

1. **Source:** merged PR #1207 (merge commit `e338083564c30dc6bdc24009f7b62a3984fb7023`) provides exactly the three allowlisted `ppu-deploy` engineering module packages and optional Readback behavior. Treat it as a source dependency, **not** proof that its code has been installed on SWPC or Z2.
2. **Master boundary:** PR #1208 has since merged into `main` at `1fb0c4b6c95e9da8f746fc3571a160b5a8bf6390`, but its non-root/Master contract is Host-only. It is **not** active Master generation/revocation, publisher provenance, production Root authority or a trusted on-device installer.
3. **Convergence:** #1209 Gate 1 supplies the shared transaction contract, read-only package verifier, HTTPS client, exact **PS Runtime** API/Coordinator ID correlation in source and explicit engineering reject-only API admission. Actual engineering installation is still `ENGINEERING_INSTALL_NOT_QUALIFIED`; legacy SSH writing remains operational but **must not** be mistaken for successful unified-API cutover. The branch is synchronized with #1208 in `main`; recheck any newer `main` and exact-head CI before a separate Gate 2 decision.
4. **Future prerequisite work (outside current Gate 1):** owner-approved scope must separately qualify a trusted on-device engineering installer, authenticated/revocable active Master plus approved package publisher/source, certificate-verified Bootstrap HTTPS service, deployed/runtime-verified PS transaction receipts, and safe SWPC+Z2 cross-host compensation and rollback. Preserve protected Root, ownership/quiescence, FPGA Image/Manifest/Golden and factory recovery. Do not retire SSH before verified replacement parity and accepted real rollout.

### First deployment acceptance batch (only after prerequisites)

| Module | Exact #1207 scope | Future acceptance evidence |
| --- | --- | --- |
| `wordport` | Z2 PS WordPort Python engine/integration and SWPC WordPort client | Immutable package/source/file digests; both hosts report matching active version, successful single-API deploy/verify and bounded rollback receipts. |
| `openocd-integration` | Same reviewed Z2 WordPort/OpenOCD Python integration and SWPC client | Verify OpenOCD integration files, pinned OpenOCD binary/config identity **without replacing the executable**; matching cross-host transaction/receipt and rollback proof. |
| `abtest` | Shared Z2 Python integration plus SWPC A/B Runner | Verify Runner and engine versions on both hosts, manifest/source hashes, API activation/verify/rollback and CDC/Verify configuration contract; **no automatic flash cycle or DUT operation** as part of deployment acceptance. |

The three packages overlap on Z2 Python files, and `wordport`/`openocd-integration` share the SWPC engine file; `abtest` adds the SWPC Runner. Acceptance must prove compatibility and version consistency across this overlap, **not** assume three independently isolated installs or silently overwrite newer shared files.

### Release/acceptance stop criteria (future, separately authorized Gate 1)

- **Preflight:** exact approved `main`/source commit, signed or independently authenticated publisher, package SHA-256 and per-file hashes, approved module name/paths, current SWPC/Z2 installed version, Z2 Boot ID, active Master generation, HTTPS service identity, lock/quiescence, and real rollback resources all recorded. Ensure unchanged pinned OpenOCD/config, Native C bridge and paired FPGA Image/Manifest; these are checked, **not** deployed by this batch.
- **Positive:** one Bootstrap `POST /v1/deployments` admission per selected module using the existing Coordinator lock/journal; correlate API and Coordinator transaction IDs and observed on-host activation. Collect immutable before/after SWPC and Z2 receipts and status; verify each exact file SHA, source commit, archive hash and same active bundle version; confirm repeat submission is safe/idempotent.
- **Negative/recovery:** reject unknown module, path/symlink/manifest tampering, mismatched hash/publisher, stale/revoked Master, invalid TLS, active owner/busy hardware, API↔Coordinator ID disagreement, mismatched SWPC/Z2 versions and in-flight/unknown journal. Exercise approved non-hardware failure injection for Z2/SWPC activation and verified rollback on both hosts; stop in explicit `recovery_required` when restoration cannot be proven. No blind retry.
- **Evidence:** archive exact branch/main/Installer/Coordinator/engine/Stage SHAs, source and package digests, client/server request + journal transaction IDs, Master/publisher attestation (without secrets), pre/post state, real exit and rollback outcomes; label PASS/FAIL/NOT_RUN separately for each module and negative case.
- **Hardware boundary:** earlier #1206 evidence records 100 physical A/B pairs for an earlier software SHA; it does **not** qualify the new #1207/#1209 deployed stack. New Flash, FPGA, CDC or DUT execution is **NOT_RUN** until explicitly included in a future owner-approved hardware acceptance scope. Host-only CI is not physical evidence.
- **Cutover:** only after independent review of all three module receipts, fail-closed negatives, cross-host recovery, required GitHub CI and owner-authorized live acceptance may SWPC switch from legacy SSH to unified API. No source changes, deployment, merge or hardware operation are authorized by this plan update.

## Gate 1 / Gate 2 boundaries

This PR changes Host-only planning, the existing API's **reject-only** Engineering admission, PS Runtime transaction-ID correlation in source, and documentation/tests. It does **not** perform deployment, add any Root capability, change installed Z2 permissions, make a live SWPC/Z2 request, operate SWPC/Z2/FPGA/DUT, or retire a live engineering path. Any actual migration of protected runtime, on-device Owner claims and production Master authorization still requires evidence beyond GitHub-hosted tests.
