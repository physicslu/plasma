# Windows Control Station Installer Pilot

Status: **Current pilot implementation**

## Purpose

This adapter turns the verified Windows `control-station/windows/x86_64` Common Release Format payload into an unsigned per-machine MSI and validates the real Windows Service Control Manager lifecycle on a GitHub-hosted Windows runner.

It consumes the same Control Station application runtime as macOS/Linux. It does not fork Console/BFF or Manager behavior by operating system.

## Boundary

```text
verified Control Station release
  -> pinned WinSW service adapter
  -> pinned WiX v5 build tool
  -> unsigned MSI
  -> %ProgramFiles% immutable versioned runtime
  -> %ProgramData% mutable config/state/logs
  -> Windows SCM
     |- PlasmaManager
     `- PlasmaControlStationConsole
```

The MSI does not contain PPU Gateway/Server, Z2 software, FPGA assets, PL access, target-power behavior, or real-IC programming logic.

## Filesystem contract

Immutable application payload:

```text
%ProgramFiles%\Plasma\releases\<version>\
|- runtime\
|- bin\
|- THIRD_PARTY_LICENSES\WinSW.txt
`- windows-installer.json
```

Mutable machine state:

```text
%ProgramData%\Plasma\
|- config\manager.yaml
|- config\selected-ppu-alias
|- state\
`- logs\
```

The config seed components are `Permanent` and `NeverOverwrite`. Basic uninstall removes the immutable release and SCM registrations but preserves mutable configuration. Upgrade/rollback migration remains a separate milestone.

## Service adapter

The pilot uses WinSW `2.12.0` as the thin SCM adapter. The workflow downloads the official `WinSW-x64.exe` release asset and verifies the pinned SHA-256 before packaging:

```text
05b82d46ad331cc16bdc00de5c6332c1ef818df8ceefcd49c726553209b3a0da
```

The WinSW MIT license is shipped in the installed release. The binary is not checked into Plasma source control.

SCM services are installed by Windows Installer itself; Task Scheduler is not used.

The Console service declares an SCM dependency on the Manager service.

## Runtime prerequisites

The first Windows pilot intentionally keeps language runtimes external:

```text
Node.js >= 22.13
Python >= 3.11
```

Service launchers resolve supported system-wide locations and fail closed when the required runtime is not available. npm, pip, Git, Vite and the source worktree are not target-runtime requirements.

Bundling Node/Python is deferred because it changes redistribution, security-update and installer ownership responsibilities.

## MSI build

`scripts/windows-control-station-msi.py`:

1. verifies the Common Release Format input as `control-station/windows/x86_64`;
2. validates the packaged common runtime;
3. verifies the pinned WinSW binary digest;
4. stages the Windows service wrapper, PowerShell launchers and third-party license;
5. emits WiX v5 authoring using built-in `Files` harvesting for the immutable runtime tree;
6. builds `plasma-control-station-<version>-windows-x86_64.msi`;
7. emits a detached `.sha256` sidecar.

WiX Toolset `5.0.2` is pinned as a build dependency. WiX v5 is required because built-in `Files` harvesting is a WiX v5 feature; WiX v4 and earlier require a separate harvesting mechanism. WiX is build-host tooling and is not installed on the Control Station by the MSI.

## CI acceptance

`.github/workflows/windows-control-station-installer.yml` runs on `windows-latest` and performs:

```text
source checkout
  -> common Control Station runtime build
  -> Windows Common Release Format build
  -> focused packaging tests
  -> pinned WinSW download + SHA-256 verification
  -> pinned WiX CLI install
  -> unsigned MSI build
  -> MSI install
  -> SCM registration + initial service start
  -> Manager health
  -> Console health
  -> Browser-style Fetch: Console/BFF -> Manager
  -> SCM restart persistence
  -> SCM stop/start
  -> MSI uninstall
  -> service removal
  -> mutable config preservation
  -> upload MSI + SHA-256 artifact
```

The Browser/BFF smoke points Manager at a deliberately unused loopback PPU endpoint and expects the existing structured `ppu_transport_error` path. This proves the installed Console/BFF -> Manager boundary without claiming PPU or Z2 acceptance.

## Evidence boundary

A passing Windows installer workflow supports:

```text
Windows x86_64 Common Runtime               PASS
Windows MSI construction                    PASS
ProgramFiles / ProgramData placement        PASS
SCM Manager service                         PASS
SCM Console/BFF service                     PASS
install / restart / stop-start / uninstall  PASS
mutable config preservation                 PASS
```

It does not prove:

```text
code signing / trusted publisher             NOT PROVEN
bundled Node/Python                          NOT IMPLEMENTED
upgrade / rollback migration                 NOT IMPLEMENTED
real operator Windows machine                NOT PROVEN BY CI
Manager -> real Z2                           NOT PROVEN
PS <-> PL / hardware / real IC               NOT PROVEN
```

The CI artifact is an unsigned installer pilot, not production Windows distribution readiness.
