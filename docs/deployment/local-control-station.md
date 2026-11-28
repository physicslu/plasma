# Local Control Station Reference Deployment

## Status

`local-control-station` is the Linux reference deployment for the Plasma **upper computer / Control Station** role.

It deploys the same Control Station product code used by the managed Render lane. It is not a second implementation of Programming workflows or APIs.

```text
Browser
  |
  v
Control Station Console/BFF  127.0.0.1:18190
  |
  v
Plasma Manager               127.0.0.1:18280
  |                    \
  v                     v
Configured PPU          Built-in Mock PPU mock-ppu-01 (default on)
Plasma Gateway          127.0.80.1: Gateway 18080, Bootstrap 18081, Runtime 18082
```

The Physical PPU is a separate deployment role. The profile never starts a
physical PPU runtime, FPGA/PL runtime or Engineering Mock Provider.

## Built-in Mock PPU

Owner Product Decision 2026-11-28, Gate 1 D1-D7. The profile installs
`plasma-mock-ppu.service` (user systemd, enabled and started by default):

```text
plasma-mock-ppu.service
  -> <current>/venv/bin/python -m plasma_server.mock_ppu serve
       --root ~/.local/state/plasma/local-control-station/mock-ppu
       --control-plane <current>/ppu-control-plane
       --alias mock-ppu-01 --sites 8 --manager-url http://127.0.0.1:18280
     ├── plasma_server.runtime_server   (8 Mock Sites, Virtual Flash)
     ├── ppu-bootstrap-service.py serve (enrollment, B1/B2/B3, G13 admission socket)
     └── plasma_web.gateway_phase3      (Plasma Gateway)
```

- **Same PPU boundary (D1).** Three real PPU processes; the Manager uses its
  normal registry, ticket enrollment, G13-signed writes, Resource Reservation
  and Batch Engine. Nothing is added to the Manager or the Scheduler.
- **Stable identity.** The device root keeps its machine identity, Bootstrap
  controller state and Active Set across restarts; a restart reuses the
  existing enrollment. The launcher's Engineering ticket is armed only while
  UNENROLLED and only on a device whose 0600 package target says
  `platform: mock` (`ppu-bootstrap-service.py --mock-enrollment-ticket-file`).
  To re-enroll a Mock, stop the service and remove its root.
- **Registration.** The launcher adds `mock-ppu-01` to the Manager registry
  (loopback API), commissions it once the Manager observes it, and enrolls it
  with its one-time ticket, which is then deleted. It refuses an alias that
  already belongs to another endpoint. The Console's fixed Physical alias
  (`--ppu-alias`) is unchanged and `mock-ppu-01` is reserved (D6).
- **Isolation (D3/D4).** The Manager classifies each enrolled PPU from its MACed
  Bootstrap status, refuses Mock/non-Mock mixed Batches before any PPU is read
  or reserved, resolves `data/opf/programming-routes/mock-site-simulated.json`
  only for Mock Batches, and records `ppu_class` on every Batch. The Console
  shows `MOCK` on the PPU, the KPIs (`MOCK YIELD`, ...) and `[STATISTICS]` lines.
- **Opt-out (D7).** `plasmactl install|deploy local-control-station --no-mock-ppu`
  removes and disables the unit; `--mock-ppu` re-enables it. The choice is
  persisted in `profile.env` (`PLASMA_LOCAL_CONTROL_STATION_MOCK_PPU`).
- **No repository at runtime.** The Mock runs from the release venv and the
  release's `ppu-control-plane/` (built with the same `_build_control_plane`
  as the PPU Runtime release); it needs no Git, Playwright or CI fixture.
- **Platform.** Linux only. Its Runtime control socket and G13 admission rely on
  Linux Unix-socket peer credentials (`SO_PEERCRED`) and 0600 socket files;
  macOS/Windows are deferred (TODO register).

## Why this profile exists

Plasma needs one Control Station codebase that can be exercised in several environments:

```text
Render demo                    -> same product code + Mock lane
Render z2like demo             -> same product code + Manager -> SWPC PPU
Linux local-control-station    -> same product code + local Manager -> configured PPU
macOS package pilot            -> same product/runtime contract
Windows package pilot          -> same product/runtime contract
```

These are deployment/package variants, not duplicated feature implementations.

## Linux reference ownership

The Linux reference implementation uses **user systemd**. Platform packages use their native service managers while preserving the same product contract.

