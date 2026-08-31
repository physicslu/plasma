# Windows Control Station Installer Pilot

Status: **Current pilot implementation**

## Purpose

This adapter turns the verified Windows `control-station/windows/x86_64` Common Release Format payload into an unsigned per-machine MSI and validates the real Windows Service Control Manager lifecycle on a GitHub-hosted Windows runner.

It consumes the same Control Station application runtime as macOS/Linux. It does not fork Console/BFF or Manager behavior by operating system.

The Windows distribution owns its language runtimes. A target workstation does **not** need a preinstalled Python or Node.js runtime.

## Boundary

```text
verified Control Station release
  -> pinned CPython embeddable runtime
  -> pinned Node.js runtime
  -> pinned WinSW service adapter
  -> pinned WiX v5 build tool
  -> unsigned self-contained MSI
  -> %ProgramFiles% immutable versioned release
     |- application runtime
     |- bundled host runtimes
     `- Windows service adapters
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
|  |- manager\manager.pyz
|  `- console\server.js
|- host-runtime\
|  |- python\python.exe
|  `- node\node.exe
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

SCM services are installed by Windows Installer itself; Task Scheduler is not used. The Console service declares an SCM dependency on the Manager service.

The Console launcher establishes `runtime\console` as the process working directory before starting the standalone Vinext `server.js`. This working-directory contract is part of the packaged Web runtime: SSR can start from another directory, but Vinext resolves packaged `/assets/*` client files relative to the standalone runtime root. The launcher also enables the Control Station fleet UI explicitly instead of inheriting the standalone PPU default.

## Self-contained runtime ownership

Windows no longer treats Python or Node.js as host prerequisites. The MSI contains pinned runtimes under the immutable release tree:

```text
CPython 3.12.10 Windows embeddable x64
Node.js 22.23.0 Windows x64
```

The pinned source archive digests are:

```text
CPython 3.12.10 embed-amd64 ZIP
4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3

Node.js 22.23.0 win-x64 ZIP
425a5bd68cc95e8eb16bcccd0a75081b48983fc6a26f67126bd4d6c7198231e8
```

The build workflow downloads these official archives and fails closed on SHA-256 mismatch before MSI construction. The CPython license and Node.js license are shipped with the installed bundled runtimes.

The service launchers resolve exactly one runtime path each:

```text
Manager -> <release>\host-runtime\python\python.exe
Console -> <release>\host-runtime\node\node.exe
```

They do not inspect HKCU, HKLM Python registration, the user PATH, or the machine PATH for alternative interpreters. This removes the earlier privilege-boundary ambiguity where a `LocalSystem` service could accidentally depend on a workstation-managed interpreter.

The CPython embeddable `_pth` file remains isolated. Packaging adds the Manager zipapp to that explicit path contract rather than enabling global `site-packages`. The Manager application's PyYAML dependency remains inside `manager.pyz`.

This changes operational ownership: Plasma must now track Python/Node security updates and deliberately issue a new Control Station build when those runtimes need patching. That is preferable to allowing the behavior of an installed production tool to vary with arbitrary workstation runtime state.

npm, pip, Git, Vite and the source worktree remain build-time concerns and are not target-runtime requirements.

## MSI build

`scripts/windows-control-station-msi.py`:

1. verifies the Common Release Format input as `control-station/windows/x86_64`;
2. validates the packaged common runtime;
3. verifies the pinned WinSW binary digest;
4. stages the pinned bundled Python and Node.js target runtimes;
5. stages the Windows service wrapper, PowerShell launchers and third-party licenses;
6. emits WiX v5 authoring using built-in `Files` harvesting for the immutable release tree;
7. builds `plasma-control-station-<version>-windows-x86_64.msi`;
8. emits a detached `.sha256` sidecar.

WiX Toolset `5.0.2` is pinned as a build dependency. WiX v5 is required because built-in `Files` harvesting is a WiX v5 feature; WiX v4 and earlier require a separate harvesting mechanism. WiX is build-host tooling and is not installed on the Control Station by the MSI.

## CI acceptance

`.github/workflows/windows-control-station-installer.yml` runs on `windows-latest` and performs:

```text
source checkout
  -> download pinned CPython embeddable archive + SHA-256 verify
  -> download pinned Node.js archive + SHA-256 verify
  -> common Control Station runtime build
  -> Windows Common Release Format build
  -> focused packaging tests
  -> pinned WinSW download + SHA-256 verification
  -> pinned WiX CLI install
  -> self-contained MSI build
  -> MSI install
  -> assert installed manifest runtime_ownership=bundled
  -> assert launchers bind to installed bundled Python/Node paths
  -> SCM registration + initial service start
  -> Manager health
  -> Console root HTML
  -> fetch every referenced packaged CSS/JavaScript asset and require HTTP 200 + non-empty content
  -> Browser-style Fetch using installed bundled Node: Console/BFF -> Manager
  -> SCM restart persistence
  -> revalidate packaged CSS/JavaScript assets after restart
  -> SCM stop/start
  -> MSI uninstall
  -> service removal
  -> mutable config preservation
  -> upload MSI + SHA-256 artifact
```

The static-asset check closes a gap that a plain HTTP-200 Console readiness probe cannot detect: the standalone server can render SSR HTML while `/assets/*.css` and `/assets/*.js` fail if the service starts from the wrong working directory.

The Browser/BFF smoke points Manager at a deliberately unused loopback PPU endpoint and expects the existing structured `ppu_transport_error` path. This proves the installed Console/BFF -> Manager boundary without claiming PPU or Z2 acceptance.

## Evidence boundary

A passing Windows installer workflow supports:

```text
Windows x86_64 Common Runtime                PASS
Windows MSI construction                     PASS
ProgramFiles / ProgramData placement         PASS
bundled CPython runtime ownership             PASS
bundled Node.js runtime ownership             PASS
SCM Manager service                          PASS
SCM Console/BFF service                      PASS
packaged Console CSS/JavaScript serving      PASS
install / restart / stop-start / uninstall   PASS
mutable config preservation                  PASS
```

It does not prove:

```text
code signing / trusted publisher             NOT PROVEN
runtime CVE update automation                NOT IMPLEMENTED
upgrade / rollback migration                 NOT IMPLEMENTED
real operator Windows machine                NOT PROVEN BY CI
Manager -> real Z2                           NOT PROVEN
PS <-> PL / hardware / real IC               NOT PROVEN
```

The CI artifact is an unsigned installer pilot, not production Windows distribution readiness.
