# Plasma PPU Runtime Packaging

Status: **Phase-1 implementation for Z2 PS software-node deployment**

## Purpose

This layer creates the source-tree-independent PPU runtime for the PYNQ-Z2 PS path:

```text
Control Station
  -> Manager
  -> Z2 Plasma Gateway
  -> Z2 Plasma Server
  -> PS diagnostic handler
  -> return
```

It does not load FPGA content, access PL, change target power, or program an IC.

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

`ppu.pyz` is a self-contained Python zipapp exposing Server and Gateway process entrypoints. The runtime excludes Control Station, Manager, Node/npm, Git metadata, tests, FPGA bitstreams and physical-target activation logic.

## Canonical release and Release Identity v2

`scripts/ppu-release.py` validates the runtime and delegates Common Release Format construction to `scripts/product-release.py`.

Target identity remains:

```text
role         = ppu
platform     = linux
architecture = armv7l
```

The deployable release filename is source-qualified:

```text
plasma-ppu-<release-id>-linux-armv7l.tar.gz
plasma-ppu-<release-id>-linux-armv7l.tar.gz.sha256

release_id = <product-version>-<first-12-git-sha>
```

Example:

```text
plasma-ppu-0.1.1-abcdef123456-linux-armv7l.tar.gz
```

`release.json` retains the full 40-character source Git SHA. The detached SHA-256 identifies the exact archive bytes.

The release carries:

```text
Plasma Protocol = 3.3
Plasma Gateway API / Web REST = 3
```

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

## GitHub Actions release and installer kit

`.github/workflows/ppu-release.yml` validates the PPU runtime/release, Z2 bootstrap compatibility, Common Release Format integrity, closed hardware boundary, ARMv7 userspace behavior and network acceptance.

The deployable Actions transport envelope is also identity-qualified:

```text
Actions artifact:
plasma-ppu-linux-armv7l-<release-id>

contents:
plasma-ppu-<release-id>-linux-armv7l.tar.gz
plasma-ppu-<release-id>-linux-armv7l.tar.gz.sha256
plasma-ppu-z2-installer-<release-id>.py
plasma-ppu-z2-installer-<release-id>.py.sha256
```

This avoids the previous ambiguity where different source commits under the same product version could be downloaded under identical filenames.

Pull-request artifacts remain PR validation evidence. For a Z2 deployment candidate, explicitly run the workflow against the intended `main` revision and retain version, full source SHA and artifact digest evidence.

## Z2 Python ownership

ADR-0001 remains mandatory: PYNQ owns its System Python; Plasma owns a separate interpreter under:

```text
/opt/plasma/python/
```

The installer requires ARMv7 Python >=3.11 final and does not replace `/usr/bin/python3` or the PYNQ venv.

## Phase-1 PS-only topology

The first Z2 deployment deliberately keeps hardware/Site execution closed:

```yaml
ppu:
  id: z2-dev-01
  facility_id: lab
  model: PYNQ-Z2
  display_name: Plasma Z2 PS

server:
  host: 127.0.0.1
  port: 9900
  max_supported_sites: 8
  max_concurrent_jobs: 1
  max_queue_depth_per_site: 16

sites: []
```

The topology semantics are:

```text
max_supported_sites = hardware/software capacity ceiling = 8
site_count           = currently configured Sites        = 0
 enabled_site_count  = currently enabled Sites           = 0
sites                = current topology                   = []
```

`site_count = 0` is valid for a PS-only node. It does **not** create or authorize `Site 0`; any actual Site identity remains one-based (`site_id >= 1`).

This distinction is required so Manager can identify and commission the PS software node without fabricating eight physical Sites before PL/hardware topology exists.

## Service topology

```text
systemd
├── plasma-server.service
│     -> Plasma-owned Python >=3.11
│     -> /opt/plasma/current/runtime/ppu/ppu.pyz server
│     -> 127.0.0.1:9900
└── plasma-web.service
      -> Plasma-owned Python >=3.11
      -> /opt/plasma/current/runtime/ppu/ppu.pyz gateway
      -> explicit trusted Z2 IPv4 :18080
      -> local Server :9900
```

## Manager enrollment and acceptance

Manager registers the Z2 Plasma Gateway Endpoint under a stable alias such as `z2`. A trusted PS-only fleet observation may legitimately report zero Sites while still providing valid PPU identity/model/facility and ready execution.

Phase-1 evidence must prove:

```text
isolated Plasma Python                     PASS
Z2 installer local activation              PASS
Z2 Server/Gateway services                 active
GET Z2 /api/health/ready                  PASS
Manager trusted PPU identity               PASS
current Site topology                     0 Sites
Managed PS Loopback                       PASS
PYNQ System Python/PYNQ regression         PASS
```

Run Managed PS Loopback from the installed Control Station:

```bash
python3 scripts/runtime_acceptance/run.py ps-loopback \
  --base-url http://127.0.0.1:18000/api/manager/ppu \
  --environment managed-z2-ps
```

A PASS proves only the PS software node and network/control-plane path. It does not prove PS↔PL, FPGA execution, PMOD/Site I/O, target power, socket behavior or real IC programming.

## Deferred

Bundled Z2 Python, publisher signing/authenticity, PL bitstream packaging/loading, physical Site activation, target power, real programming and multi-Site hardware concurrency remain separate milestones.