Runtime state is separated from the Git worktree:

```text
~/.config/plasma/local-control-station/
  profile.env
  manager.yaml

~/.local/state/plasma/local-control-station/
  install.json
  manager-observations.sqlite3
  registry.json                  # Manager runtime PPU registry (created by Manager)
  bootstrap-credentials.json     # Manager Bootstrap pairing state (created on pairing)

~/.local/share/plasma/local-control-station/
  current -> releases/<git-sha-prefix>
  releases/<git-sha-prefix>/
    venv/
    web/
    catalog/          # committed data/ + release/ trees for the Manager Device Selector
```

User units:

```text
plasma-local-manager.service
plasma-control-station.service
```

The Console and Manager bind to loopback only. Public/LAN exposure is not created by this profile.

## Manager runtime (OPF S5)

The profile Manager runs `python -m plasma_manager.bootstrap_server`, the same Bootstrap-capable Manager entrypoint used by the packaged Control Station runtime. It composes the standard `plasma_manager.server` behavior with the PPU Bootstrap routes (`/api/registry/{alias}/bootstrap/...`) the Console uses for Platform Release Bundle admission and install.

The Manager owns the Catalog-only Device Selector (`GET /api/devices/search`, reached by the Console at `/api/manager/devices/search`). The release venv is a non-editable install and cannot locate repository data, so each immutable release ships the **committed** `data/` and `release/` trees (`git archive HEAD`, no EOL conversion) under `releases/<sha>/catalog/`. The Manager unit sets `PLASMA_DEVICE_CATALOG_MANIFEST`, `PLASMA_IC_SUPPORT_ROOT` and `PLASMA_RUNTIME_EVIDENCE_ROOT` to that release Catalog. A release build fails before activation unless the release's own venv answers a Selector self-test with HTTP 200 from those bytes.

`manager.yaml` sets `manager.registry_state_path` to `~/.local/state/plasma/local-control-station/registry.json`. This is an explicit profile decision (owner-approved PR-L1) that makes the Manager runtime registry durable and mutable, which Validate & Enable, Bootstrap pairing and Static IPv4 commissioning require. The `ppus` list written to `manager.yaml` only **seeds the first start**; once `registry.json` exists it is the Manager-owned inventory, and later `--ppu-alias`/`--ppu-endpoint` changes do not rewrite it. Activation rollback never deletes `registry.json` or `bootstrap-credentials.json`.

Releases built before this contract have no `catalog/` directory. Re-activating such a SHA with the current script is refused; roll back with the script from that older clean checkout.

## Manager IC Selector SQLite-only cutover (Catalog Database v1)

The Manager-owned `GET /api/devices/search` (and Console BFF
`GET /api/manager/devices/search`) reads **only the active, complete
SQLite Catalog/Qualification revision** selected by `PLASMA_CATALOG_SQLITE_DB`.
The legacy Manifest and Programming Qualification registry are **not**
alternative runtime Selector authorities. Missing configuration, missing
SQLite file, invalid revision, incomplete qualification or integrity failure
returns `503 DEVICE_SELECTOR_UNAVAILABLE`, never empty success or implicit
re-import. Invalid query arguments still return 400; L0 remains internal,
L1–L3 are customer-visible, and standard Job selection remains L2/L3.

For the Linux `local-control-station` profile, the persistent Manager database
defaults to `~/.local/state/plasma/local-control-station/catalog.sqlite3`.
Set `PLASMA_LOCAL_CONTROL_STATION_CATALOG_DB` to an **existing** qualified
database path when the Controller Catalog is already provisioned elsewhere.
The canonical deployment self-test checks this exact database **before
activation**; it must not reset, replace, or seed an existing published
revision. The Manager user-systemd unit binds
`PLASMA_CATALOG_SQLITE_DB` to that database. Platform launchers use
their corresponding persistent user-state / ProgramData Catalog path, with
`PLASMA_CATALOG_SQLITE_DB` as an explicit override. Provision data separately.

Initial provisioning is an **offline, owner-authorized data operation**, not
a Selector read fallback. In a clean, trusted offline environment, with the
manifest, IC Support and source/evidence roots configured for the SAME
verified Catalog revision, use the existing publisher CLI to create a
qualified database in a **new** destination:

```bash
python3 -m plasma_web.catalog_sqlite_repository \
  --db /trusted/manager-state/catalog.sqlite3 \
  --manifest /trusted/data/device-catalog/production/icpn-v1-manifest.json \
  --with-qualification
```

