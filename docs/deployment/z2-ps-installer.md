# PYNQ-Z2 PS Release Kit and Managed Acceptance

> **Start here:** [PPU deployment start page](ppu-deployment-start-here.md) defines the two PPU deployment routes; the `z2-ps` release-kit installer is the internal executor of Route A (product deployment), not a separate route.

Status: **PS-only release-kit implementation with P3 controlled Site Desired runtime activation wiring; every deployment candidate still requires real Z2 qualification**

> **Scope and authority:** This document describes the Z2 **PS release-kit and managed acceptance** path, not blanket authorization for production deployment or physical DUT/FPGA operations. The currently approved deployment mechanism and credentials must be verified against the active PPU Deployment Engine and root [AGENTS.md](../../AGENTS.md); any SSH-based diagnostic or installation examples here do not establish SSH as a required production deployment transport. Preserve the separately approved Factory Recovery boundary.

## Purpose

The Z2 PS deployment path turns a clean PYNQ-Z2 image into a Plasma PPU PS node without compiling Plasma or CPython on the board.

```text
GitHub Actions
  -> build qualified ARMv7 Plasma Python candidate
  -> build pinned OpenOCD 0.12.0 runtime candidates (x86_64 + ARMv7)
  -> build canonical ppu/linux/armv7l release
  -> assemble source-tree-independent Z2 PS kit
  -> Actions artifact

Clean PYNQ-Z2
  -> verify/install Plasma-owned Python below /opt/plasma/python
  -> verify/install immutable PPU release
  -> systemd Server + Gateway + bounded runtime-activation helper
  -> local read-only readiness (GET only: health + G13 challenge bound to this Bootstrap)
  -> Manager signed PS loopback (controller-authorized, G13)
  -> Control Station Add PPU / Validate & Enable
  -> Save Site Desired
  -> controlled Runtime Activation when required
```

The PS profile does **not** load an FPGA bitstream, access PL, change target power, or program a real IC merely by deploying or activating configuration.

## Evidence boundary

A clean separation remains mandatory:

```text
GitHub CI = source / package / software validation
Real Z2   = install / systemd-DAC / runtime / physical-host validation
```

A CI PASS must never be reported as a Real Z2 PASS.

> **Verification checkpoint:** The examples below include `scripts/plasmactl install z2-ps` / `deploy z2-ps` and describe release-kit behavior. Before treating them as current operator instructions, reconcile those exact commands against the active `scripts/plasmactl` implementation and PPU Deployment Engine transaction/rollback tests. Until verified, this document is a PS release-kit reference, not proof of the current SWPC→PPU production transport.

> **Source-backed CLI clarification (Gate 1):** `scripts/plasmactl` dispatches the `z2-ps` profile to `scripts/plasmactl-z2-ps`; the backend implements `install`, `deploy`, `verify`, and `status` commands. This confirms the documented **local Z2 PS release-kit CLI exists**, but does **not** prove the newer single SWPC→PPU Deployment Engine has replaced every legacy SSH engineering path. The separate [unified deployment Gate 1 contract](../architecture/ppu-unified-deployment-gate1.md) explicitly records partial Host-only convergence and a remaining on-device installer gap. Keep these two lifecycle claims separate until independently qualified.

## Release identity and Python ownership

PPU Release Identity v2 remains mandatory:

```text
product_version = <product version>
full git_sha    = <40-character Plasma source SHA>
release_id      = <version>-<first-12-git-sha>
artifact_sha256 = <exact PPU archive digest>
```

The Plasma Python artifact has a separate runtime identity and lives only below:

```text
/opt/plasma/python/<version>/
```

OpenOCD is also packaged as an independent, versioned Programming Engine runtime:

```text
/opt/plasma/programming-engines/openocd/<openocd-runtime-id>/
```

The current pinned runtime is OpenOCD 0.12.0 at upstream commit
`9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c`. Its artifact carries the OpenOCD
binary, the matching `share/openocd/scripts` tree, internal/detached SHA-256
evidence, ELF architecture identity and shared-library dependency evidence. The development
build explicitly enables the OpenOCD `linuxgpiod` bit-bang adapter using
Ubuntu 22.04 `libgpiod-dev` (libgpiod 1.x API). The installed binary depends
on the OS-provided `libgpiod2` shared library; the **Z2 host must provide it**
before Console deployment. CI runs `adapter list` on both x86_64 and ARMv7
packages and refuses a candidate without `linuxgpiod`.

