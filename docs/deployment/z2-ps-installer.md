# PYNQ-Z2 PS Release Kit and Managed Loopback Acceptance

Status: **PS-only release-kit implementation; every deployment candidate still requires real Z2 qualification**

## Purpose

The Z2 PS deployment path turns a clean PYNQ-Z2 image into a Plasma PPU PS node without compiling Plasma or CPython on the board.

The product flow is:

```text
GitHub Actions
  -> build qualified ARMv7 Plasma Python candidate
  -> build canonical ppu/linux/armv7l release
  -> assemble source-tree-independent Z2 PS kit
  -> Actions artifact

Clean PYNQ-Z2
  -> verify/install Plasma-owned Python below /opt/plasma/python
  -> verify/install immutable PPU release
  -> systemd Server + Gateway
  -> local readiness + PS diagnostic loopback
  -> Control Station Add PPU / Validate & Enable
  -> Managed PS Loopback acceptance
```

The PS profile does **not** load an FPGA bitstream, access PL, enable physical Sites, change target power, or program a real IC.

## Why the kit exists

A clean Z2 is a runtime target, not a build server. Rebuilding CPython on the board is slow and makes deployment depend on target-local build state. The release candidate therefore moves deterministic build work into GitHub CI and keeps the Z2 responsibility to install, execute, and provide hardware/runtime evidence.

```text
GitHub CI = build / software validation / package transport
Real Z2   = install / runtime validation / hardware qualification
```

A CI PASS must never be reported as a Real Z2 PASS.

## Release identity

PPU Release Identity v2 remains mandatory:

```text
product_version = 0.1.1
full git_sha    = <40-character Plasma source SHA>
release_id      = 0.1.1-<first-12-git-sha>
artifact_sha256 = <exact PPU archive digest>
```

The Plasma Python artifact has a separate runtime identity:

```text
role            = plasma-python-runtime
platform        = linux
architecture    = armv7l
python_version  = 3.12.13
source_ref      = pinned python.org source archive + SHA-256
```

These identities are intentionally separate: upgrading Plasma application code must not silently replace the PYNQ System Python or conflate CPython provenance with Plasma source provenance.

## Runtime ownership

ADR-0001 remains mandatory. PYNQ owns System Python; Plasma owns a separate runtime.

Observed development baseline:

```text
architecture      armv7l
OS                PynqLinux 3.0 / Ubuntu 22.04 base
glibc             2.35
systemd           249
System Python     3.10.4
PYNQ              3.1.1
Ethernet          192.168.2.99/24
```

Plasma runtime lives only below:

```text
/opt/plasma/python/<version>/
```

The bootstrap scripts remain Python-3.10-compatible so the stock PYNQ image can verify and start installation. Plasma Server and Plasma Gateway use the isolated Plasma interpreter, never `/usr/bin/python3` or the PYNQ venv.

## GitHub-built release candidate kit

Workflow:

```text
.github/workflows/z2-ps-release.yml
```

It builds CPython from the pinned official source archive inside an Ubuntu 22.04 ARMv7 userspace under QEMU, validates the resulting runtime, then assembles the PPU release and deployment tooling.

GitHub Actions artifact:

```text
plasma-z2-ps-kit-<release-id>
```

Transport payload:

```text
plasma-z2-ps-kit-<release-id>.tar.gz
plasma-z2-ps-kit-<release-id>.tar.gz.sha256
```

After extraction:

```text
plasma-z2-ps-kit-<release-id>/
├── SHA256SUMS
├── scripts/
│   ├── plasmactl
│   ├── plasmactl-z2-ps
│   ├── ppu-z2-installer.py
│   └── z2-python-runtime.py
├── artifacts/
│   ├── plasma-python-3.12.13-linux-armv7l.tar.gz
│   ├── plasma-python-3.12.13-linux-armv7l.tar.gz.sha256
│   ├── plasma-ppu-<release-id>-linux-armv7l.tar.gz
│   └── plasma-ppu-<release-id>-linux-armv7l.tar.gz.sha256
└── docs/
    └── README.md
```

The Z2 does not need Git, npm, Node.js, Vite, a Plasma source checkout, a compiler, or a local CPython build to consume this kit.

## Plasma Python artifact safety

`scripts/z2-python-runtime.py` validates:

1. detached archive SHA-256;
2. canonical archive root and safe extraction paths;
3. regular files/directories only — links and special files are rejected;
4. exact internal `SHA256SUMS` file set and digests;
5. Linux/ARMv7 runtime manifest;
6. final Python >=3.11;
7. successful target execution with `ssl` and `sqlite3` imports;
8. ownership boundary declaring that System Python and PYNQ Python are not replaced.

Installation writes:

```text
/opt/plasma/python/<version>/
/opt/plasma/install/python-runtime.json
```

The installer does not mutate `/usr/bin/python3`.

## PPU release verification before mutation

`scripts/ppu-z2-installer.py` validates:

1. detached PPU archive SHA-256;
2. safe `tar.gz` structure under `plasma-release/`;
3. no unsafe/non-regular archive members or extraction-limit breach;
4. exact internal `SHA256SUMS` file set and digests;
5. `release.json` full source identity, `ppu/linux/armv7l` target and contracts;
6. PPU runtime identity;
7. closed hardware boundary;
8. production Device Catalog presence;
9. explicit Plasma-owned ARMv7 final Python >=3.11.