Verify the complete qualification count, active revision, L0 exclusion and
customer search through the Manager endpoint before changing a running
deployment. **Do not invoke this initial importer against an existing
published SQLite database** simply because the software version changed.
Later Catalog revisions are published through the versioned, transactional
SQLite Publisher; keep source Manifest, manufacturer evidence and qualification
import tools as offline acquisition/provenance inputs. Do not mistake the
legacy source-dependent *optional display metadata* for Canonical Catalog
identity or an admission authority. Selector availability does not decide
already-admitted PPU Jobs.

**Customer-owned IC preservation is a hard upgrade invariant.**
Local Exact ICPNs and custom Profiles reside in
`controller_overlays(namespace='user_catalog')`, outside immutable Official
Catalog revisions. Official data upgrades must use the existing transactional
Publisher against the same persistent SQLite file; they must **not** replace,
copy over, delete, or reinitialize that file with a prebuilt Official-only DB.
Before and after a data update, validate exact local record/profile content,
record counts, revisions, and visibility independently from Official row counts.
Official Catalog and customer Local records may legitimately have the **same**
`(manufacturer, exact_icpn)` in distinct SQLite namespaces. An Official
Publisher update must not block, overwrite, promote or hide customer data.
The IC Selector and IC Management explicitly distinguish **OFFICIAL IC**
(authoritative published identity and Qualification) from **CUSTOMER IC**
(customer-owned, UNVERIFIED). An identical Exact ICPN does not by itself
establish that the customer Profile has been reviewed or granted hardware
execution authority.

If the customer confirms that the two records describe the **same physical
IC**, the authorized `POST /api/catalog/management/link-local-official`
operation requires an exact published Official identity, the current customer
Local revision and `confirmed_same_ic=true`. In a single `BEGIN IMMEDIATE`
transaction it moves the entire Local record and Profile to
`controller_overlays(namespace='official_profile_link')` and writes a
`LOCAL_LINK_OFFICIAL` Audit event containing the original content digest.
The stored Profile remains customer-owned and `UNVERIFIED`, with no
Qualification / Job admission promotion; the Official identity and Level
always come from the active Official revision. After a later Official rollback
removes the identity, the link is `PENDING_OFFICIAL`, the customer Profile
persists and is visibly not an Official IC until re-publication.

IC Management provides a checkbox for explicit physical-identity confirmation,
a Link button and a separate **OFFICIAL IC · CUSTOMER PROFILE** list. It
must not silently equate same-name records, auto-link customer Profiles, or
invent another manufacturer Exact ICPN. If the Local identity was truly wrong,
a separately authorized correction remains necessary; normal Official updates
must remain non-destructive for both namespaces.
Use SQLite online backup or equivalent consistent snapshot for recovery;
copying just the live `.sqlite3` file without its WAL is not safe.

This Gate 1 changes runtime read semantics and deployment contracts, **not**
an existing SWPC installation or persistent Catalog. Production cutover must
first establish the real Manager database path and backup/rollback eligibility;
a GitHub-hosted Mock is not evidence of a successful SWPC migration.

## PPU target contract

The target is configured explicitly and is not hard-coded to SWPC or PYNQ-Z2.

Accepted endpoint form:

```text
http://HOST[:PORT]
https://HOST[:PORT]
```

The value must identify the **full Plasma Gateway root used for managed control**, not a narrower diagnostics/status proxy. Embedded credentials, query strings, fragments, and nested paths are rejected.

Examples:

```text
SWPC co-resident Z2-like full local Gateway
http://127.0.0.1:18080

Real Z2 on a trusted local network
http://192.168.10.21:18080
```

The former SWPC host `127.0.0.1:18081` diagnostics/status ingress was retired by Issue #549 and must remain unused. It is not a valid Local Control Station PPU endpoint. Port `18081` remains architecturally valid only as the independent Bootstrap/recovery service on real Z2 and inside the private QEMU simulated-Z2 target.

The Manager/BFF target alias is fixed by deployment configuration. Browser selection does not rewrite the backend target.

## Install

First install requires an explicit PPU endpoint:

```bash
./scripts/plasmactl install local-control-station \
  --ppu-alias swpc-ppu \
  --ppu-endpoint http://127.0.0.1:18080
```

Optional overrides:

```text
--python PATH
--ppu-alias ALIAS
--ppu-endpoint URL
--console-port PORT
--manager-port PORT
```