For the single-Z2 development baseline, refresh the factory Bootstrap once
using the procedure in
[PPU Bootstrap Factory Provisioning and Z2 HIL](ppu-bootstrap-factory-and-hil.md).
Then use the existing Console update path; no legacy Bootstrap compatibility
shim is maintained. This adapter availability is **software-only evidence**,
not proof that the EMIO GPIO routing, SWDIO turnaround, reset, voltages or
physical target programming work.

This packaging milestone does **not** start an OpenOCD service and does not enable
the production programming route. The runtime manifest and install evidence keep
`hardware_runtime_ready=false`. Tcl RPC lifecycle, Site workers, SWD/JTAG,
target power/reset and real-IC qualification remain later gates.

PYNQ continues to own System Python. Bootstrap tooling remains Python-3.10-compatible; Plasma Server, Gateway and helper use the isolated Plasma interpreter and never replace `/usr/bin/python3` or the PYNQ venv.

## Verified OpenOCD build cache (CI only)

The Z2 PS release workflow caches the *build archive and detached SHA-256 sidecar*
for both `x86_64` and `armv7l` independently. The exact cache key is derived
from `release/openocd.json` (fixed OpenOCD source/commit), the build recipe
`scripts/build-openocd-runtime.sh`, the artifact implementation
`scripts/openocd-runtime.py`, the architecture, Ubuntu 22.04 baseline and
the explicit `OPENOCD_TOOLCHAIN_EPOCH`. No loose `restore-keys` are used.

The cache is a **build optimization**, not a new trust or deployment boundary:

- Every hit and miss must pass the existing independent archive and detached
  SHA-256 verifier; the Host real-Tcl-RPC test and the fresh matching
  Ubuntu 22.04 install/runtime smoke also run unconditionally.
- Only a successful `main` push or manual `main` workflow can write a cache,
  after complete verification and runtime smoke. PRs can restore but do not
  publish cache entries.
- Every workflow run still uploads its own verified OpenOCD runtime artifact,
  and the PPU kit still consumes that run's artifact by GitHub Actions identity,
  **not directly from a shared cache**.
- `OPENOCD_TOOLCHAIN_EPOCH` is an **explicit invalidation control**, not
  automatic detection of external apt/image updates. Ubuntu 22.04 base tags and
  `apt-get` dependencies are not hermetically pinned at present. Maintainers
  MUST bump this epoch after toolchain, package, image or dependency-policy
  changes; for cryptographic reproducibility, a later improvement should pin
  the image digest and package snapshot. Do not infer that a cache hit
  reproduces a newer floating toolchain.
- Cache hit still proves only software build/package/runtime smoke. It never
  grants FPGA SWD, target power/reset, actual MCU programming or
  `hardware_runtime_ready=true`.

## GitHub-built Z2 PS kit

Workflow:

```text
.github/workflows/z2-ps-release.yml
```

Actions artifact:

```text
plasma-z2-ps-kit-<release-id>
```

After extraction:

```text
plasma-z2-ps-kit-<release-id>/
├── SHA256SUMS
├── scripts/
│   ├── plasmactl
│   ├── plasmactl-z2-ps
│   ├── ppu-z2-installer.py
│   ├── ppu-z2-installer-core.py
│   ├── z2-python-runtime.py
│   └── openocd-runtime.py
├── artifacts/
│   ├── plasma-python-<version>-linux-armv7l.tar.gz
│   ├── plasma-python-<version>-linux-armv7l.tar.gz.sha256
│   ├── plasma-openocd-<runtime-id>-linux-armv7l.tar.gz
│   ├── plasma-openocd-<runtime-id>-linux-armv7l.tar.gz.sha256
│   ├── plasma-ppu-<release-id>-linux-armv7l.tar.gz
│   └── plasma-ppu-<release-id>-linux-armv7l.tar.gz.sha256
└── docs/
    └── README.md
```

The P3 installer is intentionally a **two-file bootstrap unit**. `ppu-z2-installer.py` is the P3 wrapper; `ppu-z2-installer-core.py` retains the audited P2 release verification and installation core. The kit is invalid if either file is missing. CI compiles both under Python 3.10, includes both in `SHA256SUMS`, and executes the extracted wrapper with its extracted sibling core.

The Z2 does not need Git, npm, Node.js, Vite, a Plasma source checkout, a compiler, or a local CPython build to consume this kit.

## PPU release verification before mutation

The installer boundary verifies at least:

