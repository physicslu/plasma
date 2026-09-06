# PYNQ-Z2 PS Installer and Managed Loopback Acceptance

Status: **PS-only installer implementation; each new deployment candidate requires real Z2 qualification**

## Purpose

`scripts/ppu-z2-installer.py` is the host-mutating product adapter for the PPU/Z2 role. It consumes the canonical `ppu/linux/armv7l` Common Release Format artifact and activates only the PS software node:

```text
verified PPU release
  -> immutable /opt/plasma/releases/<release-id>
  -> /opt/plasma/current
  -> plasma-server.service
  -> plasma-web.service
  -> /api/health/ready
```

The installer does not load an FPGA bitstream, access PL, enable physical Sites, change target power, or program a real IC.

## Release identity

Release Identity v2 is mandatory for deployment candidates:

```text
product_version = 0.1.1
full git_sha    = <40-character source SHA>
release_id      = 0.1.1-<first-12-git-sha>
artifact_sha256 = <exact archive digest>
```

The Common Release Format archive, Actions transport envelope, copied installer script and installed immutable directory all carry the same release identity. The installed evidence retains the full source SHA.

## Runtime ownership

ADR-0001 is mandatory. PYNQ owns System Python; Plasma owns a separate runtime.

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

Plasma requires a final ARMv7 Python >=3.11 below:

```text
/opt/plasma/python/
```

The bootstrap itself remains Python-3.10-compatible so the stock PYNQ image can verify/start installation, but generated services bind the explicitly qualified Plasma interpreter. The installer never replaces `/usr/bin/python3` or the PYNQ venv.

## Installer kit

The `PPU release artifact` workflow transports an identity-qualified kit:

```text
Actions artifact:
plasma-ppu-linux-armv7l-<release-id>

contents:
plasma-ppu-<release-id>-linux-armv7l.tar.gz
plasma-ppu-<release-id>-linux-armv7l.tar.gz.sha256
plasma-ppu-z2-installer-<release-id>.py
plasma-ppu-z2-installer-<release-id>.py.sha256
```

The installer script remains a bootstrap component rather than Common Release Format payload. Detached hashes prove exact bytes, not publisher authenticity.

## Verification before mutation

The bootstrap validates:

1. detached release archive SHA-256;
2. safe `tar.gz` structure under `plasma-release/`;
3. no unsafe/non-regular archive members or extraction-limit breach;
4. exact internal `SHA256SUMS` file set and digests;
5. `release.json` full source identity, `ppu/linux/armv7l` target and contracts;
6. PPU runtime identity;
7. closed hardware boundary;
8. production Device Catalog presence;
9. explicit Plasma-owned ARMv7 final Python >=3.11.

Example read-only verification:

```bash
python3 plasma-ppu-z2-installer-0.1.1-abcdef123456.py verify \
  --release-artifact plasma-ppu-0.1.1-abcdef123456-linux-armv7l.tar.gz \
  --sidecar plasma-ppu-0.1.1-abcdef123456-linux-armv7l.tar.gz.sha256
```

## Filesystem and service boundary

```text
/opt/plasma/
├── python/
├── releases/
│   └── <release-id>/
├── current -> releases/<release-id>/
└── install/last-install.json

/etc/plasma/ppu.yaml
/var/lib/plasma/
/var/log/plasma/
/etc/systemd/system/plasma-server.service
/etc/systemd/system/plasma-web.service
```

A dedicated `plasma` system user owns mutable state/logs. Immutable release content and service units remain system-owned.

## PS-only topology contract

The generated first-stage configuration deliberately keeps:

```yaml
server:
  max_supported_sites: 8

sites: []
```

This means:

```text
max_supported_sites = 8   capacity ceiling
site_count           = 0   current configured topology
enabled_site_count   = 0
sites                = []
```

This is a valid fail-closed PS-only state. It is **not** a claim that the eventual appliance has no Sites, and it does not create a canonical `Site 0`. When physical Sites exist their IDs remain one-based.

Manager must therefore accept a trusted PPU identity/topology observation with `site_count=0` when `/api/status.sites=[]` is consistent. Fabricating eight Sites merely to satisfy fleet admission would overclaim hardware topology and is prohibited.

## Network binding

Qualification requires an explicit non-loopback unicast IPv4 address for `--gateway-host`; wildcard `0.0.0.0` is rejected.

The Plasma Server remains `127.0.0.1:9900`. Plasma Gateway binds the explicit Z2 address on `18080` and connects locally to Server. Installer-local health uses a proxy-free client.

## Installation

Example:

```bash
sudo python3 plasma-ppu-z2-installer-0.1.1-abcdef123456.py install \
  --release-artifact plasma-ppu-0.1.1-abcdef123456-linux-armv7l.tar.gz \
  --sidecar plasma-ppu-0.1.1-abcdef123456-linux-armv7l.tar.gz.sha256 \
  --plasma-python /opt/plasma/python/<version>/bin/python3 \
  --gateway-host 192.168.2.99 \
  --ppu-id z2-dev-01 \
  --facility-id lab
```

The `sudo python3` process is bootstrap only. Runtime services bind the explicit Plasma Python path.

## Activation and rollback

Installation is side-by-side and source-identity-aware:

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

Activation failure rolls back the active link and managed service/configuration state. Incomplete rollback is reported explicitly; a failed immutable candidate may remain for evidence but is not active.

## Evidence levels

`/opt/plasma/install/last-install.json` supports only the exact claims it records, including exact release/source identity, isolated Python, systemd activation and Z2-local Gateway readiness.

Managed PS Loopback is separate end-to-end evidence:

```text
Mac Control Station
  -> same-origin Manager BFF
  -> Manager selected alias z2
  -> Z2 Plasma Gateway :18080
  -> Z2 Plasma Server :9900
  -> PS diagnostic handler
  -> return
```

Canonical acceptance:

```bash
python3 scripts/runtime_acceptance/run.py ps-loopback \
  --base-url http://127.0.0.1:18000/api/manager/ppu \
  --environment managed-z2-ps
```

Only after this passes for the exact deployed Control Station and PPU source identities may the record state **Managed PS Loopback PASS**.

## PYNQ regression requirement

After installation, re-check PYNQ-owned Python/PYNQ. Plasma installation must not replace that ownership domain.

## Explicit non-claims

This phase does not qualify PS↔PL, FPGA execution/loading, PMOD/Site electrical behavior, target power, real IC programming, 8-Site hardware concurrency, publisher signing/authenticity, or a bundled Plasma Python runtime.
