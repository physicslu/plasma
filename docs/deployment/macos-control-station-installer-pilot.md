# macOS Control Station Installer Pilot

> Status: **Pilot implementation**. This layer packages the already validated Control Station runtime into an **unsigned, non-notarized macOS `.pkg`** and validates installation plus per-user `launchd` lifecycle. It is not yet the production distribution/signing/upgrade contract.

## 1. Scope

This pilot consumes the common Control Station runtime produced by the existing product build:

```text
Control Station runtime
├── Console / same-host BFF
└── Plasma Manager
```

It adds only the macOS host adapter:

```text
validated runtime
    ↓
unsigned .pkg
    ↓
immutable installation under /Library/Application Support/Plasma
    ↓
per-user launchd LaunchAgents
    ↓
Console/BFF + Manager
```

The pilot does **not** add Linux or Windows installers, bundled Python/Node runtimes, Developer ID signing, notarization, full upgrade migration, deterministic rollback, PPU/Z2 deployment, FPGA execution, or real IC programming.

## 2. Filesystem boundary

The pilot deliberately separates immutable application runtime from mutable operator data.

System-owned immutable payload:

```text
/Library/Application Support/Plasma/
├── releases/
│   └── <version>/
│       ├── runtime/
│       ├── bin/
│       ├── launchd/
│       └── macos-installer.json
├── current -> releases/<version>/
└── install/
    ├── node-path
    ├── python-path
    └── user
```

Per-user mutable data:

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

The `.pkg` therefore does not need to guess a user's home while laying down the immutable payload. The postinstall step identifies the operator account and creates only the per-user mutable/service state for that account.

## 3. External runtime prerequisites

The pilot deliberately keeps the PR #224 runtime policy:

```text
Python >= 3.11
Node.js >= 22.13
```

The target does not run `pip install`, `npm install`, Git, Vite, Vinext CLI, or Wrangler.

`launchd` must not depend on `.zshrc`, `.bashrc`, nvm shell activation, pyenv shell activation, or an interactive `PATH`. During installation, the postinstall logic resolves and validates concrete executable paths from stable common locations, including `/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin`, `~/.nvm/versions/node/*/bin/node`, and `~/.pyenv/versions/*/bin/python3`.

The selected executable paths are persisted as absolute paths in `/Library/Application Support/Plasma/install/node-path` and `/Library/Application Support/Plasma/install/python-path`. The LaunchAgents start fixed shell wrappers, and those wrappers `exec` the recorded absolute runtime path.

## 4. Service contract

The pilot uses per-user LaunchAgents `com.plasma.manager` and `com.plasma.console`.

Default local bindings are `Manager: 127.0.0.1:18180` and `Console: 127.0.0.1:18000`. The Console wrapper keeps `PLASMA_MANAGER_API_URL=http://127.0.0.1:18180` loopback-only.

The selected PPU alias remains explicit. The installer creates an empty `selected-ppu-alias` file and an empty Manager PPU registry by default; it does not silently infer or invent a command target.

The included pilot service helper supports `start`, `stop`, `restart`, and `status` through `/Library/Application Support/Plasma/current/bin/service-control.sh`.

## 5. Build

A macOS build host first produces the standalone Console and common Control Station runtime, then builds the `.pkg`:

```bash
cd software/web
npm ci
npm run build:product
cd ../..

python3 scripts/control-station-runtime.py build \
  --standalone-console software/web/dist/standalone \
  --output-dir /tmp/plasma-control-station-runtime

python3 scripts/macos-control-station-pkg.py \
  --runtime-dir /tmp/plasma-control-station-runtime \
  --output-dir /tmp/plasma-macos-installer
```

The installer builder emits `plasma-control-station-<version>-macos-<arch>.pkg` and a matching `.pkg.sha256`. The package is intentionally unsigned in this pilot.

## 6. Install and local access

Install with `sudo installer -pkg plasma-control-station-<version>-macos-<arch>.pkg -target /`. After the LaunchAgents are healthy, the local Console is expected at `http://127.0.0.1:18000/`.

The installer must fail if it cannot resolve Python >= 3.11 or Node.js >= 22.13 for the selected operator account.

## 7. Basic uninstall

The pilot ships `sudo "/Library/Application Support/Plasma/current/bin/uninstall-pilot.sh"`.

The uninstall contract removes LaunchAgent definitions/jobs, immutable releases/current/install metadata, and the package receipt. It intentionally preserves mutable operator config, state, and logs. Full uninstall-data policy, upgrade migration, rollback, and multi-user handling remain future product work.

## 8. CI acceptance

`.github/workflows/macos-control-station-installer.yml` runs on a GitHub-hosted macOS environment and performs build standalone Console → build common runtime → build unsigned `.pkg` → `sudo installer` → verify installed paths/runtime bindings → verify both LaunchAgents → Manager health → Console health → deterministic unreachable smoke PPU → restart → Browser-style Fetch → Console/BFF → Manager → expected `504 ppu_transport_error` → restart persistence → stop/start → basic uninstall.

The workflow uploads the `.pkg` and detached SHA-256 text file as the Actions artifact `plasma-control-station-macos-installer-pilot`.

## 9. Claims and non-claims

A passing pilot supports `macOS unsigned Installer Pilot PASS`, `macOS launchd LaunchAgent activation PASS`, install/start/restart/stop-start/basic-uninstall, installed Browser → Console/BFF → Manager, and external Node/Python absolute runtime binding.

It does not support Developer ID signing, Apple notarization, Gatekeeper production distribution, upgrade migration, rollback, multi-user product install, Linux/Windows installers, PPU/Z2 deployment, or real IC programming.
