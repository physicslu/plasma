# PYNQ-Z2 PS Installer and Managed Loopback Acceptance

Status: **PS-only installer implementation; real Z2 qualification required after merge**

## Purpose

`scripts/ppu-z2-installer.py` is the first host-mutating product adapter for the PPU/Z2 role. It consumes the canonical `ppu/linux/armv7l` Common Release Format artifact and activates only the PS software node:

```text
verified PPU release
  -> immutable /opt/plasma/releases/<version>-<sha-prefix>
  -> /opt/plasma/current
  -> plasma-server.service
  -> plasma-web.service
  -> /api/health/ready
```

The installer does not load an FPGA bitstream, access PL, enable physical Sites, change target power, or program a real IC.

## Runtime ownership

ADR-0001 is mandatory. PYNQ owns its System Python and Plasma owns a separate runtime.

The currently observed development Z2 baseline is:

```text
architecture      armv7l
OS                PynqLinux 3.0 (Carlisle), Ubuntu 22.04 base
glibc             2.35
systemd           249
System Python     3.10.4
PYNQ              3.1.1
Ethernet          192.168.2.99/24
```

The PYNQ System Python is not a valid Plasma interpreter because the Plasma baseline is Python >= 3.11. The installer bootstrap itself remains Python-3.10-compatible so the stock image can verify and launch the installation transaction, but `--plasma-python` must identify an executable ARMv7 **final** Python release >= 3.11 beneath:

```text
/opt/plasma/python/
```

A numeric `3.11.x` version alone is not sufficient. The probe also requires `sys.version_info.releaselevel == "final"`. This matters on the current Ubuntu 22.04 base because Jammy exposes an ARMHF `python3.11` package at `3.11.0~rc1`; that prerelease must not be accepted as a Plasma-qualified runtime.

Typical ownership is therefore:

```text
/usr/bin/python3.10                    PYNQ / OS owned; unchanged
/opt/plasma/python/<version>/...       Plasma owned isolated runtime
/opt/plasma/releases/<release-id>/     immutable Plasma release
/opt/plasma/current                    active release symlink
```

The installer fails closed rather than replacing `/usr/bin/python3`, changing the PYNQ venv, silently running Plasma under Python 3.10, or accepting an alpha/beta/RC interpreter as production runtime evidence.

## Installer kit

The `PPU release artifact` workflow transports four files in one Actions artifact:

```text
plasma-ppu-<version>-linux-armv7l.tar.gz
plasma-ppu-<version>-linux-armv7l.tar.gz.sha256
plasma-ppu-z2-installer.py
plasma-ppu-z2-installer.py.sha256
```

The installer script is a transport/bootstrap component, not part of the Common Release Format payload. Its detached hash protects transport integrity; neither hash is publisher-authenticity evidence.

## Verification before mutation

The bootstrap validates, in order:

1. detached release-archive SHA-256;
2. safe `tar.gz` structure under the single `plasma-release/` root;
3. no symlink/device/non-regular members, traversal, duplicate paths, or extraction-limit breach;
4. exact internal `SHA256SUMS` file set and digests;
5. `release.json` identity `ppu/linux/armv7l` and Protocol/API contracts;
6. PPU runtime manifest identity;
7. closed hardware boundary;
8. production Device Catalog presence;
9. explicit Plasma-owned ARMv7 final Python release >= 3.11.

Read-only verification can run before root access:

```bash
python3 plasma-ppu-z2-installer.py verify \
  --release-artifact plasma-ppu-0.1.0-linux-armv7l.tar.gz \
  --sidecar plasma-ppu-0.1.0-linux-armv7l.tar.gz.sha256
```

## Filesystem and service boundary

Default product-owned paths are:

```text
/opt/plasma/
├── python/                    isolated Plasma interpreter ownership
├── releases/                  immutable exact release directories
├── current -> releases/...    active release
└── install/last-install.json  local installer evidence

/etc/plasma/ppu.yaml
/var/lib/plasma/
/var/log/plasma/
/etc/systemd/system/plasma-server.service
/etc/systemd/system/plasma-web.service
```

A dedicated `plasma` system user owns mutable state/logs. Release content and service units remain system-owned.

The generated PS-only configuration deliberately keeps:

