# macOS Control Station Installer Pilot

> Status: **Pilot implementation**. This layer consumes a verified Common Release Format Control Station artifact, produces an **unsigned, non-notarized macOS `.pkg`**, and validates installation plus per-user `launchd` lifecycle. It is not yet the production distribution/signing/upgrade contract.

## 1. Scope and release boundary

The macOS installer is a platform adapter; it is not a second release system. Its input must pass the canonical release pipeline first:

```text
Control Station runtime
├── Console / same-host BFF
└── Plasma Manager
        ↓
Control Station Common Release Format artifact
        ↓
detached SHA-256 verification
        ↓
safe extraction + release.json + SHA256SUMS verification
        ↓
macOS installer staging
        ↓
unsigned .pkg
        ↓
immutable installation under /Library/Application Support/Plasma
        ↓
per-user launchd LaunchAgents
        ↓
Console/BFF + Manager
```

`scripts/macos-control-station-pkg.py` accepts `--release-artifact`; it does not accept a raw `--runtime-dir`. This preserves the Common Release Format as the single integrity and source-identity boundary between build output and installer construction.

Release Identity v2 applies to both the package filename and installed immutable directory:

```text
release_id = <product-version>-<first-12-git-sha>
```

The package manifest retains the full source Git SHA and source release artifact SHA-256.

The pilot does **not** add bundled Python/Node runtimes, Developer ID signing, notarization, full upgrade migration, deterministic rollback, PPU/Z2 deployment, FPGA execution, or real IC programming.

## 2. Filesystem boundary

System-owned immutable payload:

```text
/Library/Application Support/Plasma/
├── releases/
│   └── <release-id>/
│       ├── runtime/
│       ├── bin/
│       ├── launchd/
│       └── macos-installer.json
├── current -> releases/<release-id>/
└── install/
    ├── node-path
    ├── python-path
    └── user
```

Example:

```text
/Library/Application Support/Plasma/releases/0.1.1-abcdef123456/
```

Per-user mutable data remains separate:

```text
~/Library/Application Support/Plasma/
├── config/
│   ├── manager.yaml
│   └── selected-ppu-alias
└── state/

~/Library/Logs/Plasma/
├── manager.log
└── console.log

~/Library/LaunchAgents/
├── com.plasma.manager.plist
└── com.plasma.console.plist
```

The `.pkg` does not guess a user's home while laying down immutable payload. Postinstall identifies the operator account and creates only per-user mutable/service state.

Acceptance verifies the system application root, activation symlink, runtime payload, and recorded runtime bindings are root-owned and not group/world writable. Generated operator config and LaunchAgent files must belong to the operator user.

## 3. External runtime prerequisites

The pilot currently requires:

```text
Python >= 3.11
Node.js >= 22.13
```

The target does not run `pip install`, `npm install`, Git, Vite, Vinext CLI, or Wrangler.

`launchd` must not depend on an interactive shell profile or PATH. Installation resolves concrete executable paths from stable locations, records them under `/Library/Application Support/Plasma/install/`, and LaunchAgents execute those recorded paths.

## 4. Service contract

The pilot uses per-user LaunchAgents `com.plasma.manager` and `com.plasma.console`.

Default local bindings are:

```text
Manager  127.0.0.1:18180
Console  127.0.0.1:18000
```

The Console wrapper keeps the Manager URL loopback-only. The installer creates an empty selected PPU alias and empty runtime registry by default; it never invents a command target.

The service helper remains `/Library/Application Support/Plasma/current/bin/service-control.sh` and supports start/stop/restart/status.

## 5. Build

```bash
cd software/web
npm ci
npm run build:product
cd ../..

python3 scripts/control-station-runtime.py build \
  --standalone-console software/web/dist/standalone \
  --output-dir /tmp/plasma-control-station-runtime

ARCH="$(uname -m)"
python3 scripts/control-station-release.py \
  --runtime-dir /tmp/plasma-control-station-runtime \
  --output-dir /tmp/plasma-control-station-release \
  --platform macos \
  --architecture "$ARCH" \
  --git-sha "$(git rev-parse HEAD)"

RELEASE="$(find /tmp/plasma-control-station-release -maxdepth 1 -name '*.tar.gz' -print -quit)"
python3 scripts/macos-control-station-pkg.py \
  --release-artifact "$RELEASE" \
  --output-dir /tmp/plasma-macos-installer
```

For product version `0.1.1` and source SHA prefix `abcdef123456`, the installer filename is:

```text
plasma-control-station-0.1.1-abcdef123456-macos-<arch>.pkg
```

A matching `.pkg.sha256` is emitted. `macos-installer.json` records:

```text
product_version
release_id
source_release.git_sha          # full 40-character source SHA
source_release.artifact_sha256  # Common Release Format input bytes
source_release.target
source_release.contracts
```

The package itself remains unsigned in this pilot.

## 6. Install and local access

Install the exact identity-qualified file, for example:

```bash
sudo installer \
  -pkg plasma-control-station-0.1.1-abcdef123456-macos-arm64.pkg \
  -target /
```

After LaunchAgents are healthy, Console is local at `http://127.0.0.1:18000/`.

The installer fails if it cannot resolve Python >=3.11 or Node.js >=22.13 for the operator account.

## 7. Basic uninstall

The pilot ships:

```text
/Library/Application Support/Plasma/current/bin/uninstall-pilot.sh
```

Uninstall removes LaunchAgent jobs/definitions, immutable releases/current/install metadata, and package receipt. Mutable operator config, state, and logs are intentionally preserved. Full data policy, upgrade migration, rollback, and multi-user behavior remain future work.

## 8. CI acceptance

`.github/workflows/macos-control-station-installer.yml` performs build, Common Release Format verification, `.pkg` construction, installation, ownership checks, absolute runtime binding checks, LaunchAgent lifecycle, Manager/Console readiness, Browser-style Console/BFF→Manager smoke, restart, stop/start, and uninstall.

The downloadable GitHub Actions artifact itself is also identity-qualified:

```text
plasma-control-station-macos-installer-<release-id>
```

This prevents two same-SemVer builds from appearing under the same Actions artifact name.

## 9. Claims and non-claims

A passing pilot supports only the tested macOS architecture and installer/control-plane boundaries. It does not prove Developer ID signing, notarization, Gatekeeper production distribution, upgrade/rollback, multi-user product installation, PPU/Z2 deployment, PS↔PL, or real IC programming.

Release Identity v2 improves traceability; it does not by itself make an artifact production-signed or hardware-qualified.