1. detached PPU archive SHA-256;
2. safe canonical `tar.gz` structure under `plasma-release/`;
3. regular files/directories only and safe extraction limits;
4. exact internal `SHA256SUMS` file set and digests;
5. full source identity and `ppu/linux/armv7l` target;
6. PPU runtime identity (no Device Catalog / IC Support is required; a legacy release that still ships them is tolerated, never required);
7. closed hardware boundary;
8. explicit Plasma-owned ARMv7 final Python >=3.11;
9. Server/Gateway canonical configuration identity;
10. the bundled same-commit control plane (`runtime/control-plane/`, PR-B Full-Copy): exact file set and SHA-256 from `control-plane-manifest.json`, the required Bootstrap / Site Worker / Adapter files, and one Site Worker protocol shared by the Runtime client (`plasma_interfaces/site_worker_c3.py`) and the bundled Worker (`ppu_site_worker.py`, currently `plasma.ppu.site-worker.v3`);
11. the bundled Adapter driver ABI against the selected engine (`/etc/plasma/site-worker-engine.json`), when one is selected.

A release without the control plane (`RELEASE_CONTROL_PLANE_MISSING`), with a Runtime/Worker protocol split (`RELEASE_SITE_WORKER_PROTOCOL_MISMATCH`) or with an unsupported Adapter ABI (`SITE_ADAPTER_ABI_INCOMPATIBLE`) ends `verify_failed` before anything is mutated.

P3 packaging separately verifies the wrapper/core bootstrap pair instead of assuming the repository source tree will be present on the appliance.

## Filesystem and service boundary

```text
/opt/plasma/
├── python/<python-version>/
├── programming-engines/openocd/<openocd-runtime-id>/
├── releases/<release-id>/
├── current -> releases/<release-id>/
└── install/
    ├── python-runtime.json
    ├── openocd-runtime.json
    └── last-install.json

/etc/plasma/ppu.yaml
/var/lib/plasma/
/var/log/plasma/
/etc/systemd/system/plasma-server.service
/etc/systemd/system/plasma-runtime-activation.service
/etc/systemd/system/plasma-web.service
```

Canonical configuration ownership remains:

```text
/etc/plasma           root:plasma   0770
/etc/plasma/ppu.yaml  plasma:plasma 0640
```

Plasma Server can read the canonical configuration but has no configuration-root write boundary. Plasma Gateway retains the narrow `/etc/plasma` write boundary required for same-directory temporary-file creation plus atomic `os.replace` when persisting Site Desired state.

P3 adds a root runtime-activation helper, but not a generic root control service. Its contract is intentionally narrow:

```text
transport      local AF_UNIX only
request        restart_server + expected ppu_id + bounded quiesce TTL
allowed target plasma-server.service only
shell          none
arbitrary unit none
filesystem API none
```

The helper is `PartOf=plasma-web.service`; Gateway `Requires=` it. It is not independently enabled after the deployment transaction, avoiding a post-commit helper-enable failure that could otherwise leave a partially activated release.

## First install versus upgrade

A first install creates every supported Site, **disabled**:

```yaml
server:
  max_supported_sites: 8

sites:
  - {id: 1, enabled: false, interface: "mock"}
  # ... through id: 8
```

The Gateway Site desired-state path (`POST /api/settings/sites/{id}` with a
strong `If-Match` ETag, then runtime activation) edits **existing** Sites
only, so every Site the PPU supports must exist in the canonical file. A
disabled Site executes nothing; `site_id` stays one-based and `SITE0` remains
invalid.

An **upgrade is different**. Existing `/etc/plasma/ppu.yaml` is persisted product state and may contain operator-approved Site Desired records. P3 therefore preserves the existing canonical file. The single exception is a one-time migration: a file whose only Site list is the exact former first-install line `sites: []` gets that line replaced by the disabled default Sites above (evidence: `site_desired_state.empty_sites_migrated_to_defaults`). Any other Site list is preserved byte for byte.

An upgrade also **restarts** `plasma-server.service` and `plasma-web.service`
after `enable --now` (which never restarts a running unit), so the health check
observes the new release. Before activation the Bootstrap deployment takes the
running Runtime's bounded TTL quiesce (`quiesce`, 60 s); it is refused while any
Site executes, and the upgrade then ends `verify_failed`
(`runtime_quiesce_denied`) without mutating the installation.

## IC Catalog / IC Support (not shipped)

Since OPF S5 / PR-C1 the Runtime kit ships **no** IC Support or Device Catalog
data, and neither `plasma-server.service` nor `plasma-web.service` sets
`PLASMA_IC_SUPPORT_ROOT` or `PLASMA_DEVICE_CATALOG_MANIFEST`. Execution is
decided only by the verified Active Bundle v3, device capability,
authorization and hardware safety; an enabled non-mock Site starts without
Catalog data. The PPU Gateway has no Device Selector route (`GET
/api/devices/search` is an unknown route since S5-B); the Device Selector is
owned by Manager (Console consumers migrated in PR-C2). Root, install,
verification and Rollback contracts are unchanged.