Default local ports:

```text
Console/BFF  127.0.0.1:18190
Manager      127.0.0.1:18280
```

These are intentional `local-control-station` profile defaults, not replacements for the generic/package Manager default `18180`. See `docs/deployment/port-profile-matrix.md` for the canonical cross-profile map.

`install` builds an immutable release, writes profile configuration and user-systemd units, and enables the units. It does not start them.

## Engineering deploy preflight (SWPC)

Before constructing a release, and **again immediately before changing the active
release**, `plasmactl deploy local-control-station` runs the read-only
`scripts/plasma_cs_deploy_preflight.py`:

- checks legacy/v2 Manager Batch journals and the Run/Start journal without
  modifying or deleting evidence;
- resolves their location from `manager.yaml`'s explicit absolute
  `manager.registry_state_path`, which must match this profile's state directory;
  the journals are siblings of the registry (as in `bootstrap_server.py`);
- requires the base Batch journal and Run/Start journal, including an explicit
  `starts` list. A missing ledger is unverified history, not definite idle or
  proof of a new installation. The optional `.v2` sidecar is read when present;
- blocks an active, unresolved or `OUTCOME_UNKNOWN` attempt or Run;
- validates known terminal outcomes, execution states, transaction identities,
  duplicates and migrated v1/v2 agreement; a Run with unknown outcome requires
  an explicit boolean acknowledgement;
- reconciles every recorded Start through the live Manager GET endpoint:
  consumed Starts must match their terminal transaction, and issued/voided
  Starts must prove `NOT_ACCEPTED`. A live `JOURNAL_INCONSISTENT` blocks even
  when local Batch rows say PASS;
- requires local Manager health and an observable, idle PPU execution owner
  (`GET /api/status`: no busy owner, no active Job);
- fails closed when journal data is unreadable or PPU execution cannot be
  observed. It does **not** retry, stop or resubmit Jobs.

This gate protects against deployment with a job already in flight. It is **not
an atomic Manager admission barrier**: a concurrent operator could start a new
Batch after the final snapshot. A true quiesce/maintenance transaction must be
implemented before claiming race-free unattended or factory deployment.
SWPC HIL programming is separately controlled and does not implicitly run from
`deploy`. GitHub PR CI does not run any physical programming.

The preflight runs with the active release's venv (including Manager's YAML
parser). It never constructs a workflow/coordinator, rewrites journals,
acknowledges unknown outcomes, voids Starts or retries a Job. A stopped v2
Batch can contain never-submitted `SKIPPED` Sites with no attempts; its
aggregate outcome must still match the Manager's rule.

For an owner work order requiring exclusive maintenance with no new Manager
admission, two passing snapshots alone are insufficient. Verify that condition
through the existing operational controls before deploying; otherwise report
deployment `NOT_RUN`. This preflight does not supply a maintenance lock.

## Development-mode clean State cutover (Replace, Not Migrate)

For the single-owner development laboratory, use **one explicit opt-in** to
replace the active Control Station's transaction state with a new empty
namespace while retaining Manager pairing. It does **not** convert historical
v1/v2 Journals, copy old transactions as live admission evidence,
or silently acknowledge UNKNOWN outcomes.

```bash
# Only in an approved, clean, committed Control Station source checkout on SWPC.
# No currently executing programming Jobs; no new Console/Manager admission
# during cutover. Never operate a DUT or Z2 runtime from this command.
./scripts/plasmactl deploy local-control-station --dev-fresh-state
./scripts/plasmactl verify local-control-station
./scripts/plasmactl status local-control-station
```

This is a **destructive-to-active-development-state** operation, not a
production upgrade. It preserves all old data without deletion, by moving the
entire existing `~/.local/state/plasma/local-control-station` directory to
a timestamped `local-control-station.archive.*` sibling. Only after the
Console and Manager services are stopped, with PPU execution still observed
idle, is a new State directory created. Old Journals remain only in the
archive. Existing `registry.json` and `bootstrap-credentials.json` are copied
unchanged into the new State, preserving the paired Device ID, Controller ID,
generation and credential; absent files remain absent for an unpaired install.
The Manager uses the configured PPU seed only when no Registry file exists.

