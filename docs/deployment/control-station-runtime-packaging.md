# Control Station Runtime Packaging

> Status: **Current**. PR #224 established the Control Station application-runtime payload and its macOS/Linux/Windows clean-runtime acceptance. This document defines the common runtime boundary; host installation belongs to separate platform adapters such as the macOS and Windows installer pilots.

## 1. Purpose

The Control Station product role must run without a Git worktree, npm/pip installation, Vite development server, Wrangler, GNU `timeout`, or SWPC deployment assumptions.

The build boundary is:

```text
source tree / CI build host
    |
    +-- Vinext product build
    |      -> dist/standalone
    |
    +-- Plasma Manager source + PyYAML
           -> Python zipapp
    |
    v
Control Station runtime payload
    |
    v
Common Release Format
    |
    v
clean extraction
    |
    +-- Node >= 22.13 -> Console/BFF
    +-- Python >= 3.11 -> Manager
```

## 2. Runtime ownership

A Control Station owns exactly two application processes in this phase:

```text
Control Station
├── Console / same-host BFF
└── Plasma Manager
```

It does not include:

```text
PPU Gateway
Plasma Server
PS / PL execution
Site hardware execution
```

Those remain PPU responsibilities.

## 3. Console product build

The existing Cloudflare/Mock CD build remains intact for development and existing acceptance workflows.

Product packaging uses a separate build mode:

```text
PLASMA_PRODUCT_BUILD=1
    -> Vinext build
    -> next.config.ts output="standalone"
    -> dist/standalone/
```

The product runtime entry point is:

```text
node console/server.js
```

The standalone payload contains Vinext-selected runtime dependencies under:

```text
console/node_modules/
```

This is not the repository development `node_modules` tree. Vinext standalone copies the server externals selected by its build graph plus the Vinext production runtime and its runtime dependencies.

The product target therefore requires Node.js but does not require npm, Vinext CLI, Vite, Wrangler, Git, or GNU `timeout` at runtime.

## 4. Manager runtime

Manager is packaged as:

```text
manager/manager.pyz
```

The zipapp contains:

```text
plasma_manager/
yaml/                 # pure-Python PyYAML runtime
__main__.py
```

The target invocation is conceptually:

```text
python manager/manager.pyz --config <persistent-manager-config>
```

The target requires Python >= 3.11 but does not run `pip install`.

PyYAML third-party license text is distributed beside the zipapp:

```text
manager/THIRD_PARTY_LICENSES/PyYAML.txt
```

## 5. Runtime manifest

The runtime payload root contains:

```text
control-station-runtime.json
```

It identifies:

- role = `control-station`;
- Console runtime family, requirement and entry point;
- Manager runtime family, requirement and entry point;
- required Console environment-variable names;
- packaging method for Console and Manager;
- bundled third-party runtime metadata and license location.

It deliberately does not own persistent Manager registry data, secrets, service-manager definitions, logs, or operator state.

## 6. Runtime payload layout

```text
runtime/
├── control-station-runtime.json
├── console/
│   ├── server.js
│   ├── dist/
│   ├── node_modules/
│   └── ... Vinext standalone runtime files
└── manager/
    ├── manager.pyz
    └── THIRD_PARTY_LICENSES/
        └── PyYAML.txt
```

`console/node_modules/**` is the only allowed `node_modules` location in a Control Station runtime release. Generic Common Release Format packaging continues to reject arbitrary `node_modules` payloads; `scripts/control-station-release.py` first validates the Control Station runtime contract and narrows the exception to the Vinext standalone Console tree before delegating archive construction to `scripts/product-release.py`.

## 7. Configuration boundary

Console/BFF keeps the existing Manager routing safety contract:

```text
PLASMA_MANAGER_API_URL
PLASMA_MANAGER_PPU_ALIAS
```

The Manager URL remains loopback-only. The selected PPU alias remains explicit. Packaging does not infer a PPU alias or convert browser state into authoritative fleet configuration.

The standalone server uses Vinext runtime variables:

```text
HOST
PORT
```

Persistent product configuration is still outside the immutable runtime payload.

## 8. Clean-runtime acceptance

The dedicated CI workflow runs on:

```text
Linux
macOS
Windows
```

Each host performs:

```text
npm ci                         # build host only
Vinext standalone product build
    ↓
Control Station runtime assembly
    ↓
Manager zipapp assembly
    ↓
Control Station release artifact
    ↓
Common Release Format verification
    ↓
clean extraction outside the source runtime path
    ↓
start packaged Manager
    ↓
start packaged Console/BFF
    ↓
POST same-origin Manager BFF route with browser-style Fetch semantics
    ↓
Manager resolves configured PPU alias
    ↓
expected PPU transport failure from a deliberately unused endpoint
    ↓
BFF relays Manager's structured 504 response
    ↓
PASS
```

The deliberately unreachable PPU proves the Console/BFF -> Manager process boundary without claiming a PPU, Z2, PS, PL, or IC acceptance result.

## 9. Common-runtime evidence

Passing common-runtime acceptance supports these claims:

```text
Control Station Runtime Package PASS
Vinext standalone Console/BFF PASS on tested host OS
Packaged Manager zipapp PASS on tested host OS
Common Release Format integration PASS
Clean extraction runtime startup PASS
Console/BFF -> Manager local route PASS
```

The common-runtime evidence alone does not prove a platform installer or service adapter. macOS installer evidence is owned by the separate [macOS Control Station Installer Pilot](macos-control-station-installer-pilot.md); Windows MSI/SCM evidence is owned by the separate [Windows Control Station Installer Pilot](windows-control-station-installer-pilot.md). Linux installer/systemd, upgrade/rollback, bundled interpreters, PPU/Z2, PS <-> PL, and real-IC behavior remain separate evidence boundaries.

## 10. Platform adapter boundary

Platform adapters consume the same common application contract:

```text
Control Station runtime payload
        |
        +-- macOS launchd adapter      # unsigned .pkg pilot implemented
        +-- Linux systemd adapter      # pending
        +-- Windows SCM adapter        # unsigned MSI pilot implemented
```

The adapters own filesystem placement, service definitions, privileges, install lifecycle and host-specific logging integration. They must not fork the Console/BFF or Manager application behavior by operating system.

The macOS and Windows pilots deliberately keep Node.js and Python external. macOS records validated absolute executable paths for `launchd`; Windows resolves supported system-wide runtime locations from its SCM launch wrappers. Both separate immutable application payload from mutable configuration/state/logs. Signing and full upgrade/rollback remain outside these pilots.