## Site Desired versus Runtime

Saving Desired and activating Runtime are distinct transactions:

```text
Browser Draft
  -> Save Desired
  -> /etc/plasma/ppu.yaml
  -> restart_required

Activate Desired Configuration
  -> verify expected aggregate Desired revision
  -> prevent concurrent Desired writes
  -> Server-authoritative quiesce
  -> restart plasma-server.service only
  -> Server reloads /etc/plasma/ppu.yaml
  -> verify same ppu_id
  -> verify same Desired revision
  -> reconcile Runtime
```

Two separate races must be closed:

- **Execution race:** SiteManager checks active execution and establishes the runtime quiesce gate under the same authoritative execution lock used for Job admission. A new Job cannot slip into the idle-check-to-restart window.
- **Desired-state race:** the canonical Site configuration controller marks runtime activation active before checking the aggregate Desired revision. Site Desired writes fail closed until restart/reconciliation ends. A stale activation request therefore cannot silently restart the Server after a newer Desired write wins.

The quiesce lease has a bounded TTL and expires automatically. Gateway/helper failure must not create an indefinite admission lock.

Protocol v3.3 still hides dormant interface bindings for disabled Sites. A successful restart can therefore reconcile to `partially_observable`; the UI must not invent evidence and call that state fully proven `in_sync`.

## Deployment activation and rollback

The release transaction remains side-by-side and rollback-oriented:

```text
verify everything
  -> copy immutable <release-id>
  -> snapshot canonical config + owned units + config-root metadata
  -> preserve existing ppu.yaml on upgrade
  -> write candidate Server/Gateway/helper units
  -> atomically switch /opt/plasma/current
  -> daemon-reload
  -> start Server + Gateway (Gateway pulls helper)
  -> direct/no-proxy readiness
```

If activation fails, the previous release, canonical configuration, Server/Gateway units, helper unit and config-root metadata are restored within the owned boundary. On first-install failure, candidate managed files are removed rather than promoted as an installation.

The installer also records explicit evidence that an upgrade preserved existing canonical configuration and that runtime activation uses the bounded helper contract.

### Full-Copy: Runtime + Bootstrap + Site Worker + Adapter (PR-B)

The PPU Runtime release carries the complete Bootstrap control plane of the same commit (the file set is `ppu-bootstrap-installer.py` `control_plane_files()`: Bootstrap service and deployment engine, enrollment/controller, B3 installer pair and policy, asset helpers, Package Action control plane, Site Worker v3, Site engine and the ABI-5 Adapter, Root parser and privileged source-only inputs). The Bootstrap deployment coordinator installs it inside the **same** transaction, lock and journal as the Runtime; there is no second installer:

```text
verify release + control plane + Adapter ABI           (verify_failed, nothing mutated)
  -> stage immutable <release-id>
  -> Runtime upgrade quiesce (refused while any Site executes)
  -> control_plane_installing: durable snapshot of every file to be replaced
       (/var/lib/plasma-bootstrap/control-plane-snapshots/<transaction>/, 0700)
  -> existing Bootstrap installer _copy_scripts into /opt/plasma/bootstrap
  -> verify every installed file SHA-256; write control-plane.json
       (release id, release git SHA, archive SHA-256, Worker protocol, Adapter ABI)
  -> activating: existing install_release (restarts Package control + Site Worker,
       then Server + Gateway) -> readiness
```

Rollback and recovery:

* control-plane copy or post-copy verification fails → the snapshot is restored byte-exact (files that did not exist are removed); Runtime and Worker were never restarted → `rolled_back`.
* Runtime activation or readiness fails → the installer calls the coordinator's `on_rollback` **before** restarting the previous Runtime: snapshot restored, Package control + Site Worker restarted on it, then the previous release/config/units are restored → `rolled_back`.
* any restore or rollback step fails, or the process ends mid-transaction → `recovery_required`. The snapshot is kept; the next deployment is refused and nothing is retried or resent automatically.

Device identity (`/etc/machine-id`), Bootstrap controller/enrollment state, Site seals, the engine selection, FPGA/privileged state and the Active Asset Set are outside the copied file set and are never touched.

Runtime binding: at start the Runtime (`plasma_server.package_actions.from_config`) requires `/opt/plasma/bootstrap/control-plane.json` to name the Active release's git SHA and its own Site Worker protocol, and the loaded `ppu_site_worker.PROTOCOL` to match. Otherwise the Runtime exits (`CONTROL_PLANE_RELEASE_UNBOUND`, `CONTROL_PLANE_RELEASE_MISMATCH`, `SITE_WORKER_PROTOCOL_MISMATCH`), so a new Runtime never runs against an old Worker and a deployment readiness check rolls back.