The immutable new release is constructed **before** stopping the services.
The CLI checks the configured PPU's read-only `GET /api/status` before
build, after build and again after the two SWPC user services stop. Each
check requires `busy=false`, `active_job_count=0`, and empty execution
owner identity. An unavailable PPU, any active Job or unknown owner is
BLOCKED. Stopping the local Manager closes the managed admission entrypoint;
it does not block a separate external operator with direct PPU access, which
remains outside this single-owner development profile.

The CLI preserves old release/config/systemd artifacts and performs its
existing post-activation verification. On a command error it restores the
prior release, config and archived State, then restarts the original services.
Any partially created new State is saved as
`local-control-station.failed.*` for diagnosis. An abrupt power loss or
`SIGKILL` during the rename is **not** a proved automatic rollback; inspect
the archived state, installed SHA and user units before recovery. No
unattended fleet/production migration claim is made.

**Default `deploy` (without the flag) remains the strict, transaction-aware
deployment path.** `--dev-fresh-state` is not accepted by install, verify
or status. The flag never changes PPU/Z2 firmware, FPGA, Site or DUT power.

## Deploy

```bash
./scripts/plasmactl deploy local-control-station
```

The profile activates the repository's **current clean committed HEAD**. It does not run `git pull`, merge, checkout, reset, or other source-control mutation. The source may be a primary clone or a linked `git worktree`; either must be clean.

Deployment flow:

```text
clean committed source
        |
        v
build/reuse immutable release
        |
        v
write Manager target + Console/BFF units
        |
        v
switch current release
        |
        v
restart local Manager
        |
        v
restart Console/BFF
        |
        v
local runtime verification
        |
        +-- PASS -> keep activation
        |
        +-- FAIL -> restore previous release/config/units
```

An unreachable PPU does **not** invalidate the Control Station deployment itself. PPU reachability is reported separately because:

```text
Control Station readiness != PPU readiness != Programming readiness
```

However, if the configured PPU is reachable and `/api/health/live` succeeds while `/api/settings/sites` is unavailable, verification fails closed. That condition proves the configured endpoint is not the managed-control Gateway surface, which is a deployment configuration error rather than temporary PPU unavailability.

## Verification

```bash
./scripts/plasmactl verify local-control-station
```

This verifies:

- install evidence and active immutable release agree;
- both user-systemd units are Plasma-owned and active;
- Console is in managed mode;
- Console BFF points to the local Manager;
- fixed PPU alias is injected into the BFF;
- the Manager unit runs `plasma_manager.bootstrap_server` and points at the release Device Selector Catalog;
- `manager.yaml` declares the profile runtime registry state path;
- Manager liveness passes on loopback;
- Manager `GET /api/devices/search` returns HTTP 200 on loopback (Manager-owned Catalog, never relayed to a PPU);
- Console root responds on loopback;
- a reachable configured PPU exposes the managed Site configuration surface rather than only a restricted diagnostics/status surface.

The configured PPU `/api/health/live` is probed as additional evidence. An unreachable target remains non-fatal for **Control Station deployment qualification**, but a reachable target with an incompatible managed-control surface fails configuration verification.

It does not prove:

```text
PPU execution readiness
PYNQ-Z2 / ARM qualification
PS <-> PL integration
FPGA behavior
Site electrical behavior
real IC erase/program/verify
8-Site hardware concurrency
```

Those are separate target/hardware acceptance layers.

## `plasma.open4th.com` role

When the SWPC local-control-station runtime is intentionally exposed through the existing tunnel, the routing role is:

```text
plasma.open4th.com
  -> Cloudflare Tunnel
  -> SWPC 127.0.0.1:18190
  -> Local Control Station Console/BFF
```

The tunnel should point at the loopback Console. The profile itself must not bind the Console publicly or open a firewall port.

## macOS / Windows

`plasmactl local-control-station` is **not** the macOS or Windows installer.

The existing macOS/Windows package pilots preserve the same logical runtime contract:

```text
Control Station Console/BFF
        |
        v
Manager
        |
        v
PPU API
```

Only packaging/service integration changes by OS. Product features, Programming workflows, Manager contract, and PPU API remain shared.

## Real Z2 qualification profiles

Real hardware is a separate deployment family:

```text
z2-ps      implemented Real Z2 PS-only deployment/qualification profile
z2-full    future PS + PL + Site/Programming qualification
z2         intentionally unavailable until z2-full is qualified
```

`z2-ps` being implemented does not mean the current revision is qualified on a real board; real-board install/readiness/PS-loopback evidence remains a separate acceptance step. `swpc-z2like` must never be silently aliased to any Real Z2 profile.
