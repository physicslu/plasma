# Plasma PPU Runtime Packaging

Status: **P3 software/release implementation for Z2 PS deployment; physical Z2 runtime activation remains a separate qualification boundary**

## Purpose

This layer creates the source-tree-independent PPU runtime for the PYNQ-Z2 PS path:

```text
Control Station
  -> Manager
  -> Z2 Plasma Gateway
  -> bounded runtime-activation helper
  -> Z2 Plasma Server
  -> PS diagnostic/programming runtime
```

P3 adds controlled Site Desired runtime activation. It does not load FPGA content, access PL, change target power, or program a real IC merely by activating configuration.

## Runtime boundary

`scripts/ppu-runtime.py` builds:

```text
ppu-runtime.json
ppu/
├── ppu.pyz
└── THIRD_PARTY_LICENSES/
    └── PyYAML.txt
data/
└── device-catalog/
    └── production/
```

`ppu.pyz` is a self-contained Python zipapp exposing Server, Gateway, and the bounded runtime-activation helper entrypoint. The runtime excludes Control Station, Manager, Node/npm, Git metadata, tests, FPGA bitstreams and physical-target power control.

## Canonical release and Release Identity v2

`scripts/ppu-release.py` validates the runtime and delegates Common Release Format construction to `scripts/product-release.py`.

```text
role         = ppu
platform     = linux
architecture = armv7l

release_id = <product-version>-<first-12-git-sha>
```

Deployable release files:

```text
plasma-ppu-<release-id>-linux-armv7l.tar.gz
plasma-ppu-<release-id>-linux-armv7l.tar.gz.sha256
```

`release.json` retains the full 40-character source Git SHA. The release carries Plasma Protocol 3.3 and Plasma Gateway/Web REST contract 3; P3 does not change either protocol contract.

## Build

```bash
python3 scripts/ppu-runtime.py build \
  --output-dir /tmp/plasma-ppu-runtime

python3 scripts/ppu-release.py \
  --runtime-dir /tmp/plasma-ppu-runtime \
  --output-dir /tmp/plasma-ppu-release \
  --git-sha "$(git rev-parse HEAD)"
```

The target PPU does not need Git, npm, Node.js, Vite, or a source checkout to run the packaged runtime.

## GitHub Actions release and installer bootstrap

`.github/workflows/ppu-release.yml` validates the PPU runtime/release, Z2 bootstrap compatibility, Common Release Format integrity, the closed hardware boundary, ARMv7 userspace behavior and network acceptance.

The P3 Z2 installer is an intentional **two-file bootstrap unit**. The versioned wrapper contains the P3 operational delta; the sibling core retains the audited P2 verification/install implementation. Publishing only the wrapper is invalid because the wrapper imports the sibling core by exact filename.

```text
Actions artifact:
plasma-ppu-linux-armv7l-<release-id>

contents:
plasma-ppu-<release-id>-linux-armv7l.tar.gz
plasma-ppu-<release-id>-linux-armv7l.tar.gz.sha256
plasma-ppu-z2-installer-<release-id>.py
plasma-ppu-z2-installer-<release-id>.py.sha256
ppu-z2-installer-core.py
ppu-z2-installer-core.py.sha256
```

CI compiles both bootstrap files under Python 3.10, verifies both detached digests, and executes the packaged wrapper with the packaged sibling core against the canonical PPU release. This is specifically intended to prevent a source-tree-only installer from being published as a valid deployment artifact.

Pull-request artifacts remain PR validation evidence. For a Z2 deployment candidate, explicitly run the workflow against the intended `main` revision and retain version, full source SHA and artifact digest evidence.

## Z2 Python ownership

ADR-0001 remains mandatory: PYNQ owns its System Python; Plasma owns a separate interpreter under:

```text
/opt/plasma/python/
```

The bootstrap remains Python-3.10-compatible. The installed Plasma runtime requires ARMv7 Python >=3.11 final and does not replace `/usr/bin/python3` or the PYNQ venv.

## First-install versus upgrade configuration ownership