The running `plasma-bootstrap.service` keeps its in-memory code until it is restarted; the deployment result reports `control_plane.bootstrap_service_restart_required` and never restarts it. Once `control-plane.json` exists, `ppu-bootstrap-installer.py` (factory install and `--refresh-only`) refuses with `BOOTSTRAP_MANAGED_BY_FULL_COPY_DEPLOYMENT`; update Bootstrap by deploying the Runtime release of the same commit.

## Installation on a clean Z2

After extracting the kit:

```bash
sudo bash scripts/plasmactl install z2-ps \
  --python-artifact artifacts/plasma-python-<version>-linux-armv7l.tar.gz \
  --python-sidecar artifacts/plasma-python-<version>-linux-armv7l.tar.gz.sha256 \
  --openocd-artifact artifacts/plasma-openocd-<runtime-id>-linux-armv7l.tar.gz \
  --openocd-sidecar artifacts/plasma-openocd-<runtime-id>-linux-armv7l.tar.gz.sha256 \
  --release-artifact artifacts/plasma-ppu-<release-id>-linux-armv7l.tar.gz \
  --release-sidecar artifacts/plasma-ppu-<release-id>-linux-armv7l.tar.gz.sha256 \
  --gateway-host <Z2-IP> \
  --ppu-id z2-dev-01 \
  --facility-id lab
```

A later release uses `deploy z2-ps`. If no new Python artifact/path is supplied, the profile reuses `/opt/plasma/install/python-runtime.json` rather than guessing among interpreters. If no replacement OpenOCD artifact is supplied, it likewise requires and reuses `/opt/plasma/install/openocd-runtime.json`. Installing the Programming Engine does not start an OpenOCD service and does not change `hardware_runtime_ready=false`.

## Local Z2 verification

```bash
bash scripts/plasmactl verify z2-ps
bash scripts/plasmactl status z2-ps
```

The current verifier proves a real ARMv7 host, active Server/Gateway/runtime-activation helper services, canonical Site Desired ownership, P3 installer evidence, the bounded Server/helper Unix-socket DAC contract, Gateway readiness, the G13 controller challenge served through the Bootstrap admission socket for the same device (GET only; since LOM-P2A-2 P0 the installer sends no write and never reads the controller credential — the signed PS loopback is the Manager's controller-authorized acceptance), and the closed hardware boundary. OpenOCD packaging is qualified separately: CI builds both x86_64 and ARMv7 artifacts, executes the ARMv7 runtime under QEMU, checks the bundled script tree and shared-library closure, and runs a software-only dummy-adapter smoke. That evidence is Programming Engine packaging/runtime evidence only. It does **not** issue the controlled restart transaction merely to make verification pass.

A real P3 activation acceptance should additionally prove on the exact deployed identity:

```text
Server + Gateway + runtime helper active as intended
upgrade preserved canonical Site Desired state
active programming execution blocks activation
new Job admission cannot race restart
controlled activation restarts only Plasma Server
same ppu_id after restart
same aggregate Desired revision after restart
Runtime reconciliation reaches the expected state
PYNQ System Python/PYNQ ownership unchanged
```

Until the controlled activation sequence is actually exercised on physical hardware, report the verifier PASS as **Real Z2 PS runtime/wiring evidence**, not as a complete Real Z2 P3 controlled-activation PASS.

## Managed Control Station path

The intended operator path is:

```text
Control Station EMode
  -> PPU/Site Management
  -> Add PPU
  -> Manager observation
  -> Validate & Enable
  -> edit Site Draft
  -> Save Desired
  -> Activate Desired Configuration if required
```

Managed activation uses an explicit same-origin BFF route and an exact Manager allowlist entry for `/api/settings/sites/activation`; it is not a generic URL proxy. Secure Gateway admits the activation endpoint only for Engineer/Admin roles and keeps durable command-idempotency admission.

## Explicit non-claims

P3 does not qualify or implement:

```text
hot reload
Plasma Protocol v3.3 changes
WebSocket/SSE
PS <-> PL
FPGA execution/loading
PMOD/Site electrical behavior
target power
OpenOCD Tcl RPC / worker lifecycle
SWD/JTAG through a physical adapter or PL
real IC programming
8-Site hardware concurrency
publisher signing/authenticity
production programmer readiness
```

Controlled Server restart is implemented in software/release wiring; physical Z2 acceptance remains separate evidence.
