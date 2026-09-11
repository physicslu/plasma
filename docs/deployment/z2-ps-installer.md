# PYNQ-Z2 PS Release Kit and Managed Acceptance

Status: **PS-only release-kit implementation with P3 controlled Site Desired runtime activation wiring; every deployment candidate still requires real Z2 qualification**

## Purpose

The Z2 PS deployment path turns a clean PYNQ-Z2 image into a Plasma PPU PS node without compiling Plasma or CPython on the board.

```text
GitHub Actions
  -> build qualified ARMv7 Plasma Python candidate
  -> build canonical ppu/linux/armv7l release
  -> assemble source-tree-independent Z2 PS kit
  -> Actions artifact

Clean PYNQ-Z2
  -> verify/install Plasma-owned Python below /opt/plasma/python
  -> verify/install immutable PPU release
  -> systemd Server + Gateway + bounded runtime-activation helper
  -> local readiness + PS diagnostic loopback
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

PYNQ continues to own System Python. Bootstrap tooling remains Python-3.10-compatible; Plasma Server, Gateway and helper use the isolated Plasma interpreter and never replace `/usr/bin/python3` or the PYNQ venv.

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
│   └── z2-python-runtime.py
├── artifacts/
│   ├── plasma-python-<version>-linux-armv7l.tar.gz
│   ├── plasma-python-<version>-linux-armv7l.tar.gz.sha256
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
6. PPU runtime identity and production Device Catalog presence;
7. closed hardware boundary;
8. explicit Plasma-owned ARMv7 final Python >=3.11;
9. Server/Gateway canonical configuration identity.

P3 packaging separately verifies the wrapper/core bootstrap pair instead of assuming the repository source tree will be present on the appliance.

## Filesystem and service boundary

```text
/opt/plasma/
├── python/<python-version>/
├── releases/<release-id>/
├── current -> releases/<release-id>/
└── install/
    ├── python-runtime.json
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

A first install may create the fail-closed PS bootstrap topology:

```yaml
server:
  max_supported_sites: 8

sites: []
```

This means capacity ceiling 8 and configured Site count 0; it does not create `SITE0` and does not hard-code eight Sites into the Web/API topology.

An **upgrade is different**. Existing `/etc/plasma/ppu.yaml` is persisted product state and may contain operator-approved Site Desired records. P3 therefore preserves the existing canonical file instead of regenerating first-install `sites: []`. The release/service wiring changes; the canonical Desired content survives.

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

Protocol v3.3 still hides dormant interface/target bindings for disabled Sites. A successful restart can therefore reconcile to `partially_observable`; the UI must not invent evidence and call that state fully proven `in_sync`.

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

## Installation on a clean Z2

After extracting the kit:

```bash
sudo bash scripts/plasmactl install z2-ps \
  --python-artifact artifacts/plasma-python-<version>-linux-armv7l.tar.gz \
  --python-sidecar artifacts/plasma-python-<version>-linux-armv7l.tar.gz.sha256 \
  --release-artifact artifacts/plasma-ppu-<release-id>-linux-armv7l.tar.gz \
  --release-sidecar artifacts/plasma-ppu-<release-id>-linux-armv7l.tar.gz.sha256 \
  --gateway-host <Z2-IP> \
  --ppu-id z2-dev-01 \
  --facility-id lab
```

A later release uses `deploy z2-ps`. If no new Python artifact/path is supplied, the profile reuses `/opt/plasma/install/python-runtime.json` rather than guessing among interpreters.

## Local Z2 verification

```bash
bash scripts/plasmactl verify z2-ps
bash scripts/plasmactl status z2-ps
```

The historical PS-only verification proves a real ARMv7 host, active Server/Gateway, Gateway readiness, local PS diagnostic loopback, and the closed hardware boundary. P3 adds helper/service/configuration contracts in source and packaging, but **that does not automatically qualify controlled activation on a physical Z2**.

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

Until this is actually exercised on physical hardware, report it as software/release implementation rather than Real Z2 P3 PASS.

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
real IC programming
8-Site hardware concurrency
publisher signing/authenticity
production programmer readiness
```

Controlled Server restart is implemented in software/release wiring; physical Z2 acceptance remains separate evidence.
