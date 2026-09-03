# Plasma PPU Runtime Packaging

Status: **Phase-1 implementation for Z2 PS software-node deployment**

## Purpose

This layer creates the first source-tree-independent PPU product runtime for the PYNQ-Z2 path. Its acceptance target is deliberately narrow:

```text
Control Station
  -> Manager
  -> Z2 Plasma Gateway
  -> Z2 Plasma Server
  -> PS diagnostic handler
  -> return
```

It does not load an FPGA bitstream, access PL, change target power, or program an IC.

## Runtime boundary

`scripts/ppu-runtime.py` builds one PPU runtime directory containing:

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

`ppu.pyz` is a self-contained Python zipapp containing the Plasma PPU Python packages and PyYAML. It exposes exactly two process entrypoints:

```text
python3 ppu/ppu.pyz server  --config <ppu-config>
python3 ppu/ppu.pyz gateway <gateway arguments>
```

The `gateway` CLI subcommand is an implementation identifier; the running northbound service is the **Plasma Gateway**.

The PPU runtime does not contain the Control Console, Plasma Manager, Node.js/npm payloads, Git metadata, tests, FPGA bitstreams, or PL/real-target activation logic.

The production Device Catalog is included as runtime data so the Plasma Gateway does not depend on a source-tree-relative `data/` directory when later Device Catalog routes are used. A deployed service should set `PLASMA_DEVICE_CATALOG_MANIFEST` to the installed manifest path.

## Canonical release

`scripts/ppu-release.py` validates the PPU runtime and delegates immutable release construction to the Common Release Format implementation in `scripts/product-release.py`.

Current target identity is intentionally exact:

```text
role         = ppu
platform     = linux
architecture = armv7l
```

The resulting artifact is conceptually:

```text
plasma-ppu-<version>-linux-armv7l.tar.gz
plasma-ppu-<version>-linux-armv7l.tar.gz.sha256
```

The release carries the canonical contracts:

```text
Plasma Protocol = 3.3
Plasma Gateway API / Web REST = 3
```

## Build

From a clean build host with Python >= 3.11 and the repository's Python build dependencies available:

```bash
python3 scripts/ppu-runtime.py build \
  --output-dir /tmp/plasma-ppu-runtime

python3 scripts/ppu-release.py \
  --runtime-dir /tmp/plasma-ppu-runtime \
  --output-dir /tmp/plasma-ppu-release \
  --git-sha "$(git rev-parse HEAD)"
```

The target PPU does not need Git, npm, Node.js, Vite, or a source checkout merely to run the packaged PPU runtime.

## GitHub Actions release artifact

`.github/workflows/ppu-release.yml` provides the CI build boundary for the same canonical `ppu/linux/armv7l` release. It runs on relevant pull requests and can also be started explicitly with `workflow_dispatch`.

The workflow:

```text
checkout
  -> install Python build/test dependencies
  -> PPU packaging regression tests
  -> build + validate ppu-runtime
  -> build canonical linux-armv7l release
  -> Common Release Format clean verification
  -> closed hardware-boundary verification
  -> detached SHA-256 verification
  -> upload GitHub Actions artifact
```

The uploaded Actions artifact is a transport envelope containing exactly the deployable release archive and its detached digest:

```text
plasma-ppu-<version>-linux-armv7l.tar.gz
plasma-ppu-<version>-linux-armv7l.tar.gz.sha256
```

Pull-request artifacts are validation evidence for the PR merge ref and must not be confused with a released `main` build. For a Z2 deployment candidate, run the workflow explicitly against the intended `main` revision and retain the resulting artifact/SHA evidence. This workflow does not deploy to a Z2 and does not create a GitHub Release.

## Z2 deployment prerequisites

Before mutating the Z2, run the existing read-only PPU readiness audit on the target and record the result:

```bash
python3 product-deploy.py audit ppu --json
```

The current product baseline requires:

- Linux on an ARM target;
- Python >= 3.11;
- system-level systemd;
- network reachability suitable for the Control Station Manager to reach the PPU Plasma Gateway Endpoint.

An audit failure is a deployment blocker to resolve explicitly. Do not bypass a Python/runtime mismatch by claiming the product runtime has been validated.

## Phase-1 PS-only configuration

The first Z2 deployment must keep Site/hardware execution closed. A valid PS-only Plasma Server configuration may declare the canonical PPU identity and zero active Sites while the PS diagnostic route is being accepted:

```yaml
ppu:
  id: z2-dev-01
  facility_id: lab
  model: PYNQ-Z2
  display_name: Plasma Z2 PS Phase 1

server:
  host: 127.0.0.1
  port: 9900
  max_supported_sites: 8
  max_concurrent_jobs: 1
  max_queue_depth_per_site: 16
  output_root: /var/lib/plasma/output
  log_root: /var/log/plasma
  max_metadata_bytes: 65536
  max_map_bytes: 1048576
  max_binary_bytes: 67108864

sites: []
```

This is not a claim that the physical PPU has zero Sites. It is a deliberate fail-closed execution configuration for the PS-only deployment milestone. Physical Site topology and PL-backed interfaces belong to a later approved hardware phase.

## Service topology

The intended first Z2 service topology is:

```text
systemd
├── plasma-server.service
│     -> Python >= 3.11
│     -> ppu.pyz server
│     -> 127.0.0.1:9900
└── plasma-web.service
      -> Python >= 3.11
      -> ppu.pyz gateway
      -> externally reachable Plasma Gateway port (normally 18080)
      -> local Plasma Server 127.0.0.1:9900
```

`plasma-web.service` is the existing systemd unit name and remains unchanged for compatibility. Its product role is Plasma Gateway.

The Plasma Gateway listen address is a deployment/security choice. Do not default an externally reachable service to an arbitrary public interface without confirming the intended trusted network path. The Plasma Server remains loopback-only.

## Manager enrollment

The Control Station Manager registry uses a stable alias and the Z2 **Plasma Gateway Endpoint**:

```yaml
ppus:
  - alias: z2
    endpoint: http://<z2-reachable-address>:18080
```

After enrollment, the Control Station selected PPU alias can be switched from the SWPC Mock target to `z2`.

## Phase-1 acceptance

The first runtime evidence must prove the real deployed process chain, not only package integrity:

```text
Z2 readiness audit                         PASS
Z2 plasma-server service                  active
Z2 plasma-web service                     active
GET Z2 /api/health/ready                  PASS
Control Station Manager selected alias    z2
Managed PS Loopback                       PASS
```

Run the existing managed runtime scenario from the Control Station using its BFF base URL:

```bash
python3 scripts/runtime_acceptance/run.py ps-loopback \
  --base-url http://127.0.0.1:18000/api/manager/ppu \
  --environment managed-z2-ps
```

A PASS proves only the PS software node and network/control-plane path. It does **not** prove PS <-> PL, FPGA execution, PMOD/Site I/O, target power, socket behavior, or real IC programming.

## Deferred after Phase 1

The following are intentionally outside this milestone:

- production-grade PPU installer/upgrade/rollback adapter;
- PL bitstream packaging/loading;
- FPGA interface activation;
- physical Site topology enablement;
- real target power and programming;
- multi-Site hardware concurrency acceptance.
