# Windows Control Station Installer Pilot

Status: **Current pilot implementation**

## Purpose

This adapter turns the verified Windows `control-station/windows/x86_64` Common Release Format payload into an unsigned per-machine MSI and validates the real Windows Service Control Manager lifecycle on a GitHub-hosted Windows runner.

It consumes the same Control Station application runtime as macOS/Linux. It does not fork Console/BFF or Manager behavior by operating system.

The Windows distribution owns its language runtimes. A target workstation does **not** need a preinstalled Python or Node.js runtime.

Release Identity v2 applies to both the MSI filename and immutable Program Files release directory:

```text
release_id = <product-version>-<first-12-git-sha>
```

The installed manifest retains the full source Git SHA and source Common Release Format artifact digest.

## Boundary

```text
verified Control Station release
  -> pinned CPython embeddable runtime
  -> pinned Node.js runtime
  -> pinned WinSW service adapter
  -> pinned WiX v5 build tool
  -> unsigned self-contained MSI
  -> %ProgramFiles% immutable release-id directory
     |- application runtime
     |- bundled host runtimes
     `- Windows service adapters
  -> %ProgramData% mutable config/state/logs
  -> Windows SCM
     |- PlasmaManager
     `- PlasmaControlStationConsole
```

The MSI contains no PPU Gateway/Server, Z2 software, FPGA assets, PL access, target-power behavior, or real-IC programming logic.

## Filesystem contract

Immutable application payload:

```text
%ProgramFiles%\Plasma\releases\<release-id>\
|- runtime\
|  |- manager\manager.pyz
|  `- console\server.js
|- host-runtime\
|  |- python\python.exe
|  `- node\node.exe
|- bin\
|- THIRD_PARTY_LICENSES\WinSW.txt
`- windows-installer.json
```

Example:

```text
%ProgramFiles%\Plasma\releases\0.1.1-abcdef123456\
```

Mutable machine state:

```text
%ProgramData%\Plasma\
|- config\manager.yaml
|- config\selected-ppu-alias
|- state\
`- logs\
```

The config seed components remain `Permanent` and `NeverOverwrite`. Basic uninstall removes immutable release content and SCM registrations but preserves mutable configuration. Upgrade/rollback migration remains a separate milestone.

## Service adapter

The pilot uses WinSW `2.12.0` as the thin SCM adapter. The workflow downloads the official `WinSW-x64.exe` and verifies the pinned SHA-256:

```text
05b82d46ad331cc16bdc00de5c6332c1ef818df8ceefcd49c726553209b3a0da
```

SCM services are installed by Windows Installer; Task Scheduler is not used. Console declares an SCM dependency on Manager.

## Vinext Windows static-asset compatibility boundary

Plasma currently pins `vinext` `0.0.50`. Its production `StaticFileCache` can otherwise retain Windows backslash-separated relative asset paths while browser URL paths use forward slashes, producing Windows-only packaged asset 404s.

Until the pinned dependency contains the fix natively, `software/web/scripts/patch-vinext-windows-static-assets.mjs` applies the narrow normalization:

```text
path.relative(base, file)
  -> path.relative(base, file).split(path.sep).join("/")
```

The patch fails closed on version/layout drift and runs at build time; the installed target does not patch dependencies.

## Self-contained runtime ownership

The MSI contains pinned runtimes:

```text
CPython 3.12.10 Windows embeddable x64
Node.js 22.23.0 Windows x64
```

Pinned source archive digests:

```text
CPython 3.12.10 embed-amd64 ZIP
4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3

Node.js 22.23.0 win-x64 ZIP
425a5bd68cc95e8eb16bcccd0a75081b48983fc6a26f67126bd4d6c7198231e8
```

The service launchers bind only to bundled runtime paths under the immutable release. They do not inspect user/machine PATH or alternate Python registrations.

## MSI build

`scripts/windows-control-station-msi.py`:

1. verifies the Common Release Format input as `control-station/windows/x86_64`;
2. validates the packaged common runtime;
3. derives `release_id` from product version plus source SHA prefix;
4. verifies the pinned WinSW binary digest;
5. stages pinned bundled Python and Node.js runtimes;
6. stages service wrappers, launchers and licenses;
7. emits WiX v5 authoring with an immutable `<release-id>` Program Files directory;
8. builds `plasma-control-station-<release-id>-windows-x86_64.msi`;
9. emits a detached `.sha256` sidecar.

Example:

```text
plasma-control-station-0.1.1-abcdef123456-windows-x86_64.msi
```

The MSI package version remains the SemVer `product_version` (for Windows Installer upgrade semantics); the immutable filesystem/build identity is the SHA-qualified `release_id`. These are intentionally different concepts.

`windows-installer.json` records `product_version`, `release_id`, bundled runtime ownership, and full source release provenance.

WiX Toolset `5.0.2` is pinned as build tooling and is not installed on the target Control Station.

## CI acceptance

`.github/workflows/windows-control-station-installer.yml` covers pinned runtime downloads and hashes, product runtime build, Common Release Format verification, packaging tests, WinSW/WiX, MSI installation, installed manifest/runtime binding, SCM lifecycle, Manager/Console health, packaged static assets, Browser-style BFF→Manager smoke, restart, stop/start, uninstall and mutable config preservation.

The downloadable GitHub Actions artifact is identity-qualified:

```text
plasma-control-station-windows-installer-<release-id>
```

This prevents same-SemVer builds from being indistinguishable in the Actions UI/download directory.

## Evidence boundary

A passing workflow supports Windows x86_64 common runtime, MSI construction, Program Files/ProgramData placement, bundled runtime ownership, SCM services, packaged static assets and installer lifecycle for the tested runner.

It does **not** prove code signing, trusted publisher distribution, upgrade/rollback migration, a real operator workstation, Manager→real Z2, PS↔PL, or real IC programming.

Release Identity v2 improves provenance and field traceability; it is not publisher-authenticity evidence.