```yaml
sites: []
```

This is a fail-closed qualification configuration, not a claim that the physical appliance has zero Sites.

## Network binding

The first Z2 qualification requires an explicit non-loopback unicast IPv4 address for `--gateway-host`. Wildcard `0.0.0.0` is rejected by the installer so an operator cannot accidentally broaden the trust boundary while commissioning the board.

For the currently observed development board:

```text
192.168.2.99
```

The Plasma Server remains bound to `127.0.0.1:9900`. The Plasma Gateway binds the explicit Z2 address on port `18080` and connects locally to the Server. Installer-local `/api/health/ready` uses a proxy-free urllib opener so host `HTTP_PROXY` / `HTTPS_PROXY` state cannot redirect or fabricate the local qualification path.

## Installation

After an isolated Plasma Python has separately been provisioned and qualified under `/opt/plasma/python/`, the intended command is:

```bash
sudo python3 plasma-ppu-z2-installer.py install \
  --release-artifact plasma-ppu-0.1.0-linux-armv7l.tar.gz \
  --sidecar plasma-ppu-0.1.0-linux-armv7l.tar.gz.sha256 \
  --plasma-python /opt/plasma/python/<version>/bin/python3 \
  --gateway-host 192.168.2.99 \
  --ppu-id z2-dev-01 \
  --facility-id lab
```

The `sudo python3` process is only the bootstrap transaction. Generated services bind the explicit `--plasma-python` absolute path and never rely on interactive `PATH` or `/usr/bin/python3`.

## Activation and rollback

Installation is side-by-side and exact-SHA aware:

```text
verify everything
  -> copy immutable release
  -> snapshot managed config + systemd units
  -> write candidate PS-only config and systemd units
  -> atomically move /opt/plasma/current
  -> daemon-reload
  -> enable/start Server
  -> enable/start Gateway
  -> direct/no-proxy /api/health/ready
```

If activation/readiness fails, rollback is transactional across the active release link and managed service configuration:

- with an existing installation, the previous `current` release, `/etc/plasma/ppu.yaml`, `plasma-server.service`, and `plasma-web.service` bytes/metadata are restored, systemd is reloaded, and the previous services are restarted;
- on first installation, candidate services are stopped/disabled, the candidate `current` link is removed, and newly created managed config/unit files are removed.

If rollback itself is incomplete, installation reports that fact explicitly instead of claiming recovery. The failed immutable candidate may remain under `releases/` for evidence/debugging; it is not considered active.

## Evidence levels in this phase

A successful installer-local health transaction records:

```text
/opt/plasma/install/last-install.json
```

That evidence supports only:

```text
exact PPU release installed       PASS
isolated final Plasma Python      PASS
systemd activation                PASS
Z2-local Gateway readiness        PASS
```

It explicitly does **not** claim Managed PS Loopback. Managed routing is a separate end-to-end acceptance from the installed Mac Control Station:

```text
Mac Control Station
  -> same-origin Manager BFF
  -> Manager selected alias z2
  -> http://192.168.2.99:18080 Plasma Gateway
  -> Z2 Plasma Server :9900
  -> PS diagnostic handler
  -> return
```

Run the existing scenario from the Control Station:

```bash
python3 scripts/runtime_acceptance/run.py ps-loopback \
  --base-url http://127.0.0.1:18000/api/manager/ppu \
  --environment managed-z2-ps
```

Only after that scenario passes may the qualification record state **Managed PS Loopback PASS**.

## PYNQ regression requirement

PS isolation is not complete merely because Plasma starts. After installation, re-check the PYNQ-owned baseline:

```bash
python3 --version
python3 - <<'PY'
import pynq
print(pynq.__version__)
PY
```

The expected system/PYNQ baseline remains Python 3.10.x with PYNQ import working. Plasma installation must not replace that ownership domain.

## Explicit non-claims

This installer phase does not qualify:

- PS <-> PL;
- FPGA loading or execution;
- PMOD/Site electrical behavior;
- target power control;
- real IC programming;
- 8-Site hardware concurrency;
- production publisher signing/authenticity;
- a bundled Python runtime.

The isolated Python runtime remains a separately provisioned qualification prerequisite until a future release carries a PYNQ-Z2-qualified bundled interpreter.
