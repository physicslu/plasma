# Plasma Product Release Format v1

> Status: **Current**. The manifest schema remains v1. Current deployment identity policy is **Release Identity v2**: every deployable artifact is named by product version plus a 12-character source Git SHA prefix, while the manifest retains the full 40-character Git SHA and detached SHA-256 integrity evidence.

## 1. Purpose

Plasma product deployment must consume immutable release artifacts rather than interpret the source repository on the target machine.

```text
source repository
    |
    | build/test environment
    v
already-built runtime payload
    |
    v
scripts/product-release.py build
    |
    v
canonical Plasma release artifact
    |
    | later installer phases
    v
Control Station or PPU
```

`product-release.py` is a build/release tool. It is not an installer and does not run npm, pip, source compilation, service mutation, FPGA loading, or IC programming.

## 2. Version, release identity, and digest

Canonical product metadata lives in `release/product.json`. The current product version is:

```text
product_version = 0.2.0
```

Product version is independent from Web/Python component package versions.

Release Identity v2 separates three concerns:

```text
product_version = 0.2.0
full git_sha    = abcdef1234567890...40 hex characters...
release_id      = 0.2.0-abcdef123456
artifact_sha256 = <64 hex characters>
```

Their meanings are deliberately different:

- `product_version` is the SemVer product version used for product evolution and platform package-version semantics.
- `release_id` is the immutable deployment/build identity: `<product-version>-<first-12-git-sha>`.
- `artifact_sha256` identifies the exact artifact bytes and proves transport/integrity equality.

A different source Git SHA MUST NOT reuse the same deployable artifact filename or immutable release directory even when `product_version` is unchanged. Rebuilding the same source may retain the same `release_id`, but the detached artifact digest remains the exact-byte identity.

The full Git SHA remains authoritative provenance. The 12-character prefix is a human-operational identity used in filenames and install paths; it does not replace the full SHA in `release.json`.

## 3. Supported v1 release targets

### Control Station

```text
macos-arm64
macos-x86_64
linux-arm64
linux-x86_64
windows-x86_64
```

### PPU

```text
linux-armv7l
```

Unsupported role/platform/architecture combinations fail closed.

## 4. Artifact naming and archive format

Canonical Common Release Format names are now:

```text
plasma-control-station-<release-id>-macos-arm64.tar.gz
plasma-control-station-<release-id>-macos-x86_64.tar.gz
plasma-control-station-<release-id>-linux-arm64.tar.gz
plasma-control-station-<release-id>-linux-x86_64.tar.gz
plasma-control-station-<release-id>-windows-x86_64.zip
plasma-ppu-<release-id>-linux-armv7l.tar.gz
```

Example:

```text
plasma-ppu-0.2.0-abcdef123456-linux-armv7l.tar.gz
```

Common Release Format does not mean every operating system uses the same archive container:

- macOS/Linux/PPU use `tar.gz`;
- Windows uses ZIP.

Platform installers inherit the same release identity. Examples:

```text
plasma-control-station-0.2.0-abcdef123456-macos-arm64.pkg
plasma-control-station-0.2.0-abcdef123456-windows-x86_64.msi
```

## 5. Canonical bundle layout

Every archive has one canonical root:

```text
plasma-release/
├── release.json
├── SHA256SUMS
├── runtime/
└── config/
    └── defaults/
```