## Filesystem and service boundary

```text
/opt/plasma/
├── python/
│   └── <python-version>/
├── releases/
│   └── <release-id>/
├── current -> releases/<release-id>/
└── install/
    ├── python-runtime.json
    └── last-install.json

/etc/plasma/ppu.yaml
/var/lib/plasma/
/var/log/plasma/
/etc/systemd/system/plasma-server.service
/etc/systemd/system/plasma-web.service
```

A dedicated `plasma` system user owns mutable state/logs. Immutable release content and systemd units remain system-owned.

## PS-only topology contract

The generated first-stage configuration deliberately keeps:

```yaml
server:
  max_supported_sites: 8

sites: []
```

Therefore:

```text
max_supported_sites = 8   capacity ceiling
site_count           = 0   current configured topology
enabled_site_count   = 0
sites                = []
```

This is a valid fail-closed PS-only state. It is not a claim that the eventual appliance has no Sites, and it never creates `SITE 0`. Physical Site identity remains one-based.

## Network binding

Qualification requires an explicit non-loopback unicast IPv4 address for `--gateway-host`; wildcard `0.0.0.0` is rejected.

The Plasma Server remains:

```text
127.0.0.1:9900
```

The Plasma Gateway binds the explicit Z2 address on port `18080` and connects locally to Server.

## Installation on a clean Z2

Assume the extracted kit directory is the current directory and the Z2 address is `192.168.2.99`.

First identify the exact artifact names:

```bash
ls artifacts/
```

Then install using the kit-local `plasmactl` router:

```bash
sudo bash scripts/plasmactl install z2-ps \
  --python-artifact artifacts/plasma-python-3.12.13-linux-armv7l.tar.gz \
  --python-sidecar artifacts/plasma-python-3.12.13-linux-armv7l.tar.gz.sha256 \
  --release-artifact artifacts/plasma-ppu-<release-id>-linux-armv7l.tar.gz \
  --release-sidecar artifacts/plasma-ppu-<release-id>-linux-armv7l.tar.gz.sha256 \
  --gateway-host 192.168.2.99 \
  --ppu-id z2-dev-01 \
  --facility-id lab
```

The first install verifies and installs the isolated Python runtime before invoking the existing PPU installer. An already installed Z2 uses `deploy` for a new Plasma release:

```bash
sudo bash scripts/plasmactl deploy z2-ps \
  --release-artifact artifacts/plasma-ppu-<new-release-id>-linux-armv7l.tar.gz \
  --release-sidecar artifacts/plasma-ppu-<new-release-id>-linux-armv7l.tar.gz.sha256 \
  --gateway-host 192.168.2.99 \
  --ppu-id z2-dev-01 \
  --facility-id lab
```

When `--python-artifact` and `--plasma-python` are omitted during deploy, the profile reuses `/opt/plasma/install/python-runtime.json`.

## Activation and rollback

PPU activation remains side-by-side and source-identity-aware:

```text
verify everything
  -> copy immutable <release-id>
  -> snapshot managed config + units
  -> write candidate PS-only config + units
  -> atomically switch /opt/plasma/current
  -> daemon-reload
  -> enable/start Server + Gateway
  -> direct/no-proxy readiness
```

PPU activation failure restores the previous release/configuration/service state. Python runtime installation is separate and fail-closed; a Python runtime must execute successfully on the real ARMv7 target before PPU activation begins.

## Local Z2 verification

```bash
bash scripts/plasmactl verify z2-ps
bash scripts/plasmactl status z2-ps
```

`verify z2-ps` requires:

```text
real Linux ARMv7 host
plasma-server.service active
plasma-web.service active
/api/health/ready PASS
local POST /api/engineering/diagnostics/loopback executes at endpoint=ps/source=ps
closed hardware boundary retained in install evidence
```

A PASS here means:

```text
Real Z2 ARMv7 PS runtime + local PS diagnostic path qualified
```

It does **not** yet prove the Control Station managed route.

## Control Station enrollment and Managed PS Loopback

After local Z2 verification:

```text
Control Station EMode
  -> Add PPU
  -> alias + http://<Z2-IP>:18080
  -> Pending
  -> Manager trusted observation
  -> Validate & Enable
  -> Managed PS Loopback
```

The end-to-end acceptance path is:

```text
Control Station
  -> same-origin Manager BFF
  -> Manager selected Z2 alias
  -> Z2 Plasma Gateway :18080
  -> Z2 Plasma Server :9900
  -> PS diagnostic handler
  -> return
```

Only after this passes for the exact deployed Control Station and PPU source identities may retained evidence state **Managed PS Loopback PASS**.

## PYNQ regression requirement

After installation, re-check PYNQ-owned Python/PYNQ. Plasma installation must not replace that ownership domain.

## Explicit non-claims

This phase does not qualify:

```text
PS <-> PL
FPGA execution/loading
PMOD/Site electrical behavior
target power
real IC programming
8-Site hardware concurrency
publisher signing/authenticity
production programmer readiness
```