A clean first installation may generate the fail-closed PS-only canonical topology:

```yaml
server:
  max_supported_sites: 8

sites: []
```

That is a bootstrap state only. On an **upgrade**, `/etc/plasma/ppu.yaml` is operator/runtime state and must not be regenerated from first-install defaults. P3 therefore preserves the entire existing canonical file, including Site Desired records, while updating release/service wiring.

The topology semantics remain:

```text
max_supported_sites = capacity ceiling
site_count           = configured Sites
site_id              = one-based identity; Site 0 is invalid
```

## Service topology

```text
systemd
├── plasma-server.service
│     -> Plasma-owned Python >=3.11
│     -> ppu.pyz server --config /etc/plasma/ppu.yaml
│     -> local runtime-control Unix socket
│     -> 127.0.0.1:9900
├── plasma-runtime-activation.service
│     -> root process, Group=plasma
│     -> AF_UNIX only
│     -> exact operation: restart plasma-server.service
│     -> no arbitrary service name, command, or shell
│     -> PartOf=plasma-web.service
└── plasma-web.service
      -> Plasma-owned Python >=3.11
      -> ppu.pyz gateway --ppu-config /etc/plasma/ppu.yaml
      -> bounded helper Unix socket
      -> explicit trusted Z2 IPv4 :18080
```

The helper is not independently enabled as a fourth autonomous product daemon. Gateway `Requires=` the helper and owns its lifecycle; `PartOf=plasma-web.service` keeps rollback/restart behavior coupled to the Gateway deployment transaction.

## Controlled Site Desired runtime activation

Saving Desired configuration and activating Runtime remain separate operations:

```text
Browser Draft
  -> Save Desired
  -> canonical /etc/plasma/ppu.yaml
  -> restart_required
  -> Activate Desired Configuration
  -> Gateway Desired transaction guard
  -> Server-authoritative quiesce
  -> exact plasma-server.service restart
  -> reload canonical config
  -> verify same ppu_id
  -> verify same aggregate Desired revision
  -> Runtime In Sync / Partially Observable
```

The Site configuration controller serializes Desired writes against this activation transaction. This closes the stale-request race where Desired could otherwise change after the aggregate revision check but before the restart. Separately, SiteManager uses the same authoritative execution lock for Job admission and runtime quiesce, closing the idle-check-to-restart TOCTOU window.

The quiesce lease is bounded and expires automatically. Protocol v3.3 still does not expose dormant interface/target bindings for disabled Sites, so a post-restart state can legitimately remain `partially_observable` instead of being falsely promoted to fully proven `in_sync`.

## Filesystem/write boundary

```text
/etc/plasma           root:plasma   0770
/etc/plasma/ppu.yaml  plasma:plasma 0640
```

Plasma Server reads canonical configuration but does not persist it. Plasma Gateway retains the bounded `/etc/plasma` directory write required by same-directory atomic `os.replace` for Site Desired persistence. The runtime helper does not receive a generic `/etc` write API.

## Qualification boundary

CI can prove source contracts, packaging completeness, Python compatibility, bounded helper behavior in software tests, ARMv7 userspace packaging, and managed-relay contracts. It does **not** prove real PYNQ-Z2 systemd/DAC behavior or that a physical restart is safe under every target condition.

A physical P3 acceptance must separately exercise the exact deployed Z2 identity and demonstrate at minimum:

```text
real ARMv7 Z2 runtime
Server + Gateway + helper service topology
saved canonical Site Desired state survives software upgrade
active execution blocks activation
controlled activation restarts only Plasma Server
same ppu_id after restart
Desired revision unchanged through activation
Runtime reconciliation reaches expected state
PYNQ-owned Python remains unchanged
```

No CI PASS is promoted into this physical evidence class.

## Deferred / non-claims

P3 does not implement hot reload, Protocol v3.3 changes, WebSocket/SSE, PL bitstream loading, Site electrical qualification, target power control, real IC programming, or 8-Site hardware-concurrency qualification. Those remain separate milestones.
